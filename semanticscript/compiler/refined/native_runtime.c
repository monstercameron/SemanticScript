/* The runtime of a standalone executable built with `refined build --kind executable`.
 *
 * It implements the callbacks compiled code makes (see CALLBACKS in codegen.py) in plain C, so the
 * program's object file and this file link statically into one executable with no Python. It covers
 * the core language: output, regions, traps with a stack trace, the call stack, recursion and stack
 * guards, strings, and tasks (run when started). Library targets that need the operating system host
 * (files, sockets, processes, maps, channels, ...) are in the JIT runtime only: calling one traps with
 * the target's name. The entry and its stack budget come from the small file `build` generates.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TRAP_EXIT_CODE 70
#define MAX_FRAMES 65536

static const char *frame_names[MAX_FRAMES];
static int64_t frame_lengths[MAX_FRAMES];
static int64_t frame_count;
static int64_t stack_floor;
static int64_t depth[4096];

void refined_set_floor(int64_t floor) { stack_floor = floor; }

void refined_trap(const char *p, int64_t n) {
    fflush(stdout);
    fprintf(stderr, "trap: %.*s\n", (int)n, p);
    int64_t shown = 0, top = frame_count < MAX_FRAMES ? frame_count : MAX_FRAMES;
    for (int64_t i = top - 1; i >= 0 && shown < 12; ) {
        int64_t j = i, runs = 0;
        while (j >= 0 && frame_lengths[j] == frame_lengths[i] &&
               memcmp(frame_names[j], frame_names[i], (size_t)frame_lengths[i]) == 0) {
            j--;
            runs++;
        }
        if (runs > 1)
            fprintf(stderr, "  in %.*s (%lld calls deep)\n", (int)frame_lengths[i], frame_names[i], (long long)runs);
        else
            fprintf(stderr, "  in %.*s\n", (int)frame_lengths[i], frame_names[i]);
        shown++;
        i = j;
    }
    fflush(stderr);
    exit(TRAP_EXIT_CODE);
}

static void trap_text(const char *message) { refined_trap(message, (int64_t)strlen(message)); }

int32_t refined_write(int32_t fd, const char *p, int64_t n, int32_t newline) {
    FILE *f = fd == 2 ? stderr : stdout;
    if (n > 0 && fwrite(p, 1, (size_t)n, f) != (size_t)n) return 1;
    if (newline && fputc('\n', f) == EOF) return 1;
    return 0;
}

int32_t refined_write_int(int32_t fd, int64_t v, int32_t newline) {
    FILE *f = fd == 2 ? stderr : stdout;
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
    if (strcmp(buf, "inf") == 0 || strcmp(buf, "-inf") == 0 || strcmp(buf, "nan") == 0) { /* as written */ }
    return fprintf(f, newline ? "%s\n" : "%s", buf) < 0;
}

int32_t refined_bytes_equal(const char *a, int64_t an, const char *b, int64_t bn) {
    return an == bn && (an == 0 || memcmp(a, b, (size_t)an) == 0);
}

/* ---------------------------------------------------------------- regions */

typedef struct Block { struct Block *next; } Block;
typedef struct Region { int64_t capacity, used; Block *blocks; const char *label; int64_t label_len; } Region;

void *refined_region_new(int64_t capacity, const char *label, int64_t label_len) {
    Region *r = calloc(1, sizeof(Region));
    if (!r) trap_text("out of memory creating a region");
    r->capacity = capacity;
    r->label = label;
    r->label_len = label_len;
    return r;
}

void *refined_region_alloc(void *handle, int64_t size) {
    Region *r = handle;
    if (r->used + size > r->capacity) {
        char msg[256];
        snprintf(msg, sizeof msg, "%.*s exceeded its capacity of %lld bytes", (int)r->label_len, r->label,
                 (long long)r->capacity);
        trap_text(msg);
    }
    r->used += size;
    Block *b = calloc(1, sizeof(Block) + (size_t)(size > 0 ? size : 1));
    if (!b) trap_text("out of memory in a region");
    b->next = r->blocks;
    r->blocks = b;
    return b + 1;
}

int64_t refined_region_remaining(void *handle) {
    Region *r = handle;
    return r->capacity - r->used;
}

void refined_region_free(void *handle) {
    Region *r = handle;
    for (Block *b = r->blocks; b;) {
        Block *n = b->next;
        free(b);
        b = n;
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

/* ---------------------------------------------------------------- host targets: the JIT runtime only */

int32_t refined_host(const char *name, int64_t n, int64_t *args, int64_t *results, int64_t *payload) {
    char msg[512];
    int64_t shown = n;
    for (int64_t i = 0; i < n; i++) if (name[i] == '|') { shown = i; break; }
    snprintf(msg, sizeof msg, "`%.*s` needs the host library, which standalone executables do not include; "
             "run this program with `refined run`", (int)shown, name);
    trap_text(msg);
    (void)args; (void)results; (void)payload;
    return 1;
}

/* ---------------------------------------------------------------- tasks: run when started */

void *refined_task_frame(int64_t size) {
    void *p = calloc(1, (size_t)(size > 0 ? size : 1));
    if (!p) trap_text("out of memory for a task");
    return p;
}

/* A task runs to its end when it is started, so `cancel` has nothing left to stop. A group keeps the first
   error one of its tasks reports (D-48) until its `join` reads it. */
#define MAX_GROUPS 4096
static unsigned char *group_error_bytes[MAX_GROUPS];
static int64_t group_error_size[MAX_GROUPS];
static int64_t next_group = 0, current_group = 0;

int64_t refined_task_spawn(void *thunk, void *frame, int64_t group) {
    int64_t outer = current_group;
    current_group = group;
    ((void (*)(void *))thunk)(frame);
    current_group = outer;
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

/* ---------------------------------------------------------------- the call stack and recursion */

int32_t refined_recursion_enter(int64_t op, int64_t limit, int64_t here) {
    int64_t d = ++depth[op & 4095];
    if (d > limit) return 1;
    if (stack_floor && here < stack_floor) return 2;
    return 0;
}
void refined_recursion_leave(int64_t op) { --depth[op & 4095]; }

void refined_frame_push(const char *p, int64_t n) {
    if (frame_count < MAX_FRAMES) {
        frame_names[frame_count] = p;
        frame_lengths[frame_count] = n;
    }
    frame_count++;
}
void refined_frame_pop(void) { frame_count--; }

void refined_block(const char *p, int64_t n, void **values, int64_t count, const char *d, int64_t dn) {
    (void)p; (void)n; (void)values; (void)count; (void)d; (void)dn;
}
