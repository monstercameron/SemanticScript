/*
 * ss_event.c — in-process event stream / pub-sub runtime for the `event.*`
 * intrinsics (APP-RUN-3). A stream owns a growable queue of monotonic event
 * ids; each subscription holds a read cursor over its stream. Source-visible
 * handles are pointer-typed OpaquePointer values; this legacy C shim still
 * takes/returns `long long`, and the compiler bridges explicitly at the call
 * boundary.
 * Single-threaded, allocation-backed; the out-buffer args of receive are
 * ignored (the smoke reads only the returned event id).
 */
#include <stdlib.h>
#include <stdint.h>
#include "ss_runtime_export.h"

typedef struct SSEventStream SSEventStream;
typedef struct SSEventSub SSEventSub;

struct SSEventStream {
    long long *ids;
    int count;
    int cap;
    long long next_id;
    /* R-131: the live subscriptions parented to this stream. closeStream orphans
     * them (NULLs each back-pointer) before freeing, so a later receive on an
     * orphaned subscription returns 0 instead of dereferencing this freed stream
     * (the subscription-after-close use-after-free). */
    SSEventSub **subs;
    int sub_count;
    int sub_cap;
};

struct SSEventSub {
    SSEventStream *stream;
    int cursor;
};

/*
 * R-131: a registry of live streams (the sqlite R-139 tombstone pattern). A
 * double closeStream finds the stream already untracked and becomes a no-op
 * instead of a double-free, and subscribe/append on a closed stream are rejected
 * by membership rather than dereferencing freed memory. Membership compares
 * pointer VALUES only — a freed pointer's fields are never read. Single-threaded
 * (one loop thread owns the runtime), so no lock is needed.
 */
static SSEventStream **g_live_streams = NULL;
static size_t g_live_count = 0;
static size_t g_live_cap = 0;

static int ss_event_track_stream(SSEventStream *s) {
    if (g_live_count == g_live_cap) {
        size_t next = g_live_cap == 0 ? 8 : g_live_cap * 2;
        if (g_live_cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(SSEventStream *)) {
            return 0;
        }
        SSEventStream **grown = (SSEventStream **)realloc(
            g_live_streams, next * sizeof(SSEventStream *));
        if (!grown) return 0;
        g_live_streams = grown;
        g_live_cap = next;
    }
    g_live_streams[g_live_count++] = s;
    return 1;
}

static int ss_event_is_live_stream(const SSEventStream *s) {
    for (size_t i = 0; i < g_live_count; i++) {
        if (g_live_streams[i] == s) return 1;
    }
    return 0;
}

static int ss_event_untrack_stream(SSEventStream *s) {
    for (size_t i = 0; i < g_live_count; i++) {
        if (g_live_streams[i] == s) {
            g_live_streams[i] = g_live_streams[g_live_count - 1];
            g_live_count--;
            return 1;
        }
    }
    return 0;
}

/*
 * R-196: a registry of live subscriptions, mirroring the stream tombstone above.
 * R-131 parent-tracked subscriptions on their stream (so closeStream could orphan
 * them) but kept no global registry, so receive/close validated a raw subscription
 * handle with only a NULL check — a stale (already-closed, freed) handle is
 * non-NULL, so `sub->stream` read freed memory (use-after-free) and a double
 * close_subscription double-freed. Membership here is checked by pointer VALUE
 * before any field is read. Single-threaded, so no lock is needed.
 */
static SSEventSub **g_live_subs = NULL;
static size_t g_live_sub_count = 0;
static size_t g_live_sub_cap = 0;

static int ss_event_track_sub(SSEventSub *sub) {
    if (g_live_sub_count == g_live_sub_cap) {
        size_t next = g_live_sub_cap == 0 ? 8 : g_live_sub_cap * 2;
        if (g_live_sub_cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(SSEventSub *)) {
            return 0;
        }
        SSEventSub **grown = (SSEventSub **)realloc(
            g_live_subs, next * sizeof(SSEventSub *));
        if (!grown) return 0;
        g_live_subs = grown;
        g_live_sub_cap = next;
    }
    g_live_subs[g_live_sub_count++] = sub;
    return 1;
}

static int ss_event_is_live_sub(const SSEventSub *sub) {
    for (size_t i = 0; i < g_live_sub_count; i++) {
        if (g_live_subs[i] == sub) return 1;
    }
    return 0;
}

static int ss_event_untrack_sub(SSEventSub *sub) {
    for (size_t i = 0; i < g_live_sub_count; i++) {
        if (g_live_subs[i] == sub) {
            g_live_subs[i] = g_live_subs[g_live_sub_count - 1];
            g_live_sub_count--;
            return 1;
        }
    }
    return 0;
}

SS_EXPORT long long ss_event_open_stream(const char *name, long long capacity) {
    (void)name;
    /* R-131: a huge `capacity` would truncate through the int `cap` (then the
     * calloc count wraps), and the ring allocation was unchecked. Clamp to a
     * sane range and verify both allocations. */
    if (capacity <= 0) {
        capacity = 16;
    }
    if (capacity > (1 << 24)) {
        return 0;  /* refuse an absurd ring size */
    }
    SSEventStream *s = (SSEventStream *)calloc(1, sizeof(SSEventStream));
    if (!s) return 0;
    s->cap = (int)capacity;
    s->ids = (long long *)calloc((size_t)s->cap, sizeof(long long));
    if (!s->ids) {
        free(s);
        return 0;
    }
    s->next_id = 1;
    if (!ss_event_track_stream(s)) {  /* registry growth failed */
        free(s->ids);
        free(s);
        return 0;
    }
    return (long long)(intptr_t)s;
}

