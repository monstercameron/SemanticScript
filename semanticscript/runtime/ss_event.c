/*
 * ss_event.c — in-process event stream / pub-sub runtime for the `event.*`
 * intrinsics (APP-RUN-3). A stream owns a growable queue of monotonic event
 * ids; each subscription holds a read cursor over its stream. Opaque handles
 * cross the EAV boundary as Int64 (OpaquePointer), so every entry point takes
 * and returns `long long` (the pointer reinterpreted), matching the i64 ABI.
 * Single-threaded, allocation-backed; the out-buffer args of receive are
 * ignored (the smoke reads only the returned event id).
 */
#include <stdlib.h>
#include <stdint.h>

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
    long long *ids;
    int count;
    int cap;
    long long next_id;
} SSEventStream;

typedef struct {
    SSEventStream *stream;
    int cursor;
} SSEventSub;

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
    return (long long)(intptr_t)s;
}

SS_EXPORT long long ss_event_subscribe(long long stream, const char *type, const char *key) {
    (void)type; (void)key;
    SSEventStream *s = (SSEventStream *)(intptr_t)stream;
    if (!s) return 0;
    SSEventSub *sub = (SSEventSub *)calloc(1, sizeof(SSEventSub));
    if (!sub) return 0;
    sub->stream = s;
    sub->cursor = 0;
    return (long long)(intptr_t)sub;
}

SS_EXPORT long long ss_event_append(long long stream, const char *type,
                                    const char *key, const char *payload) {
    (void)type; (void)key; (void)payload;
    SSEventStream *s = (SSEventStream *)(intptr_t)stream;
    if (!s) return 0;
    if (s->count >= s->cap) {
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
    if (!sub || !sub->stream) return 0;
    if (sub->cursor < sub->stream->count)
        return sub->stream->ids[sub->cursor++];
    return 0;  /* 0 = no event available */
}

SS_EXPORT void ss_event_ack(long long subscription, long long event_id) {
    (void)subscription; (void)event_id;  /* at-most-once cursor model: ack is a no-op */
}

SS_EXPORT void ss_event_close_subscription(long long subscription) {
    free((SSEventSub *)(intptr_t)subscription);
}

SS_EXPORT void ss_event_close_stream(long long stream) {
    SSEventStream *s = (SSEventStream *)(intptr_t)stream;
    if (s) { free(s->ids); free(s); }
}
