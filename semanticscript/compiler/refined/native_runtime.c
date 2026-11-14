/* The runtime of a standalone executable built with `refined build --kind executable`.
 *
 * It implements the callbacks compiled code makes (see CALLBACKS in codegen.py) in plain C, so the
 * program's object file and this file link statically into one executable with no Python. It covers
 * the core language (output, regions, traps with a stack trace, the call stack, recursion and stack
 * guards, strings, tasks run when started) and the native host library (D-80): files and directories,
 * arguments, the environment, standard input, child processes, deadlines and clocks, byte buffers,
 * `string.fromBytes`, maps and sets, and log lines. Each behaves as its handler in host.py does, error
 * variants included. Compiled code reaches them through the same `refined_host` name dispatch the JIT
 * uses, so the generated code is the same for both; `TARGETS` below is the list of what is native, and
 * native.py reads it to refuse (R901) only programs that call something else (D-81).
 *
 * The entry and its stack budget come from the small file `build` generates, which hands the program
 * its command line with `refined_start` (D-82).
 */
#if !defined(_WIN32)
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE 1
#define _DARWIN_C_SOURCE 1
#endif
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <fcntl.h>
#include <io.h>
#include <sys/locking.h>
#include <sys/stat.h>
#else
#include <dirent.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
extern char **environ;
#endif

#define TRAP_EXIT_CODE 70
#define NEVER (-1)

static void trap_text(const char *message);

/* room for `need` items, the new ones zeroed */
static void *grow(void *p, int64_t *cap, int64_t need, size_t item) {
    if (need <= *cap) return p;
    int64_t n = *cap ? *cap : 8;
    while (n < need) n *= 2;
    char *q = realloc(p, (size_t)n * item);
    if (!q) trap_text("out of memory in the runtime");
    memset(q + (size_t)*cap * item, 0, (size_t)(n - *cap) * item);
    *cap = n;
    return q;
}

/* ---------------------------------------------------------------- the call stack, traps */

typedef struct Frame { const char *name; int64_t len; } Frame;
static Frame *frames;
static int64_t frame_count, frame_cap;
static int64_t frame_base;  /* the first frame of the task that is running (D-37: tasks run on this stack) */
static int task_depth;
static int64_t stack_floor;
static int64_t *depth;  /* per recursive operation, by the id the compiler gives it */
static int64_t depth_cap;

void refined_set_floor(int64_t floor) { stack_floor = floor; }

static int64_t release_all(void);

static int same_frame(const Frame *a, const Frame *b) {
    return a->len == b->len && (a->name == b->name || memcmp(a->name, b->name, (size_t)a->len) == 0);
}

/* As the JIT prints it (tasks.stack_trace): the running task's operations, innermost first, consecutive repeats
   collapsed into one line with a count, at most 12 lines, then how many more, then whether a task was running. */
void refined_trap(const char *p, int64_t n) {
    fflush(stdout);
    fprintf(stderr, "trap: %.*s\n", (int)n, p);
    int64_t runs = 0;
    for (int64_t i = frame_count - 1; i >= frame_base;) {
        int64_t j = i, k = 0;
        while (j >= frame_base && same_frame(&frames[j], &frames[i])) {
            j--;
            k++;
        }
        if (runs < 12) {
            if (k > 1)
                fprintf(stderr, "  in %.*s (%lld calls deep)\n", (int)frames[i].len, frames[i].name, (long long)k);
            else
                fprintf(stderr, "  in %.*s\n", (int)frames[i].len, frames[i].name);
        }
        runs++;
        i = j;
    }
    if (runs > 12) fprintf(stderr, "  ... and %lld more\n", (long long)(runs - 12));
    if (task_depth > 0) fputs("  (in a task started with `start`)\n", stderr);
    int64_t released = release_all();
    if (released)
        fprintf(stderr, "the runtime released %lld resource%s the program still held (files flushed and closed, "
                "connections closed, child processes stopped); deferred cleanups do not run after a trap\n",
                (long long)released, released != 1 ? "s" : "");
    fflush(stderr);
    exit(TRAP_EXIT_CODE);
}

static void trap_text(const char *message) { refined_trap(message, (int64_t)strlen(message)); }

int32_t refined_recursion_enter(int64_t op, int64_t limit, int64_t here) {
    if (op < 0) trap_text("a recursive operation has no depth counter");
    depth = grow(depth, &depth_cap, op + 1, sizeof(int64_t));
    int64_t d = ++depth[op];
    if (d > limit) return 1;
    if (stack_floor && here < stack_floor) return 2;
    return 0;
}
void refined_recursion_leave(int64_t op) {
    if (op >= 0 && op < depth_cap) --depth[op];
}

void refined_frame_push(const char *p, int64_t n) {
    if (frame_count >= frame_cap) {
        int64_t cap = frame_cap ? frame_cap * 2 : 1024;
        Frame *f = realloc(frames, (size_t)cap * sizeof(Frame));
        if (!f) {
            frame_count++;  /* the trace loses this frame; the program goes on */
            return;
        }
        frames = f;
        frame_cap = cap;
    }
    frames[frame_count].name = p;
    frames[frame_count].len = n;
    frame_count++;
}
void refined_frame_pop(void) {
    if (frame_count > 0) frame_count--;
}

void refined_block(const char *p, int64_t n, void **values, int64_t count, const char *d, int64_t dn) {
    (void)p; (void)n; (void)values; (void)count; (void)d; (void)dn;
}

/* ---------------------------------------------------------------- output */

int32_t refined_write(int32_t fd, const char *p, int64_t n, int32_t newline) {
    FILE *f = fd == 2 ? stderr : stdout;
    if (fd == 2) fflush(stdout);  /* the JIT writes unbuffered, so the two streams interleave as written */
    if (n > 0 && fwrite(p, 1, (size_t)n, f) != (size_t)n) return errno ? errno : 1;
    if (newline && fputc('\n', f) == EOF) return errno ? errno : 1;
    return 0;
}

int32_t refined_write_int(int32_t fd, int64_t v, int32_t newline) {
    FILE *f = fd == 2 ? stderr : stdout;
    if (fd == 2) fflush(stdout);
    return fprintf(f, newline ? "%lld\n" : "%lld", (long long)v) < 0;
}

int32_t refined_write_float(int32_t fd, double v, int32_t newline) {
    FILE *f = fd == 2 ? stderr : stdout;
    char buf[64];
    /* shortest text that reads back as the same double, as the JIT runtime prints it */
    for (int digits = 1; digits <= 17; digits++) {
        snprintf(buf, sizeof buf, "%.*g", digits, v);
        if (strtod(buf, NULL) == v) break;
    }
    if (!strchr(buf, '.') && !strchr(buf, 'e') && !strchr(buf, 'n') && !strchr(buf, 'i')) strcat(buf, ".0");
    return fprintf(f, newline ? "%s\n" : "%s", buf) < 0;
}

int32_t refined_bytes_equal(const char *a, int64_t an, const char *b, int64_t bn) {
    return an == bn && (an == 0 || memcmp(a, b, (size_t)an) == 0);
}

/* ---------------------------------------------------------------- regions: chunked bump allocation (D-84) */

#define REGION_ALIGN 16
#define CHUNK_FIRST 4096
#define CHUNK_LAST (1 << 20)
typedef struct Chunk { struct Chunk *next; size_t size, used; } Chunk;
#define CHUNK_HEAD ((sizeof(Chunk) + REGION_ALIGN - 1) & ~(size_t)(REGION_ALIGN - 1))

typedef struct Region {
    int64_t capacity, used;  /* `used` counts the bytes asked for, as the JIT does, so `arena.remaining` agrees */
    Chunk *chunks;           /* the chunk being filled first */
    size_t next_chunk;
    const char *label;
    int64_t label_len;
    int64_t *handles;        /* host objects released with the region (maps, buffers, listings, ...) */
    int64_t handle_count, handle_cap;
} Region;

void *refined_region_new(int64_t capacity, const char *label, int64_t label_len) {
    Region *r = calloc(1, sizeof(Region));
    if (!r) trap_text("out of memory creating a region");
    r->capacity = capacity;
    r->label = label;
    r->label_len = label_len;
    r->next_chunk = CHUNK_FIRST;
    return r;
}

static Chunk *new_chunk(size_t size) {
    Chunk *c = calloc(1, CHUNK_HEAD + size);  /* zeroed, and never reused, so every allocation starts zeroed */
    if (!c) trap_text("out of memory in a region");
    c->size = size;
    return c;
}

void *refined_region_alloc(void *handle, int64_t size) {
    Region *r = handle;
    if (size < 0 || r->used + size > r->capacity) {
        char msg[256];
        snprintf(msg, sizeof msg, "%.*s exceeded its capacity of %lld bytes", (int)r->label_len, r->label,
                 (long long)r->capacity);
        trap_text(msg);
    }
    r->used += size;
    size_t need = ((size_t)(size > 0 ? size : 1) + REGION_ALIGN - 1) & ~(size_t)(REGION_ALIGN - 1);
    Chunk *c = r->chunks;
    if (c && c->size - c->used >= need) {
        void *p = (char *)c + CHUNK_HEAD + c->used;
        c->used += need;
        return p;
    }
    if (need > CHUNK_LAST / 4) {
        /* a large block gets a chunk of its own, behind the one being filled */
        Chunk *big = new_chunk(need);
        big->used = need;
        if (c) {
            big->next = c->next;
            c->next = big;
        } else {
            r->chunks = big;
        }
        return (char *)big + CHUNK_HEAD;
    }
    size_t want = r->next_chunk;
    while (want < need) want *= 2;
    Chunk *n = new_chunk(want);
    n->next = c;
    r->chunks = n;
    if (r->next_chunk < CHUNK_LAST) r->next_chunk *= 2;
    n->used = need;
    return (char *)n + CHUNK_HEAD;
}

int64_t refined_region_remaining(void *handle) {
    Region *r = handle;
    return r->capacity - r->used;
}

static void drop(int64_t h);

void refined_region_free(void *handle) {
    Region *r = handle;
    for (int64_t i = 0; i < r->handle_count; i++) drop(r->handles[i]);
    free(r->handles);
    for (Chunk *c = r->chunks; c;) {
        Chunk *n = c->next;
        free(c);
        c = n;
    }
    free(r);
}

/* ---------------------------------------------------------------- text */

void *refined_format_int(int64_t v, void *region, int64_t *out_len) {
    char buf[32];
    int n = snprintf(buf, sizeof buf, "%lld", (long long)v);
    char *p = refined_region_alloc(region, n);
    memcpy(p, buf, (size_t)n);
    *out_len = n;
    return p;
}

int64_t refined_find(const char *h, int64_t hn, const char *nd, int64_t nn) {
    if (nn == 0) return 0;
    for (int64_t i = 0; i + nn <= hn; i++)
        if (memcmp(h + i, nd, (size_t)nn) == 0) return i;
    return -1;
}

int32_t refined_parse_int(const char *p, int64_t n, int64_t *out) {
    *out = 0;
    int64_t i = 0;
    int negative = 0;
    if (n > 0 && p[0] == '-') { negative = 1; i = 1; }
    if (i >= n) return 1;
    uint64_t limit = negative ? (uint64_t)INT64_MAX + 1 : (uint64_t)INT64_MAX, v = 0;
    for (; i < n; i++) {
        if (p[i] < '0' || p[i] > '9') return 1;
        uint64_t d = (uint64_t)(p[i] - '0');
        if (v > (limit - d) / 10) return 2;
        v = v * 10 + d;
    }
    *out = negative ? (int64_t)(0 - v) : (int64_t)v;
    return 0;
}

/* D-91: a Float64 as the shortest text that reads back as it (as refined_write_float prints it) */
void *refined_format_float(double v, void *region, int64_t *out_len) {
    char buf[64];
    for (int digits = 1; digits <= 17; digits++) {
        snprintf(buf, sizeof buf, "%.*g", digits, v);
        if (strtod(buf, NULL) == v) break;
    }
    if (!strchr(buf, '.') && !strchr(buf, 'e') && !strchr(buf, 'n') && !strchr(buf, 'i')) strcat(buf, ".0");
    int64_t n = (int64_t)strlen(buf);
    char *p = refined_region_alloc(region, n);
    memcpy(p, buf, (size_t)n);
    *out_len = n;
    return p;
}