SS_EXPORT long long ss_event_subscribe(long long stream, const char *type, const char *key) {
    (void)type; (void)key;
    SSEventStream *s = (SSEventStream *)(intptr_t)stream;
    /* R-131: no subscribing to a closed/never-opened stream (membership check,
     * never a deref of a possibly-freed pointer). */
    if (!s || !ss_event_is_live_stream(s)) return 0;
    SSEventSub *sub = (SSEventSub *)calloc(1, sizeof(SSEventSub));
    if (!sub) return 0;
    /* R-196: register in the live-subscription tombstone before handing the
     * handle out, so receive/close can validate it by membership. On any
     * subsequent failure, untrack before freeing so the registry never holds a
     * dangling pointer. */
    if (!ss_event_track_sub(sub)) { free(sub); return 0; }
    /* parent-track: record the subscription on its stream so closeStream can
     * orphan it. Grow the list first; on failure free the sub and fail. */
    if (s->sub_count == s->sub_cap) {
        int ncap = s->sub_cap == 0 ? 4 : s->sub_cap * 2;
        if (ncap <= 0) { ss_event_untrack_sub(sub); free(sub); return 0; }  /* int overflow guard */
        SSEventSub **grown = (SSEventSub **)realloc(
            s->subs, (size_t)ncap * sizeof(SSEventSub *));
        if (!grown) { ss_event_untrack_sub(sub); free(sub); return 0; }
        s->subs = grown;
        s->sub_cap = ncap;
    }
    sub->stream = s;
    sub->cursor = 0;
    s->subs[s->sub_count++] = sub;
    return (long long)(intptr_t)sub;
}

SS_EXPORT long long ss_event_append(long long stream, const char *type,
                                    const char *key, const char *payload) {
    (void)type; (void)key; (void)payload;
    SSEventStream *s = (SSEventStream *)(intptr_t)stream;
    /* R-131: appending to a closed stream is rejected, not a deref of freed
     * memory. */
    if (!s || !ss_event_is_live_stream(s)) return 0;
    if (s->count >= s->cap) {
        /* R-131: bound the doubling so `s->cap * 2` can't overflow the int and
         * wrap the realloc count. open_stream already caps the initial size. */
        if (s->cap <= 0 || s->cap > (1 << 24)) {
            return 0;
        }
        int ncap = s->cap * 2;
        long long *nids = (long long *)realloc(s->ids, (size_t)ncap * sizeof(long long));
        if (!nids) return 0;
        s->ids = nids;
        s->cap = ncap;
    }
    long long id = s->next_id++;
    s->ids[s->count++] = id;
    return id;
}

SS_EXPORT long long ss_event_receive(long long subscription) {
    SSEventSub *sub = (SSEventSub *)(intptr_t)subscription;
    /* R-196: reject a stale/closed subscription by membership BEFORE reading any
     * field (a freed handle is non-NULL; the prior bare `!sub` check let it
     * dereference freed memory). An orphaned-but-live sub has stream == NULL. */
    if (!sub || !ss_event_is_live_sub(sub) || !sub->stream) return 0;
    if (sub->cursor < sub->stream->count)
        return sub->stream->ids[sub->cursor++];
    return 0;  /* 0 = no event available */
}

SS_EXPORT void ss_event_ack(long long subscription, long long event_id) {
    (void)subscription; (void)event_id;  /* at-most-once cursor model: ack is a no-op */
}

SS_EXPORT void ss_event_close_subscription(long long subscription) {
    SSEventSub *sub = (SSEventSub *)(intptr_t)subscription;
    /* R-196: untrack first (membership by pointer value, no deref). A double
     * close or a bogus handle fails membership and becomes a no-op instead of a
     * double-free / use-after-free. Only a confirmed-live sub is dereferenced. */
    if (!sub || !ss_event_untrack_sub(sub)) return;
    /* R-131: unlink from the parent stream's list (if the stream is still live)
     * so a later closeStream cannot write through this freed sub pointer. After a
     * closeStream sub->stream is already NULL, so we simply free. */
    SSEventStream *s = sub->stream;
    if (s && ss_event_is_live_stream(s)) {
        for (int i = 0; i < s->sub_count; i++) {
            if (s->subs[i] == sub) {
                s->subs[i] = s->subs[s->sub_count - 1];
                s->sub_count--;
                break;
            }
        }
    }
    free(sub);
}

SS_EXPORT void ss_event_close_stream(long long stream) {
    SSEventStream *s = (SSEventStream *)(intptr_t)stream;
    /* R-131: a double closeStream finds the stream already untracked -> no-op,
     * not a double-free (untrack compares pointer values, never derefs `s`). */
    if (!s || !ss_event_untrack_stream(s)) return;
    /* Orphan every live subscription so a later receive returns 0 instead of
     * dereferencing this freed stream (subscription-after-close UAF). */
    for (int i = 0; i < s->sub_count; i++) {
        if (s->subs[i]) s->subs[i]->stream = NULL;
    }
    free(s->subs);
    free(s->ids);
    free(s);
}