/* D-91: 0 parsed, 1 not a number, 2 too large for a Float64. The text is `-`? digits (`.` digits)?
   ([eE] [+-]? digits)?, nothing else. */
int32_t refined_parse_float(const char *p, int64_t n, double *out) {
    *out = 0.0;
    int64_t i = 0, start;
    if (i < n && p[i] == '-') i++;
    start = i;
    while (i < n && p[i] >= '0' && p[i] <= '9') i++;
    if (i == start) return 1;
    if (i < n && p[i] == '.') {
        start = ++i;
        while (i < n && p[i] >= '0' && p[i] <= '9') i++;
        if (i == start) return 1;
    }
    if (i < n && (p[i] == 'e' || p[i] == 'E')) {
        i++;
        if (i < n && (p[i] == '+' || p[i] == '-')) i++;
        start = i;
        while (i < n && p[i] >= '0' && p[i] <= '9') i++;
        if (i == start) return 1;
    }
    if (i != n) return 1;
    char *buf = malloc((size_t)n + 1);
    if (!buf) trap_text("out of memory reading a number");
    memcpy(buf, p, (size_t)n);
    buf[n] = 0;
    double v = strtod(buf, NULL);
    free(buf);
    if (v > 1.7976931348623157e308 || v < -1.7976931348623157e308) return 2;
    *out = v;
    return 0;
}

/* The offset of the first byte that does not start a valid UTF-8 sequence, or -1: the same strict rules and
   the same offset as Python's decoder (no overlong forms, no surrogates, nothing past U+10FFFF). */
static int64_t utf8_invalid_at(const unsigned char *s, int64_t n) {
    int64_t i = 0;
    while (i < n) {
        unsigned char b = s[i];
        int64_t need;
        unsigned char lo = 0x80, hi = 0xBF;
        if (b < 0x80) { i++; continue; }
        if (b >= 0xC2 && b <= 0xDF) need = 1;
        else if (b == 0xE0) { need = 2; lo = 0xA0; }
        else if ((b >= 0xE1 && b <= 0xEC) || b == 0xEE || b == 0xEF) need = 2;
        else if (b == 0xED) { need = 2; hi = 0x9F; }
        else if (b == 0xF0) { need = 3; lo = 0x90; }
        else if (b >= 0xF1 && b <= 0xF3) need = 3;
        else if (b == 0xF4) { need = 3; hi = 0x8F; }
        else return i;
        for (int64_t k = 1; k <= need; k++) {
            if (i + k >= n) return i;
            unsigned char c = s[i + k];
            if (k == 1 ? (c < lo || c > hi) : (c < 0x80 || c > 0xBF)) return i;
        }
        i += need + 1;
    }
    return -1;
}

/* ---------------------------------------------------------------- tests (not part of an executable's run) */

void refined_assert_int(int64_t e, int64_t a, const char *c, int64_t cn) {
    if (e != a) trap_text("an assertion failed (tests run with `refined test`)");
    (void)c; (void)cn;
}
void refined_assert_true(int32_t v, const char *c, int64_t cn) {
    if (!v) trap_text("an assertion failed (tests run with `refined test`)");
    (void)c; (void)cn;
}
void refined_assert_str(const char *a, int64_t an, const char *b, int64_t bn, const char *c, int64_t cn) {
    if (!refined_bytes_equal(a, an, b, bn)) trap_text("an assertion failed (tests run with `refined test`)");
    (void)c; (void)cn;
}
void refined_fail(const char *p, int64_t n, const char *c, int64_t cn) { refined_trap(p, n); (void)c; (void)cn; }

/* ---------------------------------------------------------------- tasks: run when started */

void *refined_task_frame(int64_t size) {
    void *p = calloc(1, (size_t)(size > 0 ? size : 1));
    if (!p) trap_text("out of memory for a task");
    return p;
}

/* A task runs to its end when it is started, so `cancel` has nothing left to stop. A group keeps the first
   error one of its tasks reports (D-48) until its `join` reads it. As on its own thread under the JIT, a task
   starts with no recursion depth and its trap shows only its own operations. */
#define MAX_GROUPS 4096
static unsigned char *group_error_bytes[MAX_GROUPS];
static int64_t group_error_size[MAX_GROUPS];
static int64_t next_group = 0, current_group = 0;

int64_t refined_task_spawn(void *thunk, void *frame, int64_t group) {
    int64_t outer_group = current_group, outer_base = frame_base, *outer_depth = depth, outer_cap = depth_cap;
    current_group = group;
    frame_base = frame_count;
    depth = NULL;
    depth_cap = 0;
    task_depth++;
    ((void (*)(void *))thunk)(frame);
    task_depth--;
    free(depth);
    depth = outer_depth;
    depth_cap = outer_cap;
    frame_base = outer_base;
    current_group = outer_group;
    return 1;
}
void refined_task_fail(void *error, int64_t size) {
    if (current_group <= 0 || current_group >= MAX_GROUPS || group_error_bytes[current_group]) return;
    group_error_bytes[current_group] = malloc((size_t)size);
    if (!group_error_bytes[current_group]) trap_text("out of memory for a task group's error");
    memcpy(group_error_bytes[current_group], error, (size_t)size);
    group_error_size[current_group] = size;
}
int32_t refined_group_error(int64_t g, void *out, int64_t size) {
    if (g <= 0 || g >= MAX_GROUPS || !group_error_bytes[g]) return 0;
    memcpy(out, group_error_bytes[g], (size_t)(size < group_error_size[g] ? size : group_error_size[g]));
    free(group_error_bytes[g]);
    group_error_bytes[g] = NULL;
    return 1;
}
void refined_task_join(int64_t h) { (void)h; }
void refined_task_cancel(int64_t h) { (void)h; }
void refined_task_release(int64_t h) { (void)h; }
int64_t refined_group_new(int64_t limit) {
    (void)limit;
    if (++next_group >= MAX_GROUPS) trap_text("too many task groups");
    return next_group;
}
void refined_group_await(int64_t g) { (void)g; }
void refined_group_join(int64_t g) { (void)g; }
void refined_group_cancel(int64_t g) { (void)g; }
void refined_group_free(int64_t g) { (void)g; }

/* ================================================================ the native host library (D-80) */

/* Error variants are numbered from 1 in the order library.py declares them; tests/test_tooling.py checks every
   ERR_ constant here against library.py. */
#define ERR_fs_FileError_notFound 1
#define ERR_fs_FileError_denied 2
#define ERR_fs_FileError_exists 3
#define ERR_fs_FileError_tooLarge 4
#define ERR_fs_FileError_timedOut 5
#define ERR_fs_FileError_cancelled 6
#define ERR_fs_FileError_busy 7
#define ERR_fs_FileError_failed 8
#define ERR_fs_EntryIndexError_outOfRange 1
#define ERR_console_ReadError_endOfInput 1
#define ERR_console_ReadError_tooLong 2
#define ERR_console_ReadError_timedOut 3
#define ERR_console_ReadError_failed 5
#define ERR_environment_MissingError_missing 1
#define ERR_process_ArgumentError_outOfRange 1
#define ERR_process_RunError_notFound 1
#define ERR_process_RunError_timedOut 2
#define ERR_process_RunError_tooLarge 4
#define ERR_process_RunError_failed 5
#define ERR_string_Utf8Error_invalidAt 1
#define ERR_map_KeyMissing_missing 1
#define ERR_log_LogError_failed 1

/* ---------------------------------------------------------------- calls: slots in, slots out */

struct Call;
typedef int32_t (*HostFn)(struct Call *c);
typedef struct Target { const char *name; HostFn fn; int scoped; } Target;

#define MAX_PARAMS 24
typedef struct Shape {
    const char *key;
    int64_t key_len;
    const Target *target;
    int params, nres;
    int count[MAX_PARAMS], offset[MAX_PARAMS];
} Shape;

typedef struct Call {
    const Shape *s;
    int64_t *args, *res, *payload;
    int params;
} Call;

typedef struct Text { const char *p; int64_t n; } Text;

static int64_t *slot(Call *c, int i) { return c->args + c->s->offset[i]; }
static int64_t arg(Call *c, int i) { return slot(c, i)[0]; }
static int count(Call *c, int i) { return c->s->count[i]; }
static Text text_of(const int64_t *s) {
    Text t = {(const char *)(intptr_t)s[0], s[1]};
    return t;
}
static Text text_arg(Call *c, int i) { return text_of(slot(c, i)); }
static inline char *cstr(Text t) {
    char *s = malloc((size_t)t.n + 1);
    if (!s) trap_text("out of memory in the runtime");
    if (t.n) memcpy(s, t.p, (size_t)t.n);
    s[t.n] = 0;
    return s;
}
static int32_t fail(Call *c, int32_t status, int64_t payload) {
    *c->payload = payload;
    return status;
}
/* bytes copied into a region, given back as a (pointer, length) pair of result slots */
static void put(int64_t region, const void *data, int64_t n, int64_t *out) {
    void *p = refined_region_alloc((void *)(intptr_t)region, n);
    if (n) memcpy(p, data, (size_t)n);
    out[0] = (int64_t)(intptr_t)p;
    out[1] = n;
}

/* ---------------------------------------------------------------- handles */

/* As in host.py: handles are small integers into one table, so a handle used after it was closed, or after the
   region that owns it was released, is caught and traps naming its kind. */
enum { H_NONE, H_FILE, H_LISTING, H_BUFFER, H_MAP, H_SET, H_ARGUMENTS };
static const char *KIND_NAMES[] = {"", "File", "Listing", "Buffer", "Map", "Set", "Arguments"};
typedef struct Object { int kind; void *p; int64_t region; } Object;
static Object *objects;
static int64_t object_cap, next_handle = 1;

static int64_t new_handle(int kind, void *p, int64_t region) {
    int64_t h = next_handle++;
    objects = grow(objects, &object_cap, h + 1, sizeof(Object));
    objects[h].kind = kind;
    objects[h].p = p;
    objects[h].region = region;
    if (region) {
        Region *r = (Region *)(intptr_t)region;
        r->handles = grow(r->handles, &r->handle_cap, r->handle_count + 1, sizeof(int64_t));
        r->handles[r->handle_count++] = h;
    }
    return h;
}

/* D-107: the region a host value lives in, where text stored in it is copied */
void *refined_handle_region(int64_t h) {
    if (h < 1 || h >= next_handle || objects[h].kind == H_NONE || !objects[h].region)
        trap_text("a value was stored in a collection that is not in any region");
    return (void *)(intptr_t)objects[h].region;
}

static void *get_object(int64_t h, int kind) {
    if (h < 1 || h >= next_handle || objects[h].kind != kind) {
        char msg[160];
        snprintf(msg, sizeof msg, "a %s handle was used after it was closed or its region was released",
                 KIND_NAMES[kind]);
        trap_text(msg);
    }
    return objects[h].p;
}

/* ---------------------------------------------------------------- time */

static int64_t now_ms(void) {
#ifdef _WIN32
    return (int64_t)GetTickCount64();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
#endif
}

static int past(int64_t deadline) { return deadline != NEVER && deadline <= now_ms(); }

/* milliseconds left before a deadline, at most `cap` (NEVER: `cap`) */
static int64_t left_ms(int64_t deadline, int64_t cap) {
    if (deadline == NEVER) return cap;
    int64_t left = deadline - now_ms();
    if (left < 0) left = 0;
    return left < cap ? left : cap;
}

static void sleep_ms(int64_t ms) {
    if (ms <= 0) return;
#ifdef _WIN32
    while (ms > 0) {
        DWORD part = ms > 0x7FFFFFFF ? 0x7FFFFFFF : (DWORD)ms;
        Sleep(part);
        ms -= part;
    }
#else
    struct timespec ts = {(time_t)(ms / 1000), (long)(ms % 1000) * 1000000L}, rem;
    while (nanosleep(&ts, &rem) != 0 && errno == EINTR) ts = rem;
#endif
}

static int64_t duration(int64_t ms, const char *what) {
    if (ms < 0) {
        char msg[200];
        snprintf(msg, sizeof msg, "%s was given %lld milliseconds; a duration is zero or more", what, (long long)ms);
        trap_text(msg);
    }
    return ms;
}

static int32_t h_deadline_never(Call *c) {
    c->res[0] = NEVER;
    return 0;
}
static int32_t h_deadline_after(Call *c) {
    c->res[0] = (int64_t)((uint64_t)now_ms() + (uint64_t)duration(arg(c, 0), "`time.Deadline.after`"));
    return 0;
}
static int32_t h_sleep(Call *c) {
    sleep_ms(duration(arg(c, 0), "`time.sleep`"));
    return 0;
}
static int32_t h_clock_now(Call *c) {
#ifdef _WIN32
    FILETIME ft;
    GetSystemTimeAsFileTime(&ft);
    uint64_t t = ((uint64_t)ft.dwHighDateTime << 32) | ft.dwLowDateTime;  /* 100 ns since 1601 */
    c->res[0] = (int64_t)(t / 10000 - 11644473600000ULL);
#else
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    c->res[0] = (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
#endif
    return 0;
}
static int32_t h_clock_monotonic(Call *c) {
    c->res[0] = now_ms();
    return 0;
}

/* ---------------------------------------------------------------- operating-system errors */

/* An OS error as `fs.FileError`, as Python classifies it: no such file, permission, already exists, or the
   error number as `failed`. */
static int32_t file_error(Call *c, int err) {
    if (err == ENOENT) return fail(c, ERR_fs_FileError_notFound, 0);
    if (err == EACCES || err == EPERM) return fail(c, ERR_fs_FileError_denied, 0);
    if (err == EEXIST) return fail(c, ERR_fs_FileError_exists, 0);
    return fail(c, ERR_fs_FileError_failed, err ? err : 1);
}

#ifdef _WIN32
/* Python's winerror_to_errno for the errors file and directory calls report */
static int win_errno(DWORD e) {
    switch (e) {
    case ERROR_FILE_NOT_FOUND: case ERROR_PATH_NOT_FOUND: case ERROR_INVALID_DRIVE: case ERROR_NO_MORE_FILES:
    case ERROR_BAD_NETPATH: case ERROR_BAD_NET_NAME: case ERROR_BAD_PATHNAME: case ERROR_FILENAME_EXCED_RANGE:
    case ERROR_INVALID_NAME:
        return ENOENT;
    case ERROR_TOO_MANY_OPEN_FILES: return EMFILE;
    case ERROR_ACCESS_DENIED: case ERROR_CURRENT_DIRECTORY: case ERROR_WRITE_PROTECT: case ERROR_SHARING_VIOLATION:
    case ERROR_LOCK_VIOLATION: case ERROR_NETWORK_ACCESS_DENIED: case ERROR_CANNOT_MAKE:
        return EACCES;
    case ERROR_INVALID_HANDLE: return EBADF;
    case ERROR_NOT_SAME_DEVICE: return EXDEV;
    case ERROR_FILE_EXISTS: case ERROR_ALREADY_EXISTS: return EEXIST;
    case ERROR_DIR_NOT_EMPTY: return ENOTEMPTY;
    case ERROR_DIRECTORY: return ENOTDIR;
    case ERROR_DISK_FULL: case ERROR_HANDLE_DISK_FULL: return ENOSPC;
    case ERROR_BROKEN_PIPE: case ERROR_NO_DATA: return EPIPE;
    default: return EINVAL;
    }
}

static wchar_t *widen(Text t) {
    int m = t.n > 0 ? MultiByteToWideChar(CP_UTF8, 0, t.p, (int)t.n, NULL, 0) : 0;
    wchar_t *w = malloc(((size_t)m + 1) * sizeof(wchar_t));
    if (!w) trap_text("out of memory in the runtime");
    if (m) MultiByteToWideChar(CP_UTF8, 0, t.p, (int)t.n, w, m);
    w[m] = 0;
    return w;
}
static char *narrow(const wchar_t *w, int64_t *len) {
    int m = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
    char *s = malloc(m > 0 ? (size_t)m : 1);
    if (!s) trap_text("out of memory in the runtime");
    if (m > 0) WideCharToMultiByte(CP_UTF8, 0, w, -1, s, m, NULL, NULL);
    else s[0] = 0;
    if (len) *len = m > 0 ? m - 1 : 0;
    return s;
}
#endif

/* ---------------------------------------------------------------- paths: resolved as os.path.realpath does */

#ifdef _WIN32
#define SEP '\\'
static int is_sep(char ch) { return ch == '/' || ch == '\\'; }

/* the final path of something that exists, links and junctions followed; NULL when it cannot be opened */
static wchar_t *final_path(const wchar_t *p) {
    HANDLE h = CreateFileW(p, 0, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, OPEN_EXISTING,
                           FILE_FLAG_BACKUP_SEMANTICS, NULL);
    if (h == INVALID_HANDLE_VALUE) return NULL;
    DWORD n = GetFinalPathNameByHandleW(h, NULL, 0, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS);
    wchar_t *out = NULL;
    if (n) {
        out = malloc(((size_t)n + 1) * sizeof(wchar_t));
        if (out && !GetFinalPathNameByHandleW(h, out, n + 1, FILE_NAME_NORMALIZED | VOLUME_NAME_DOS)) {
            free(out);
            out = NULL;
        }
    }
    CloseHandle(h);
    if (out) {
        if (wcsncmp(out, L"\\\\?\\UNC\\", 8) == 0) {
            memmove(out + 2, out + 8, (wcslen(out + 8) + 1) * sizeof(wchar_t));
        } else if (wcsncmp(out, L"\\\\?\\", 4) == 0) {
            memmove(out, out + 4, (wcslen(out + 4) + 1) * sizeof(wchar_t));
        }
    }
    return out;
}

/* an absolute, normalized path with the longest existing prefix resolved and the rest kept as written */
static wchar_t *resolve_full(const wchar_t *full) {
    wchar_t *done = final_path(full);
    if (done) return done;
    size_t n = wcslen(full);
    size_t i = n;
    while (i > 0 && full[i - 1] != L'\\') i--;
    if (i == 0 || i == n) return _wcsdup(full);
    size_t head_len = i - 1;
    if (head_len == 0 || (head_len == 2 && full[1] == L':')) head_len++;  /* keep the root's separator */
    wchar_t *head = malloc((head_len + 1) * sizeof(wchar_t));
    memcpy(head, full, head_len * sizeof(wchar_t));
    head[head_len] = 0;
    if (wcscmp(head, full) == 0) {
        free(head);
        return _wcsdup(full);
    }
    wchar_t *base = resolve_full(head);
    free(head);
    size_t bn = wcslen(base), tn = n - i;
    wchar_t *out = malloc((bn + tn + 2) * sizeof(wchar_t));
    memcpy(out, base, bn * sizeof(wchar_t));
    size_t at = bn;
    if (at == 0 || out[at - 1] != L'\\') out[at++] = L'\\';
    memcpy(out + at, full + i, tn * sizeof(wchar_t));
    out[at + tn] = 0;
    free(base);
    return out;
}

/* normcase(realpath(path)) as UTF-8 */
static char *resolve(Text path) {
    wchar_t *w = widen(path.n ? path : (Text){".", 1});
    DWORD n = GetFullPathNameW(w, 0, NULL, NULL);
    wchar_t *full = malloc(((size_t)n + 2) * sizeof(wchar_t));
    if (!n || !GetFullPathNameW(w, n + 1, full, NULL)) wcscpy(full, w);
    free(w);
    wchar_t *real = resolve_full(full);
    free(full);
    CharLowerBuffW(real, (DWORD)wcslen(real));
    for (wchar_t *q = real; *q; q++)
        if (*q == L'/') *q = L'\\';
    char *out = narrow(real, NULL);
    free(real);
    return out;
}
static char *normcase(Text t) {
    wchar_t *w = widen(t);
    CharLowerBuffW(w, (DWORD)wcslen(w));
    for (wchar_t *q = w; *q; q++)
        if (*q == L'/') *q = L'\\';
    char *out = narrow(w, NULL);
    free(w);
    return out;
}
#else
#define SEP '/'
static int is_sep(char ch) { return ch == '/'; }

static char *join2(const char *a, const char *b, size_t bn) {
    size_t an = strlen(a);
    char *out = malloc(an + bn + 2);
    if (!out) trap_text("out of memory in the runtime");
    memcpy(out, a, an);
    size_t at = an;
    if (at == 0 || out[at - 1] != '/') out[at++] = '/';
    memcpy(out + at, b, bn);
    out[at + bn] = 0;
    return out;
}
static void parent_in_place(char *p) {
    char *last = strrchr(p, '/');
    if (!last || last == p) strcpy(p, "/");
    else *last = 0;
}

/* posixpath.realpath (not strict): each part in turn, links followed, `..` applied to what is resolved so far,
   parts that do not exist kept as written */
static char *join_real(char *path, const char *rest, int hops) {
    const char *at = rest;
    while (*at) {
        const char *end = strchr(at, '/');
        size_t n = end ? (size_t)(end - at) : strlen(at);
        const char *next = end ? end + 1 : at + n;
        if (n == 0 || (n == 1 && at[0] == '.')) { at = next; continue; }
        if (n == 2 && at[0] == '.' && at[1] == '.') {
            parent_in_place(path);
            at = next;
            continue;
        }
        char *candidate = join2(path, at, n);
        struct stat st;
        if (hops < 40 && lstat(candidate, &st) == 0 && S_ISLNK(st.st_mode)) {
            char target[4096];
            ssize_t len = readlink(candidate, target, sizeof target - 1);
            if (len > 0) {
                target[len] = 0;
                free(candidate);
                if (target[0] == '/') strcpy(path, "/");
                path = join_real(path, target, hops + 1);
                at = next;
                continue;
            }
        }
        free(path);
        path = candidate;
        at = next;
    }
    return path;
}

static char *resolve(Text path) {
    char *p = cstr(path.n ? path : (Text){".", 1});
    char *start;
    if (p[0] == '/') {
        start = malloc(4096 + 2);
        strcpy(start, "/");
    } else {
        start = malloc(4096 + 2);
        if (!getcwd(start, 4096)) strcpy(start, "/");
    }
    /* `start` grows with each joined part, so the result is reallocated by join_real */
    char *out = join_real(start, p, 0);
    free(p);
    return out;
}
static char *normcase(Text t) { return cstr(t); }
#endif

static int starts_with(const char *s, const char *prefix) { return strncmp(s, prefix, strlen(prefix)) == 0; }

/* `base.rstrip(os.sep) + os.sep` */
static char *as_prefix(const char *base) {
    size_t n = strlen(base);
    while (n > 0 && base[n - 1] == SEP) n--;
    char *out = malloc(n + 2);
    memcpy(out, base, n);
    out[n] = SEP;
    out[n + 1] = 0;
    return out;
}

/* library.path_within with resolve=True: a directory scope (`data/`) or a name pattern (`suite-*`) */
static int path_within(Text path, Text scope) {
    if (scope.n == 0 || (scope.p[scope.n - 1] != '/' && scope.p[scope.n - 1] != '*')) return 0;
    char *real = resolve(path);
    int ok;
    Text body = {scope.p, scope.n - 1};
    if (scope.p[scope.n - 1] == '/') {
        char *base = resolve(body.n ? body : (Text){".", 1});
        char *prefix = as_prefix(base);
        ok = strcmp(real, base) == 0 || starts_with(real, prefix);
        free(base);
        free(prefix);
    } else {
        int64_t i = body.n;
        while (i > 0 && !is_sep(body.p[i - 1])) i--;
        int64_t head_n = i;
        while (head_n > 1 && is_sep(body.p[head_n - 1])) head_n--;  /* os.path.split strips the head's separators */
        Text head = {body.p, head_n}, tail = {body.p + i, body.n - i};
        char *base = resolve(head.n ? head : (Text){".", 1});
        char *prefix = as_prefix(base);
        if (!starts_with(real, prefix)) {
            ok = 0;
        } else {
            const char *first = real + strlen(prefix);
            const char *end = strchr(first, SEP);
            size_t fn = end ? (size_t)(end - first) : strlen(first);
            char *want = normcase(tail);
            ok = strlen(want) <= fn && strncmp(first, want, strlen(want)) == 0;
            free(want);
        }
        free(base);
        free(prefix);
    }
    free(real);
    return ok;
}

/* ---------------------------------------------------------------- capability scopes at run time (D-38) */

static const char *SCOPED_RESOURCES[] = {"net.tcp", "net.outbound", "fs.files", "process.programs", "ffi.libraries",
                                         "ffi.symbols"};

static int scoped_resource(const char *p, int64_t n) {
    for (int i = 0; i < 6; i++)
        if ((int64_t)strlen(SCOPED_RESOURCES[i]) == n && memcmp(SCOPED_RESOURCES[i], p, (size_t)n) == 0) return i;
    return -1;
}

/* Python's repr of a str, for the scopes a trap lists */
static void repr_into(char **out, int64_t *len, int64_t *cap, Text t) {
    int has_single = memchr(t.p, '\'', (size_t)t.n) != NULL, has_double = memchr(t.p, '"', (size_t)t.n) != NULL;
    char quote = has_single && !has_double ? '"' : '\'';
    *out = grow(*out, cap, *len + t.n * 4 + 3, 1);
    (*out)[(*len)++] = quote;
    for (int64_t i = 0; i < t.n; i++) {
        unsigned char ch = (unsigned char)t.p[i];
        char *o = *out + *len;
        if (ch == '\\' || ch == (unsigned char)quote) { o[0] = '\\'; o[1] = (char)ch; *len += 2; }
        else if (ch == '\n') { memcpy(o, "\\n", 2); *len += 2; }
        else if (ch == '\r') { memcpy(o, "\\r", 2); *len += 2; }
        else if (ch == '\t') { memcpy(o, "\\t", 2); *len += 2; }
        else if (ch < 0x20 || ch == 0x7F) { snprintf(o, 5, "\\x%02x", ch); *len += 4; }
        else { o[0] = (char)ch; *len += 1; }
    }
    (*out)[(*len)++] = quote;
}

/* host._check_scope: the scoped argument must fall inside a scope of a capability the operation uses for the
   call's effect; the lines are `<verb> <resource>` headers, each followed by that resource's scopes */
static void check_scope(const char *target, Text value, Text scope_text) {
    int allowed = 0, resource = -1;
    char *listed = NULL;
    int64_t listed_len = 0, listed_cap = 0;
    int64_t at = 0;
    for (;;) {
        const char *nl = memchr(scope_text.p + at, '\n', (size_t)(scope_text.n - at));
        int64_t end = nl ? (int64_t)(nl - scope_text.p) : scope_text.n;
        Text line = {scope_text.p + at, end - at};
        const char *space = memchr(line.p, ' ', (size_t)line.n);
        int header = space ? scoped_resource(space + 1, line.n - (int64_t)(space + 1 - line.p)) : -1;
        if (header >= 0) {
            resource = header;
        } else {
            const char *name = resource >= 0 ? SCOPED_RESOURCES[resource] : "";
            if (strcmp(name, "process.programs") == 0 || strcmp(name, "ffi.libraries") == 0 ||
                strcmp(name, "ffi.symbols") == 0)
                allowed = allowed || refined_bytes_equal(value.p, value.n, line.p, line.n);
            else if (strcmp(name, "fs.files") == 0)
                allowed = allowed || path_within(value, line);
            if (listed_len) {
                listed = grow(listed, &listed_cap, listed_len + 2, 1);
                listed[listed_len++] = ',';
                listed[listed_len++] = ' ';
            }
            repr_into(&listed, &listed_len, &listed_cap, line);
        }
        if (!nl) break;
        at = end + 1;
    }
    if (allowed) {
        free(listed);
        return;
    }
    int64_t n = 200 + value.n + listed_len + (int64_t)strlen(target);
    char *msg = malloc((size_t)n);
    int64_t m = snprintf(msg, (size_t)n, "`%s` was given `%.*s`, which no capability this operation uses allows "
                         "(scopes: %.*s)", target, (int)value.n, value.p, (int)(listed_len ? listed_len : 4),
                         listed_len ? listed : "none");
    refined_trap(msg, m < n ? m : n - 1);
}

/* ---------------------------------------------------------------- files (D-52: one writer per file) */

typedef struct File {
    int fd;
    char *key;
    int writes, readable, writable;
} File;

typedef struct Claim { char *key; int64_t readers, writers; } Claim;
static Claim *claims;
static int64_t claim_count, claim_cap;

static int64_t find_claim(const char *key) {
    for (int64_t i = 0; i < claim_count; i++)
        if (strcmp(claims[i].key, key) == 0) return i;
    return -1;
}

/* the key of a path for D-52; 0 and the key, or `busy` */
static int32_t claim(Call *c, Text path, int writes, char **key_out) {
    char *key = resolve(path);
    int64_t i = find_claim(key);
    if (i >= 0 && (writes || claims[i].writers)) {
        free(key);
        return fail(c, ERR_fs_FileError_busy, 0);
    }
    if (i < 0) {
        claims = grow(claims, &claim_cap, claim_count + 1, sizeof(Claim));
        i = claim_count++;
        claims[i].key = strdup(key);
        claims[i].readers = claims[i].writers = 0;
    }
    if (writes) claims[i].writers++;
    else claims[i].readers++;
    *key_out = key;
    return 0;
}

static void unclaim(const char *key, int writes) {
    int64_t i = find_claim(key);
    if (i < 0) return;
    if (writes) claims[i].writers--;
    else claims[i].readers--;
    if (claims[i].readers + claims[i].writers <= 0) {
        free(claims[i].key);
        claims[i] = claims[--claim_count];
    }
}

static int open_path(Text path, int flags) {
#ifdef _WIN32
    wchar_t *w = widen(path);
    int fd = _wopen(w, flags | _O_BINARY | _O_NOINHERIT, _S_IREAD | _S_IWRITE);
    free(w);
    return fd;
#else
    char *p = cstr(path);
    int fd = open(p, flags | O_CLOEXEC, 0666);
    free(p);
    return fd;
#endif
}

static int is_regular_file(Text path) {
#ifdef _WIN32
    wchar_t *w = widen(path);
    DWORD a = GetFileAttributesW(w);
    free(w);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
#else
    char *p = cstr(path);
    struct stat st;
    int ok = stat(p, &st) == 0 && S_ISREG(st.st_mode);
    free(p);
    return ok;
#endif
}

static int64_t raw_read(int fd, void *buf, int64_t n) {
#ifdef _WIN32
    return _read(fd, buf, (unsigned)(n > 0x40000000 ? 0x40000000 : n));
#else
    return read(fd, buf, (size_t)(n > 0x40000000 ? 0x40000000 : n));
#endif
}

static int64_t raw_write(int fd, const void *buf, int64_t n) {
#ifdef _WIN32
    return _write(fd, buf, (unsigned)(n > 0x40000000 ? 0x40000000 : n));
#else
    return write(fd, buf, (size_t)(n > 0x40000000 ? 0x40000000 : n));
#endif
}

static int raw_close(int fd) {
#ifdef _WIN32
    return _close(fd);
#else
    return close(fd);
#endif
}

/* read up to `limit` bytes (as a buffered read does: until `limit` or the end); -1 and errno on an error */
static int64_t read_upto(int fd, int64_t limit, unsigned char **out) {
    int64_t len = 0, cap = 0;
    unsigned char *data = NULL;
    while (len < limit) {
        int64_t want = limit - len < 65536 ? limit - len : 65536;
        data = grow(data, &cap, len + want, 1);
        int64_t got = raw_read(fd, data + len, want);
        if (got < 0) {
            if (errno == EINTR) continue;
            int e = errno;
            free(data);
            errno = e;
            return -1;
        }
        if (got == 0) break;
        len += got;
    }
    *out = data;
    return len;
}

static int write_all(int fd, const char *p, int64_t n) {
    while (n > 0) {
        int64_t done = raw_write(fd, p, n);
        if (done < 0) {
            if (errno == EINTR) continue;
            return errno ? errno : 1;
        }
        p += done;
        n -= done;
    }
    return 0;
}

enum { OPEN_READ, OPEN_WRITE, OPEN_CREATE, OPEN_APPEND };

static int32_t open_file(Call *c, int how) {
    Text path = text_arg(c, 0);
    int writes = how != OPEN_READ;
    char *key;
    int32_t busy = claim(c, path, writes, &key);
    if (busy) return busy;
    int flags, err = 0, fd = -1;
#ifdef _WIN32
    const int RD = _O_RDONLY, RW = _O_RDWR, WR = _O_WRONLY, CR = _O_CREAT, EX = _O_EXCL, AP = _O_APPEND;
#else
    const int RD = O_RDONLY, RW = O_RDWR, WR = O_WRONLY, CR = O_CREAT, EX = O_EXCL, AP = O_APPEND;
#endif
    switch (how) {
    case OPEN_READ: flags = RD; break;
    case OPEN_WRITE: flags = RW; break;  /* an existing file, emptied */
    case OPEN_CREATE: flags = WR | CR | EX; break;
    default: flags = WR | CR | AP; break;
    }
    if (how == OPEN_WRITE && !is_regular_file(path)) {
        err = ENOENT;
    } else {
        fd = open_path(path, flags);
        if (fd < 0) err = errno;
#ifdef _WIN32
        else if (how == OPEN_WRITE && _chsize_s(fd, 0) != 0) err = errno;
#else
        else if (how == OPEN_WRITE && ftruncate(fd, 0) != 0) err = errno;
#endif
    }
    if (err) {
        if (fd >= 0) raw_close(fd);
        unclaim(key, writes);
        free(key);
        return file_error(c, err);
    }
    File *f = calloc(1, sizeof(File));
    f->fd = fd;
    f->key = key;
    f->writes = writes;
    f->readable = how == OPEN_READ || how == OPEN_WRITE;
    f->writable = how != OPEN_READ;
    c->res[0] = new_handle(H_FILE, f, 0);
    return 0;
}

static int32_t h_fs_open_read(Call *c) { return open_file(c, OPEN_READ); }
static int32_t h_fs_open_write(Call *c) { return open_file(c, OPEN_WRITE); }
static int32_t h_fs_create(Call *c) { return open_file(c, OPEN_CREATE); }
static int32_t h_fs_open_append(Call *c) { return open_file(c, OPEN_APPEND); }

static int32_t h_fs_read(Call *c) {
    File *f = get_object(arg(c, 0), H_FILE);
    if (!f->readable) return fail(c, ERR_fs_FileError_failed, 1);  /* Python: "not readable", no errno */
    int64_t limit = arg(c, 2) > 0 ? arg(c, 2) : 0;
    unsigned char *data = NULL;
    int64_t n = read_upto(f->fd, limit, &data);
    if (n < 0) return file_error(c, errno);
    put(arg(c, 1), data, n, c->res);
    free(data);
    return 0;
}

static int32_t h_fs_write(Call *c) {
    File *f = get_object(arg(c, 0), H_FILE);
    if (!f->writable) return fail(c, ERR_fs_FileError_failed, 1);  /* Python: "not writable", no errno */
    Text data = text_arg(c, 1);
    int err = write_all(f->fd, data.p, data.n);
    return err ? file_error(c, err) : 0;
}

static int32_t h_fs_close(Call *c) {
    int64_t h = arg(c, 0);
    File *f = get_object(h, H_FILE);
    int fd = f->fd;
    unclaim(f->key, f->writes);
    free(f->key);
    free(f);
    objects[h].kind = H_NONE;
    objects[h].p = NULL;
    return raw_close(fd) != 0 ? file_error(c, errno) : 0;
}

static int32_t h_fs_exists(Call *c) {
    Text path = text_arg(c, 0);
#ifdef _WIN32
    wchar_t *w = widen(path);
    struct _stat64 st;
    c->res[0] = path.n > 0 && _wstat64(w, &st) == 0;
    free(w);
#else
    char *p = cstr(path);
    struct stat st;
    c->res[0] = stat(p, &st) == 0;
    free(p);
#endif
    return 0;
}

static int32_t h_fs_remove(Call *c) {
    Text path = text_arg(c, 0);
    char *key = resolve(path);
    int64_t held = find_claim(key);
    free(key);
    if (held >= 0) return fail(c, ERR_fs_FileError_busy, 0);
#ifdef _WIN32
    wchar_t *w = widen(path);
    BOOL ok = DeleteFileW(w);
    DWORD e = GetLastError();
    free(w);
    return ok ? 0 : file_error(c, win_errno(e));
#else
    char *p = cstr(path);
    int r = unlink(p), e = errno;
    free(p);
    return r == 0 ? 0 : file_error(c, e);
#endif
}

static int32_t h_fs_create_directory(Call *c) {
#ifdef _WIN32
    wchar_t *w = widen(text_arg(c, 0));
    BOOL ok = CreateDirectoryW(w, NULL);
    DWORD e = GetLastError();
    free(w);
    return ok ? 0 : file_error(c, win_errno(e));
#else
    char *p = cstr(text_arg(c, 0));
    int r = mkdir(p, 0777), e = errno;
    free(p);
    return r == 0 ? 0 : file_error(c, e);
#endif
}

static int32_t h_fs_remove_directory(Call *c) {
#ifdef _WIN32
    wchar_t *w = widen(text_arg(c, 0));
    BOOL ok = RemoveDirectoryW(w);
    DWORD e = GetLastError();
    free(w);
    return ok ? 0 : file_error(c, win_errno(e));
#else
    char *p = cstr(text_arg(c, 0));
    int r = rmdir(p), e = errno;
    free(p);
    return r == 0 ? 0 : file_error(c, e);
#endif
}

/* a local file read or write does not block for long: the deadline is checked before it starts */
static int32_t file_wait_check(Call *c, int64_t deadline) {
    return past(deadline) ? fail(c, ERR_fs_FileError_timedOut, 0) : 0;
}

static int32_t h_fs_read_all(Call *c) {
    Text path = text_arg(c, 0);
    int64_t region = arg(c, 1), limit = arg(c, 2);
    int32_t late = file_wait_check(c, arg(c, 3));
    if (late) return late;
    char *key;
    int32_t busy = claim(c, path, 0, &key);
    if (busy) return busy;
#ifdef _WIN32
    int fd = open_path(path, _O_RDONLY);
#else
    int fd = open_path(path, O_RDONLY);
#endif
    int err = fd < 0 ? errno : 0;
    unsigned char *data = NULL;
    int64_t n = 0;
    if (!err) {
        n = read_upto(fd, limit < 0 ? 0 : (limit == INT64_MAX ? limit : limit + 1), &data);
        if (n < 0) err = errno;
        raw_close(fd);
    }
    unclaim(key, 0);
    free(key);
    if (err) return file_error(c, err);
    if (n > limit) {
        free(data);
        return fail(c, ERR_fs_FileError_tooLarge, 0);
    }
    put(region, data, n, c->res);
    free(data);
    return 0;
}

static int32_t h_fs_write_all(Call *c) {
    Text path = text_arg(c, 0), data = text_arg(c, 1);
    int32_t late = file_wait_check(c, arg(c, 2));
    if (late) return late;
    char *key;
    int32_t busy = claim(c, path, 1, &key);
    if (busy) return busy;
#ifdef _WIN32
    int fd = open_path(path, _O_WRONLY | _O_CREAT | _O_TRUNC);
#else
    int fd = open_path(path, O_WRONLY | O_CREAT | O_TRUNC);
#endif
    int err = fd < 0 ? errno : 0;
    if (!err) {
        err = write_all(fd, data.p, data.n);
        if (raw_close(fd) != 0 && !err) err = errno;
    }
    unclaim(key, 1);
    free(key);
    return err ? file_error(c, err) : 0;
}

/* an exclusive advisory lock: tried every 50 ms until the deadline, as the JIT does */
static int lock_once(File *f, int lock, int *err) {
#ifdef _WIN32
    int64_t pos = _lseeki64(f->fd, 0, SEEK_CUR);
    _lseeki64(f->fd, 0, SEEK_SET);
    int r = _locking(f->fd, lock ? _LK_NBLCK : _LK_UNLCK, 1);
    *err = errno;
    _lseeki64(f->fd, pos, SEEK_SET);
    return r;
#else
    int r = flock(f->fd, lock ? LOCK_EX | LOCK_NB : LOCK_UN);
    *err = errno;
    return r;
#endif
}

static int32_t h_fs_lock(Call *c) {
    File *f = get_object(arg(c, 0), H_FILE);
    int64_t deadline = arg(c, 1);
    for (;;) {
        int err;
        if (lock_once(f, 1, &err) == 0) return 0;
        int held = err == EAGAIN || err == EACCES || err == EWOULDBLOCK;  /* someone else holds it */
#ifdef EDEADLOCK
        held = held || err == EDEADLOCK;
#endif
        if (!held) return file_error(c, err);
        if (past(deadline)) return fail(c, ERR_fs_FileError_timedOut, 0);
        sleep_ms(left_ms(deadline, 50));
    }
}

static int32_t h_fs_unlock(Call *c) {
    File *f = get_object(arg(c, 0), H_FILE);
    int err;
    return lock_once(f, 0, &err) == 0 ? 0 : file_error(c, err);
}

/* ---------------------------------------------------------------- directory listings */

typedef struct Names { Text *items; int64_t count, cap; } Names;

static void names_add(Names *ns, const char *p, int64_t n) {
    ns->items = grow(ns->items, &ns->cap, ns->count + 1, sizeof(Text));
    char *copy = malloc(n > 0 ? (size_t)n : 1);
    if (n) memcpy(copy, p, (size_t)n);
    ns->items[ns->count].p = copy;
    ns->items[ns->count].n = n;
    ns->count++;
}

static void names_free(Names *ns) {
    for (int64_t i = 0; i < ns->count; i++) free((void *)ns->items[i].p);
    free(ns->items);
    free(ns);
}

static int compare_names(const void *a, const void *b) {
    const Text *x = a, *y = b;
    int64_t n = x->n < y->n ? x->n : y->n;
    int r = n ? memcmp(x->p, y->p, (size_t)n) : 0;
    return r ? r : (x->n < y->n ? -1 : x->n > y->n);
}

static int32_t h_fs_list_directory(Call *c) {
    Text path = text_arg(c, 0);
    Names *ns = calloc(1, sizeof(Names));
#ifdef _WIN32
    Text pattern_text = path;
    char *joined = malloc((size_t)path.n + 5);
    memcpy(joined, path.p, (size_t)path.n);
    int64_t n = path.n;
    if (n && !is_sep(joined[n - 1]) && joined[n - 1] != ':') joined[n++] = '\\';
    memcpy(joined + n, "*.*", 3);
    pattern_text.p = joined;
    pattern_text.n = n + 3;
    wchar_t *w = widen(pattern_text);
    free(joined);
    WIN32_FIND_DATAW found;
    HANDLE h = FindFirstFileW(w, &found);
    free(w);
    if (h == INVALID_HANDLE_VALUE) {
        DWORD e = GetLastError();
        names_free(ns);
        if (e != ERROR_FILE_NOT_FOUND) return file_error(c, win_errno(e));
        return file_error(c, ENOENT);
    }
    do {
        if (wcscmp(found.cFileName, L".") == 0 || wcscmp(found.cFileName, L"..") == 0) continue;
        int64_t len;
        char *name = narrow(found.cFileName, &len);
        names_add(ns, name, len);
        free(name);
    } while (FindNextFileW(h, &found));
    FindClose(h);
#else
    char *p = cstr(path.n ? path : (Text){"", 0});
    DIR *d = opendir(p);
    int e = errno;
    free(p);
    if (!d) {
        names_free(ns);
        return file_error(c, e);
    }
    struct dirent *ent;
    while ((ent = readdir(d)) != NULL) {
        if (strcmp(ent->d_name, ".") == 0 || strcmp(ent->d_name, "..") == 0) continue;
        names_add(ns, ent->d_name, (int64_t)strlen(ent->d_name));
    }
    closedir(d);
#endif
    if (ns->count) qsort(ns->items, (size_t)ns->count, sizeof(Text), compare_names);
    c->res[0] = new_handle(H_LISTING, ns, arg(c, 1));
    return 0;
}

static int32_t h_fs_entry_count(Call *c) {
    Names *ns = get_object(arg(c, 0), H_LISTING);
    c->res[0] = ns->count;
    return 0;
}

static int32_t h_fs_entry_name(Call *c) {
    Names *ns = get_object(arg(c, 0), H_LISTING);
    int64_t i = arg(c, 1);
    if (i < 0 || i >= ns->count) return fail(c, ERR_fs_EntryIndexError_outOfRange, i);
    put(arg(c, 2), ns->items[i].p, ns->items[i].n, c->res);
    return 0;
}

/* ---------------------------------------------------------------- arguments, environment, standard input */

static Names program_arguments;  /* the words after the program's name on its command line */

void refined_start(int argc, char **argv) {
#ifdef _WIN32
    /* the JIT's streams are binary (Python sets them so): a line ends with one `\n` byte */
    _setmode(0, _O_BINARY);
    _setmode(1, _O_BINARY);
    _setmode(2, _O_BINARY);
    int wn = 0;
    LPWSTR *wv = CommandLineToArgvW(GetCommandLineW(), &wn);
    if (wv) {
        for (int i = 1; i < wn; i++) {
            int64_t len;
            char *s = narrow(wv[i], &len);
            names_add(&program_arguments, s, len);
            free(s);
        }
        LocalFree(wv);
        return;
    }
#else
    signal(SIGPIPE, SIG_IGN);  /* as in Python: a closed pipe is a write error, not the end of the process */
#endif
    for (int i = 1; i < argc; i++) names_add(&program_arguments, argv[i], (int64_t)strlen(argv[i]));
}

static int32_t h_argument_count(Call *c) {
    c->res[0] = program_arguments.count;
    return 0;
}

static int32_t h_argument(Call *c) {
    int64_t i = arg(c, 0);
    if (i < 0 || i >= program_arguments.count) return fail(c, ERR_process_ArgumentError_outOfRange, i);
    put(arg(c, 1), program_arguments.items[i].p, program_arguments.items[i].n, c->res);
    return 0;
}

static int32_t h_environment_get(Call *c) {
    Text name = text_arg(c, 0);
    if (name.n == 0 || memchr(name.p, '=', (size_t)name.n) || memchr(name.p, 0, (size_t)name.n))
        return fail(c, ERR_environment_MissingError_missing, 0);
#ifdef _WIN32
    wchar_t *w = widen(name);
    const wchar_t *v = _wgetenv(w);
    free(w);
    if (!v) return fail(c, ERR_environment_MissingError_missing, 0);
    int64_t len;
    char *s = narrow(v, &len);
    put(arg(c, 1), s, len, c->res);
    free(s);
#else
    char *n = cstr(name);
    const char *v = getenv(n);
    free(n);
    if (!v) return fail(c, ERR_environment_MissingError_missing, 0);
    put(arg(c, 1), v, (int64_t)strlen(v), c->res);
#endif
    return 0;
}

static unsigned char *stdin_data;
static int64_t stdin_len, stdin_cap;
static int stdin_done;

/* wait until standard input has something to read (or has ended); 0 when it may be read, 1 at the deadline */
static int stdin_wait(int64_t deadline) {
    if (deadline == NEVER) return 0;
#ifdef _WIN32
    HANDLE h = GetStdHandle(STD_INPUT_HANDLE);
    DWORD type = GetFileType(h);
    for (;;) {
        if (type == FILE_TYPE_PIPE) {
            DWORD avail = 0;
            if (!PeekNamedPipe(h, NULL, 0, NULL, &avail, NULL) || avail > 0) return 0;
        } else if (type == FILE_TYPE_CHAR) {
            if (WaitForSingleObject(h, (DWORD)left_ms(deadline, 50)) == WAIT_OBJECT_0) return 0;
        } else {
            return 0;
        }
        if (past(deadline)) return 1;
        if (type == FILE_TYPE_PIPE) sleep_ms(left_ms(deadline, 10));
    }
#else
    for (;;) {
        struct pollfd pfd = {0, POLLIN, 0};
        int r = poll(&pfd, 1, (int)left_ms(deadline, 1000));
        if (r > 0) return 0;
        if (r < 0 && errno != EINTR) return 0;
        if (past(deadline)) return 1;
    }
#endif
}

static int stdin_fill(void) {
    stdin_data = grow(stdin_data, &stdin_cap, stdin_len + 65536, 1);
#ifdef _WIN32
    DWORD got = 0;
    if (!ReadFile(GetStdHandle(STD_INPUT_HANDLE), stdin_data + stdin_len, 65536, &got, NULL)) {
        DWORD e = GetLastError();
        if (e == ERROR_BROKEN_PIPE || e == ERROR_HANDLE_EOF) got = 0;
        else return win_errno(e);
    }
#else
    ssize_t got;
    do got = read(0, stdin_data + stdin_len, 65536);
    while (got < 0 && errno == EINTR);
    if (got < 0) return errno ? errno : 1;
#endif
    if (got == 0) stdin_done = 1;
    stdin_len += (int64_t)got;
    return 0;
}

static int32_t h_read_line(Call *c) {
    int64_t region = arg(c, 0), limit = arg(c, 1), deadline = arg(c, 2);
    unsigned char *nl;
    while (!(nl = stdin_len ? memchr(stdin_data, '\n', (size_t)stdin_len) : NULL) && !stdin_done) {
        if (stdin_wait(deadline)) return fail(c, ERR_console_ReadError_timedOut, 0);
        int err = stdin_fill();
        if (err) return fail(c, ERR_console_ReadError_failed, err);
    }
    int64_t take = nl ? (int64_t)(nl - stdin_data) + 1 : stdin_len;
    if (take == 0) return fail(c, ERR_console_ReadError_endOfInput, 0);
    int64_t n = take;
    if (n > 0 && stdin_data[n - 1] == '\n') n--;
    if (n > 0 && stdin_data[n - 1] == '\r') n--;
    int32_t status = 0;
    if (n > limit) status = fail(c, ERR_console_ReadError_tooLong, 0);
    else put(region, stdin_data, n, c->res);
    memmove(stdin_data, stdin_data + take, (size_t)(stdin_len - take));
    stdin_len -= take;
    return status;
}

/* ---------------------------------------------------------------- child processes */

static int32_t h_new_arguments(Call *c) {
    c->res[0] = new_handle(H_ARGUMENTS, calloc(1, sizeof(Names)), arg(c, 0));
    return 0;
}

static int32_t h_add_argument(Call *c) {
    Names *ns = get_object(arg(c, 0), H_ARGUMENTS);
    Text t = text_arg(c, 1);
    names_add(ns, t.p, t.n);
    return 0;
}

typedef struct Captured { unsigned char *data; int64_t len, cap; } Captured;

#ifdef _WIN32
/* one pipe of a captured child: write `src` to it and close it, or read it to its end into `into` */
typedef struct Pump { HANDLE h; Captured *into; const char *src; int64_t n; } Pump;

static DWORD WINAPI pump(LPVOID p) {
    Pump *job = p;
    if (job->into == NULL) {
        int64_t at = 0;
        while (at < job->n) {
            DWORD done = 0, want = job->n - at > 65536 ? 65536 : (DWORD)(job->n - at);
            if (!WriteFile(job->h, job->src + at, want, &done, NULL)) break;
            at += done;
        }
        CloseHandle(job->h);
        return 0;
    }
    for (;;) {
        Captured *into = job->into;
        if (into->cap - into->len < 65536) {
            int64_t cap = into->cap ? into->cap * 2 : 65536;
            while (cap - into->len < 65536) cap *= 2;
            unsigned char *q = realloc(into->data, (size_t)cap);
            if (!q) return 1;
            into->data = q;
            into->cap = cap;
        }
        DWORD got = 0;
        if (!ReadFile(job->h, into->data + into->len, 65536, &got, NULL) || got == 0) break;
        into->len += got;
    }
    return 0;
}
#endif

/* run a child to its end, or stop it at the deadline; with `input` its three streams are pipes */
static int32_t run_child(Call *c, Text program, Names *args, int64_t deadline, const Text *input, Captured *out,
                         Captured *err, int64_t *status) {
    fflush(stdout);
    fflush(stderr);
#ifdef _WIN32
    /* subprocess.list2cmdline */
    char *line = NULL;
    int64_t len = 0, cap = 0;
    for (int64_t i = -1; i < args->count; i++) {
        Text a = i < 0 ? program : args->items[i];
        line = grow(line, &cap, len + a.n * 2 + 4, 1);
        if (i >= 0) line[len++] = ' ';
        int quote = a.n == 0 || memchr(a.p, ' ', (size_t)a.n) || memchr(a.p, '\t', (size_t)a.n);
        if (quote) line[len++] = '"';
        int64_t slashes = 0;
        for (int64_t k = 0; k < a.n; k++) {
            char ch = a.p[k];
            if (ch == '\\') {
                slashes++;
            } else if (ch == '"') {
                line = grow(line, &cap, len + slashes * 2 + 2 + (a.n - k) * 2 + 4, 1);
                for (int64_t s = 0; s < slashes * 2; s++) line[len++] = '\\';
                slashes = 0;
                line[len++] = '\\';
                line[len++] = '"';
            } else {
                for (; slashes > 0; slashes--) line[len++] = '\\';
                line[len++] = ch;
            }
        }
        int64_t tail = quote ? slashes * 2 : slashes;
        line = grow(line, &cap, len + tail + 4, 1);
        for (int64_t s = 0; s < tail; s++) line[len++] = '\\';
        if (quote) line[len++] = '"';
    }
    Text whole = {line ? line : "", len};
    wchar_t *wline = widen(whole);
    free(line);
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    memset(&si, 0, sizeof si);
    si.cb = sizeof si;
    si.dwFlags = STARTF_USESTDHANDLES;
    SECURITY_ATTRIBUTES sa = {sizeof sa, NULL, TRUE};
    HANDLE ours[3] = {NULL, NULL, NULL}, theirs[3] = {NULL, NULL, NULL};
    HANDLE me = GetCurrentProcess();
    DWORD std_ids[3] = {STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE};
    for (int k = 0; k < 3; k++) {
        if (input) {
            HANDLE r, w;
            CreatePipe(&r, &w, &sa, 0);
            ours[k] = k == 0 ? w : r;
            theirs[k] = k == 0 ? r : w;
            SetHandleInformation(ours[k], HANDLE_FLAG_INHERIT, 0);
        } else {
            HANDLE h = GetStdHandle(std_ids[k]);
            if (h && h != INVALID_HANDLE_VALUE) DuplicateHandle(me, h, me, &theirs[k], 0, TRUE, DUPLICATE_SAME_ACCESS);
        }
    }
    si.hStdInput = theirs[0];
    si.hStdOutput = theirs[1];
    si.hStdError = theirs[2];
    BOOL started = CreateProcessW(NULL, wline, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi);
    DWORD start_error = GetLastError();
    free(wline);
    for (int k = 0; k < 3; k++)
        if (theirs[k]) CloseHandle(theirs[k]);
    if (!started) {
        for (int k = 0; k < 3; k++)
            if (ours[k]) CloseHandle(ours[k]);
        if (start_error == ERROR_FILE_NOT_FOUND || start_error == ERROR_PATH_NOT_FOUND)
            return fail(c, ERR_process_RunError_notFound, 0);
        return fail(c, ERR_process_RunError_failed, win_errno(start_error));
    }
    CloseHandle(pi.hThread);
    int timed_out = 0;
    if (input) {
        /* each pipe has its own thread, so a child that fills one while we write another cannot stall */
        Pump pumps[3] = {{ours[0], NULL, input->p, input->n}, {ours[1], out, NULL, 0}, {ours[2], err, NULL, 0}};
        HANDLE threads[3];
        for (int k = 0; k < 3; k++) threads[k] = CreateThread(NULL, 0, pump, &pumps[k], 0, NULL);
        DWORD r = WaitForMultipleObjects(3, threads, TRUE, deadline == NEVER ? INFINITE : (DWORD)left_ms(deadline, 0x7FFFFFFE));
        if (r == WAIT_TIMEOUT) {
            timed_out = 1;
            TerminateProcess(pi.hProcess, 1);
            WaitForMultipleObjects(3, threads, TRUE, 1000);
        }
        for (int k = 0; k < 3; k++) CloseHandle(threads[k]);
        for (int k = 1; k < 3; k++) CloseHandle(ours[k]);
    }
    if (!timed_out &&
        WaitForSingleObject(pi.hProcess, deadline == NEVER ? INFINITE : (DWORD)left_ms(deadline, 0x7FFFFFFE)) ==
            WAIT_TIMEOUT) {
        timed_out = 1;
        TerminateProcess(pi.hProcess, 1);
    }
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    if (timed_out) return fail(c, ERR_process_RunError_timedOut, 0);
    *status = (int64_t)code;
    return 0;
#else
    char **argv = calloc((size_t)args->count + 2, sizeof(char *));
    argv[0] = cstr(program);
    for (int64_t i = 0; i < args->count; i++) argv[i + 1] = cstr(args->items[i]);
    int pipes[3][2] = {{-1, -1}, {-1, -1}, {-1, -1}};
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    if (input) {
        for (int k = 0; k < 3; k++) {
            if (pipe(pipes[k]) != 0) trap_text("the runtime could not create a pipe for a child process");
            fcntl(pipes[k][0], F_SETFD, FD_CLOEXEC);
            fcntl(pipes[k][1], F_SETFD, FD_CLOEXEC);
            posix_spawn_file_actions_adddup2(&actions, k == 0 ? pipes[k][0] : pipes[k][1], k);
        }
    }
    posix_spawnattr_t attr;
    posix_spawnattr_init(&attr);
    sigset_t defaults;
    sigemptyset(&defaults);
    sigaddset(&defaults, SIGPIPE);  /* the child gets the default action back, as subprocess restores it */
    posix_spawnattr_setsigdefault(&attr, &defaults);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETSIGDEF);
    pid_t pid;
    int rc = posix_spawnp(&pid, argv[0], &actions, &attr, argv, environ);
    posix_spawn_file_actions_destroy(&actions);
    posix_spawnattr_destroy(&attr);
    for (int64_t i = 0; i <= args->count; i++) free(argv[i]);
    free(argv);
    int ours[3] = {-1, -1, -1};
    if (input) {
        for (int k = 0; k < 3; k++) {
            close(k == 0 ? pipes[k][0] : pipes[k][1]);
            ours[k] = k == 0 ? pipes[k][1] : pipes[k][0];
        }
    }
    if (rc != 0) {
        for (int k = 0; k < 3; k++)
            if (ours[k] >= 0) close(ours[k]);
        if (rc == ENOENT) return fail(c, ERR_process_RunError_notFound, 0);
        return fail(c, ERR_process_RunError_failed, rc);
    }
    int timed_out = 0;
    if (input) {
        int64_t written = 0;
        for (int k = 0; k < 3; k++) fcntl(ours[k], F_SETFL, fcntl(ours[k], F_GETFL) | O_NONBLOCK);
        if (input->n == 0) {
            close(ours[0]);
            ours[0] = -1;
        }
        while (ours[0] >= 0 || ours[1] >= 0 || ours[2] >= 0) {
            if (past(deadline)) {
                timed_out = 1;
                break;
            }
            struct pollfd pfds[3];
            int which[3], n = 0;
            for (int k = 0; k < 3; k++) {
                if (ours[k] < 0) continue;
                pfds[n].fd = ours[k];
                pfds[n].events = k == 0 ? POLLOUT : POLLIN;
                pfds[n].revents = 0;
                which[n++] = k;
            }
            int r = poll(pfds, (nfds_t)n, (int)left_ms(deadline, 1000));
            if (r < 0 && errno != EINTR) break;
            for (int i = 0; i < n && r > 0; i++) {
                int k = which[i];
                if (!pfds[i].revents) continue;
                if (k == 0) {
                    ssize_t done = write(ours[0], input->p + written, (size_t)(input->n - written));
                    if (done > 0) written += done;
                    if ((done < 0 && errno != EAGAIN && errno != EINTR) || written >= input->n) {
                        close(ours[0]);
                        ours[0] = -1;
                    }
                } else {
                    Captured *into = k == 1 ? out : err;
                    into->data = grow(into->data, &into->cap, into->len + 65536, 1);
                    ssize_t got = read(ours[k], into->data + into->len, 65536);
                    if (got > 0) into->len += got;
                    else if (got == 0 || (errno != EAGAIN && errno != EINTR)) {
                        close(ours[k]);
                        ours[k] = -1;
                    }
                }
            }
        }
        for (int k = 0; k < 3; k++)
            if (ours[k] >= 0) close(ours[k]);
    }
    int st = 0;
    if (!timed_out) {
        int64_t pause = 1;
        for (;;) {
            pid_t r = waitpid(pid, &st, deadline == NEVER ? 0 : WNOHANG);
            if (r == pid) break;
            if (r < 0 && errno != EINTR) break;
            if (r == 0) {
                if (past(deadline)) {
                    timed_out = 1;
                    break;
                }
                sleep_ms(left_ms(deadline, pause));
                if (pause < 50) pause *= 2;
            }
        }
    }
    if (timed_out) {
        kill(pid, SIGKILL);
        waitpid(pid, &st, 0);
        return fail(c, ERR_process_RunError_timedOut, 0);
    }
    *status = WIFEXITED(st) ? WEXITSTATUS(st) : WIFSIGNALED(st) ? -WTERMSIG(st) : st;
    return 0;
#endif
}

static int32_t h_process_run(Call *c) {
    Names *args = get_object(arg(c, 1), H_ARGUMENTS);
    int64_t status = 0;
    int32_t r = run_child(c, text_arg(c, 0), args, arg(c, 2), NULL, NULL, NULL, &status);
    if (r) return r;
    c->res[0] = status;
    return 0;
}

static int32_t h_process_run_captured(Call *c) {
    Names *args = get_object(arg(c, 1), H_ARGUMENTS);
    Text input = text_arg(c, 2);
    int64_t region = arg(c, 3), limit = arg(c, 4), deadline = arg(c, 5), status = 0;
    Captured out = {NULL, 0, 0}, err = {NULL, 0, 0};
    int32_t r = run_child(c, text_arg(c, 0), args, deadline, &input, &out, &err, &status);
    if (!r && (out.len > limit || err.len > limit)) r = fail(c, ERR_process_RunError_tooLarge, 0);
    if (!r) {
        c->res[0] = status;
        put(region, out.data, out.len, c->res + 1);
        put(region, err.data, err.len, c->res + 3);
    }
    free(out.data);
    free(err.data);
    return r;
}

/* ---------------------------------------------------------------- byte buffers and text */

typedef struct Buffer {
    unsigned char *data;
    int64_t len, cap;
    void **kept;  /* copies handed out by `toBytes` live as long as the buffer */
    int64_t kept_count, kept_cap;
} Buffer;

static int32_t h_buffer_new(Call *c) {
    c->res[0] = new_handle(H_BUFFER, calloc(1, sizeof(Buffer)), arg(c, 0));
    return 0;
}

static void buffer_add(Buffer *b, const void *p, int64_t n) {
    b->data = grow(b->data, &b->cap, b->len + n, 1);
    if (n) memcpy(b->data + b->len, p, (size_t)n);
    b->len += n;
}

static int32_t h_buffer_append_string(Call *c) {
    Text t = text_arg(c, 1);
    buffer_add(get_object(arg(c, 0), H_BUFFER), t.p, t.n);
    return 0;
}
static int32_t h_buffer_append_byte(Call *c) {
    unsigned char b = (unsigned char)(arg(c, 1) & 0xFF);
    buffer_add(get_object(arg(c, 0), H_BUFFER), &b, 1);
    return 0;
}
static int32_t h_buffer_append_int(Call *c) {
    char digits[32];
    int n = snprintf(digits, sizeof digits, "%lld", (long long)arg(c, 1));
    buffer_add(get_object(arg(c, 0), H_BUFFER), digits, n);
    return 0;
}
static int32_t h_buffer_length(Call *c) {
    c->res[0] = ((Buffer *)get_object(arg(c, 0), H_BUFFER))->len;
    return 0;
}
static int32_t h_buffer_to_string(Call *c) {
    Buffer *b = get_object(arg(c, 0), H_BUFFER);
    int64_t bad = utf8_invalid_at(b->data, b->len);
    if (bad >= 0) return fail(c, ERR_string_Utf8Error_invalidAt, bad);
    put(arg(c, 1), b->data, b->len, c->res);
    return 0;
}
static int32_t h_buffer_to_bytes(Call *c) {
    Buffer *b = get_object(arg(c, 0), H_BUFFER);
    void *copy = malloc(b->len > 0 ? (size_t)b->len : 1);
    if (!copy) trap_text("out of memory in the runtime");
    if (b->len) memcpy(copy, b->data, (size_t)b->len);
    b->kept = grow(b->kept, &b->kept_cap, b->kept_count + 1, sizeof(void *));
    b->kept[b->kept_count++] = copy;
    c->res[0] = (int64_t)(intptr_t)copy;
    c->res[1] = b->len;
    return 0;
}

static int32_t h_string_from_bytes(Call *c) {
    Text raw = text_arg(c, 0);
    int64_t bad = utf8_invalid_at((const unsigned char *)raw.p, raw.n);
    if (bad >= 0) return fail(c, ERR_string_Utf8Error_invalidAt, bad);
    put(arg(c, 1), raw.p, raw.n, c->res);
    return 0;
}

/* ---------------------------------------------------------------- log lines */

static int32_t log_line(Call *c, const char *level) {
    Text t = text_arg(c, 0);
    fflush(stdout);
    int bad = fprintf(stderr, "[%s] ", level) < 0 || (t.n && fwrite(t.p, 1, (size_t)t.n, stderr) != (size_t)t.n) ||
              fputc('\n', stderr) == EOF;
    return bad ? fail(c, ERR_log_LogError_failed, errno ? errno : 1) : 0;
}
static int32_t h_log_debug(Call *c) { return log_line(c, "debug"); }
static int32_t h_log_info(Call *c) { return log_line(c, "info"); }
static int32_t h_log_warn(Call *c) { return log_line(c, "warn"); }
static int32_t h_log_error(Call *c) { return log_line(c, "error"); }

/* ---------------------------------------------------------------- maps and sets */

/* Rows in the order their keys were first put (D-62), found through an open-addressing index. A row is
   [live, hash, key slots..., value slots...]; a removed row stays until the rows are compacted. A text key
   (D-61) is two slots, a pointer and a length, compared by content. */
typedef struct Table {
    int text, ks, vs;
    int64_t stride;
    int64_t *rows;
    int64_t row_count, row_cap, live;
    int64_t *index;  /* row + 1; 0 empty; -1 removed */
    int64_t index_cap, index_used;
} Table;

#define ROW(t, i) ((t)->rows + (i) * (t)->stride)

static void table_shape(Table *t, int ks, int vs) {
    if (t->ks < 0 && ks >= 0) t->ks = ks;
    if (t->vs < 0 && vs >= 0) t->vs = vs;
    if (t->ks >= 0 && t->vs >= 0) t->stride = 2 + t->ks + t->vs;
}

static uint64_t finish(uint64_t h) {
    h ^= h >> 33;
    h *= 0xff51afd7ed558ccdULL;
    h ^= h >> 33;
    h *= 0xc4ceb9fe1a85ec53ULL;
    h ^= h >> 33;
    return h;
}

static uint64_t key_hash(const Table *t, const int64_t *k) {
    uint64_t h = 1469598103934665603ULL;
    if (t->text) {
        const unsigned char *p = (const unsigned char *)(intptr_t)k[0];
        for (int64_t i = 0; i < k[1]; i++) h = (h ^ p[i]) * 1099511628211ULL;
    } else {
        for (int i = 0; i < t->ks; i++) h = (h ^ (uint64_t)k[i]) * 1099511628211ULL + (uint64_t)i;
    }
    return finish(h);
}

static int key_equal(const Table *t, const int64_t *a, const int64_t *b) {
    if (t->text)
        return refined_bytes_equal((const char *)(intptr_t)a[0], a[1], (const char *)(intptr_t)b[0], b[1]);
    return memcmp(a, b, (size_t)t->ks * sizeof(int64_t)) == 0;
}

static int64_t table_find(const Table *t, const int64_t *k, uint64_t h) {
    if (!t->index_cap || t->stride == 0) return -1;
    for (uint64_t i = h & (uint64_t)(t->index_cap - 1);; i = (i + 1) & (uint64_t)(t->index_cap - 1)) {
        int64_t e = t->index[i];
        if (e == 0) return -1;
        if (e > 0) {
            int64_t *r = ROW(t, e - 1);
            if ((uint64_t)r[1] == h && key_equal(t, r + 2, k)) return e - 1;
        }
    }
}

static void table_place(Table *t, int64_t row, uint64_t h) {
    uint64_t i = h & (uint64_t)(t->index_cap - 1);
    while (t->index[i] > 0) i = (i + 1) & (uint64_t)(t->index_cap - 1);
    if (t->index[i] == 0) t->index_used++;
    t->index[i] = row + 1;
}

/* drop removed rows, keeping the order of the rest, and index them again in an index of at least `want` */
static void table_rebuild(Table *t, int64_t want) {
    int64_t j = 0;
    for (int64_t i = 0; i < t->row_count; i++) {
        if (!ROW(t, i)[0]) continue;
        if (i != j) memmove(ROW(t, j), ROW(t, i), (size_t)t->stride * sizeof(int64_t));
        j++;
    }
    t->row_count = j;
    int64_t cap = 16;
    while (cap < want || cap < (t->live + 1) * 2) cap *= 2;
    free(t->index);
    t->index = calloc((size_t)cap, sizeof(int64_t));
    if (!t->index) trap_text("out of memory in a map");
    t->index_cap = cap;
    t->index_used = 0;
    for (int64_t i = 0; i < t->row_count; i++) table_place(t, i, (uint64_t)ROW(t, i)[1]);
}

/* a new row for a key that is not in the table; its value slots are zero */
static int64_t *table_insert(Table *t, const int64_t *k, uint64_t h) {
    if ((t->index_used + 1) * 2 > t->index_cap) table_rebuild(t, t->live * 4);
    t->rows = grow(t->rows, &t->row_cap, (t->row_count + 1) * t->stride, sizeof(int64_t));
    int64_t row = t->row_count++;
    int64_t *r = ROW(t, row);
    memset(r, 0, (size_t)t->stride * sizeof(int64_t));
    r[0] = 1;
    r[1] = (int64_t)h;
    memcpy(r + 2, k, (size_t)t->ks * sizeof(int64_t));
    table_place(t, row, h);
    t->live++;
    return r;
}

static void table_remove(Table *t, int64_t row) {
    uint64_t h = (uint64_t)ROW(t, row)[1];
    for (uint64_t i = h & (uint64_t)(t->index_cap - 1);; i = (i + 1) & (uint64_t)(t->index_cap - 1)) {
        if (t->index[i] == row + 1) {
            t->index[i] = -1;
            break;
        }
    }
    ROW(t, row)[0] = 0;
    t->live--;
}

static void table_free(Table *t) {
    free(t->rows);
    free(t->index);
}

typedef struct Map {
    int64_t region;
    int text_values;  /* D-107: `String` values are copied into the map's region when they are put */
    Table t;
    Table copies;  /* D-61: every text key ever put, copied into the map's region once */
} Map;

static int32_t h_map_new(Call *c) {
    Map *m = calloc(1, sizeof(Map));
    m->region = arg(c, 0);
    m->t.text = c->params > 1 && arg(c, 1) != 0;  /* the compiler adds 1 when the keys are `String` */
    m->text_values = c->params > 2 && arg(c, 2) != 0;  /* and 1 when the values are (D-107) */
    m->t.ks = m->t.text ? 2 : -1;
    m->t.vs = -1;
    m->copies.text = 1;
    table_shape(&m->copies, 2, 0);
    c->res[0] = new_handle(H_MAP, m, m->region);
    return 0;
}

static Map *map_arg(Call *c, int vs) {
    Map *m = get_object(arg(c, 0), H_MAP);
    table_shape(&m->t, count(c, 1), vs);
    return m;
}

static int32_t h_map_put(Call *c) {
    Map *m = map_arg(c, count(c, 2));
    int64_t *k = slot(c, 1), copy[2];
    uint64_t h = key_hash(&m->t, k);
    if (m->t.text) {
        int64_t at = table_find(&m->copies, k, h);
        if (at < 0) {
            put(m->region, (const void *)(intptr_t)k[0], k[1], copy);
            table_insert(&m->copies, copy, h);
        } else {
            memcpy(copy, ROW(&m->copies, at) + 2, sizeof copy);
        }
        k = copy;
    }
    int64_t row = table_find(&m->t, k, h);
    int64_t *r = row >= 0 ? ROW(&m->t, row) : table_insert(&m->t, k, h);
    if (m->text_values) {
        int64_t *v = slot(c, 2), copied[2];
        put(m->region, (const void *)(intptr_t)v[0], v[1], copied);
        memcpy(r + 2 + m->t.ks, copied, sizeof copied);
    } else {
        memcpy(r + 2 + m->t.ks, slot(c, 2), (size_t)m->t.vs * sizeof(int64_t));
    }
    return 0;
}

static int32_t h_map_get(Call *c) {
    Map *m = map_arg(c, c->s->nres);
    int64_t *k = slot(c, 1);
    int64_t row = table_find(&m->t, k, key_hash(&m->t, k));
    if (row < 0) return fail(c, ERR_map_KeyMissing_missing, 0);
    memcpy(c->res, ROW(&m->t, row) + 2 + m->t.ks, (size_t)m->t.vs * sizeof(int64_t));
    return 0;
}

static int32_t h_map_contains(Call *c) {
    Map *m = map_arg(c, -1);
    int64_t *k = slot(c, 1);
    c->res[0] = table_find(&m->t, k, key_hash(&m->t, k)) >= 0;
    return 0;
}

static int32_t h_map_remove(Call *c) {
    Map *m = map_arg(c, -1);
    int64_t *k = slot(c, 1);
    int64_t row = table_find(&m->t, k, key_hash(&m->t, k));
    if (row < 0) return fail(c, ERR_map_KeyMissing_missing, 0);
    table_remove(&m->t, row);
    return 0;
}

static int32_t h_map_length(Call *c) {
    c->res[0] = ((Map *)get_object(arg(c, 0), H_MAP))->t.live;
    return 0;
}

/* the key at a position in first-put order, for `forEach` over a map (D-62) */
static int32_t h_map_key_at(Call *c) {
    Map *m = get_object(arg(c, 0), H_MAP);
    int64_t i = arg(c, 1);
    if (i < 0 || i >= m->t.live) {
        char msg[128];
        snprintf(msg, sizeof msg, "a map was read at position %lld of %lld", (long long)i, (long long)m->t.live);
        trap_text(msg);
    }
    if (m->t.row_count != m->t.live) table_rebuild(&m->t, m->t.index_cap);
    memcpy(c->res, ROW(&m->t, i) + 2, (size_t)m->t.ks * sizeof(int64_t));
    return 0;
}

static int32_t h_set_new(Call *c) {
    Table *t = calloc(1, sizeof(Table));
    t->text = c->params > 1 && arg(c, 1) != 0;  /* D-93: the compiler adds 1 when the items are `String` */
    t->ks = t->text ? 2 : -1;
    t->vs = 0;
    c->res[0] = new_handle(H_SET, t, arg(c, 0));
    return 0;
}

static Table *set_arg(Call *c) {
    Table *t = get_object(arg(c, 0), H_SET);
    table_shape(t, count(c, 1), 0);
    return t;
}

static int32_t h_set_add(Call *c) {
    Table *t = set_arg(c);
    int64_t *k = slot(c, 1), copy[2];
    uint64_t h = key_hash(t, k);
    if (table_find(t, k, h) >= 0) return 0;
    if (t->text) {  /* D-93: a text item is copied into the set's region the first time it is added */
        put(objects[arg(c, 0)].region, (const void *)(intptr_t)k[0], k[1], copy);
        k = copy;
    }
    table_insert(t, k, h);
    return 0;
}

/* the item at a position in first-added order, for `forEach` over a set (D-93) */
static int32_t h_set_item_at(Call *c) {
    Table *t = get_object(arg(c, 0), H_SET);
    int64_t i = arg(c, 1);
    if (i < 0 || i >= t->live) {
        char msg[128];
        snprintf(msg, sizeof msg, "a set was read at position %lld of %lld", (long long)i, (long long)t->live);
        trap_text(msg);
    }
    if (t->row_count != t->live) table_rebuild(t, t->index_cap);
    memcpy(c->res, ROW(t, i) + 2, (size_t)t->ks * sizeof(int64_t));
    return 0;
}

static int32_t h_set_contains(Call *c) {
    Table *t = set_arg(c);
    int64_t *k = slot(c, 1);
    c->res[0] = table_find(t, k, key_hash(t, k)) >= 0;
    return 0;
}

static int32_t h_set_remove(Call *c) {
    Table *t = set_arg(c);
    int64_t *k = slot(c, 1);
    int64_t row = table_find(t, k, key_hash(t, k));
    if (row >= 0) table_remove(t, row);
    return 0;
}

static int32_t h_set_length(Call *c) {
    c->res[0] = ((Table *)get_object(arg(c, 0), H_SET))->live;
    return 0;
}

/* ---------------------------------------------------------------- releasing */

static void drop(int64_t h) {
    if (h < 1 || h >= next_handle) return;
    Object *o = &objects[h];
    switch (o->kind) {
    case H_LISTING: case H_ARGUMENTS: names_free(o->p); break;
    case H_BUFFER: {
        Buffer *b = o->p;
        for (int64_t i = 0; i < b->kept_count; i++) free(b->kept[i]);
        free(b->kept);
        free(b->data);
        free(b);
        break;
    }
    case H_MAP: {
        Map *m = o->p;
        table_free(&m->t);
        table_free(&m->copies);
        free(m);
        break;
    }
    case H_SET: table_free(o->p); free(o->p); break;
    default: break;  /* a file is closed by `fs.close`, or at a trap; a region never owns one */
    }
    o->kind = H_NONE;
    o->p = NULL;
}

/* D-51: after a trap, close every file the program still holds. A child process is always waited for before
   the program goes on, so none is running when a trap happens. */
static int64_t release_all(void) {
    int64_t released = 0;
    for (int64_t h = 1; h < next_handle; h++) {
        if (objects[h].kind != H_FILE) continue;
        File *f = objects[h].p;
        raw_close(f->fd);
        objects[h].kind = H_NONE;
        released++;
    }
    return released;
}

/* ---------------------------------------------------------------- dispatch */

/* Every host target an executable implements; the third column is the index of the parameter a capability's
   scope limits (D-38), or -1. native.py reads this table: a program that calls a target not listed here is
   refused when it is built (R901). Keep one entry per line in this form. */
static const Target TARGETS[] = {
    {"buffer.appendByte", h_buffer_append_byte, -1},
    {"buffer.appendInt64", h_buffer_append_int, -1},
    {"buffer.appendString", h_buffer_append_string, -1},
    {"buffer.length", h_buffer_length, -1},
    {"buffer.new", h_buffer_new, -1},
    {"buffer.toBytes", h_buffer_to_bytes, -1},
    {"buffer.toString", h_buffer_to_string, -1},
    {"clock.monotonic", h_clock_monotonic, -1},
    {"clock.now", h_clock_now, -1},
    {"console.readLine", h_read_line, -1},
    {"environment.get", h_environment_get, -1},
    {"fs.close", h_fs_close, -1},
    {"fs.create", h_fs_create, 0},
    {"fs.createDirectory", h_fs_create_directory, 0},
    {"fs.entryCount", h_fs_entry_count, -1},
    {"fs.entryName", h_fs_entry_name, -1},
    {"fs.exists", h_fs_exists, 0},
    {"fs.listDirectory", h_fs_list_directory, 0},
    {"fs.lock", h_fs_lock, -1},
    {"fs.openAppend", h_fs_open_append, 0},
    {"fs.openRead", h_fs_open_read, 0},
    {"fs.openWrite", h_fs_open_write, 0},
    {"fs.read", h_fs_read, -1},
    {"fs.readAll", h_fs_read_all, 0},
    {"fs.remove", h_fs_remove, 0},
    {"fs.removeDirectory", h_fs_remove_directory, 0},
    {"fs.unlock", h_fs_unlock, -1},
    {"fs.write", h_fs_write, -1},
    {"fs.writeAll", h_fs_write_all, 0},
    {"log.debug", h_log_debug, -1},
    {"log.error", h_log_error, -1},
    {"log.info", h_log_info, -1},
    {"log.warn", h_log_warn, -1},
    {"map.Map.contains", h_map_contains, -1},
    {"map.Map.get", h_map_get, -1},
    {"map.Map.keyAt", h_map_key_at, -1},
    {"map.Map.length", h_map_length, -1},
    {"map.Map.new", h_map_new, -1},
    {"map.Map.put", h_map_put, -1},
    {"map.Map.remove", h_map_remove, -1},
    {"process.addArgument", h_add_argument, -1},
    {"process.argument", h_argument, -1},
    {"process.argumentCount", h_argument_count, -1},
    {"process.newArguments", h_new_arguments, -1},
    {"process.run", h_process_run, 0},
    {"process.runCaptured", h_process_run_captured, 0},
    {"set.Set.add", h_set_add, -1},
    {"set.Set.contains", h_set_contains, -1},
    {"set.Set.itemAt", h_set_item_at, -1},
    {"set.Set.length", h_set_length, -1},
    {"set.Set.new", h_set_new, -1},
    {"set.Set.remove", h_set_remove, -1},
    {"string.fromBytes", h_string_from_bytes, -1},
    {"time.Deadline.after", h_deadline_after, -1},
    {"time.Deadline.never", h_deadline_never, -1},
    {"time.sleep", h_sleep, -1},
};

/* Shapes by the address of their key: the key `<target>|<slots per parameter>|<result slots>` is a constant
   of the compiled program, so its address names it, and it is parsed once. */
static Shape **shapes;
static int64_t shape_cap, shape_count;

static Shape *parse_shape(const char *key, int64_t n) {
    Shape *s = calloc(1, sizeof(Shape));
    s->key = key;
    s->key_len = n;
    int64_t bar = 0;
    while (bar < n && key[bar] != '|') bar++;
    for (size_t i = 0; i < sizeof TARGETS / sizeof TARGETS[0]; i++)
        if ((int64_t)strlen(TARGETS[i].name) == bar && memcmp(TARGETS[i].name, key, (size_t)bar) == 0)
            s->target = &TARGETS[i];
    if (!s->target) {
        char msg[512];
        snprintf(msg, sizeof msg, "`%.*s` needs the host library, which standalone executables do not include; "
                 "run this program with `refined run`", (int)bar, key);
        trap_text(msg);
    }
    int64_t at = bar + 1, offset = 0;
    while (at < n && key[at] != '|') {
        int64_t v = 0;
        while (at < n && key[at] >= '0' && key[at] <= '9') v = v * 10 + (key[at++] - '0');
        if (s->params >= MAX_PARAMS) trap_text("a host call has too many parameters");
        s->count[s->params] = (int)v;
        s->offset[s->params] = (int)offset;
        offset += v;
        s->params++;
        if (at < n && key[at] == ',') at++;
    }
    int64_t v = 0;
    for (at++; at < n && key[at] >= '0' && key[at] <= '9'; at++) v = v * 10 + (key[at] - '0');
    s->nres = (int)v;
    return s;
}

static Shape *shape_of(const char *key, int64_t n) {
    if (shape_cap) {
        uint64_t i = finish((uint64_t)(uintptr_t)key) & (uint64_t)(shape_cap - 1);
        for (; shapes[i]; i = (i + 1) & (uint64_t)(shape_cap - 1))
            if (shapes[i]->key == key) return shapes[i];
    }
    Shape *s = parse_shape(key, n);
    if ((shape_count + 1) * 2 > shape_cap) {
        int64_t cap = shape_cap ? shape_cap * 2 : 64;
        Shape **fresh = calloc((size_t)cap, sizeof(Shape *));
        for (int64_t k = 0; k < shape_cap; k++) {
            if (!shapes[k]) continue;
            uint64_t i = finish((uint64_t)(uintptr_t)shapes[k]->key) & (uint64_t)(cap - 1);
            while (fresh[i]) i = (i + 1) & (uint64_t)(cap - 1);
            fresh[i] = shapes[k];
        }
        free(shapes);
        shapes = fresh;
        shape_cap = cap;
    }
    uint64_t i = finish((uint64_t)(uintptr_t)key) & (uint64_t)(shape_cap - 1);
    while (shapes[i]) i = (i + 1) & (uint64_t)(shape_cap - 1);
    shapes[i] = s;
    shape_count++;
    return s;
}

int32_t refined_host(const char *name, int64_t n, int64_t *args, int64_t *results, int64_t *payload) {
    Shape *s = shape_of(name, n);
    Call c = {s, args, results, payload, s->params};
    *payload = 0;
    if (s->target->scoped >= 0) {
        c.params--;  /* the compiler passes the scope text last (D-38) */
        check_scope(s->target->name, text_arg(&c, s->target->scoped), text_arg(&c, c.params));
    }
    return s->target->fn(&c);
}
