/*
 * ss_fs.c - standard.fs bounded file helpers (WS3-109).
 *
 * Handles are tombstoned on close instead of freed, so a stale/double close
 * fails closed rather than becoming a use-after-free. Chunk reads write into the
 * standard.buffer layout: [int64 length][bytes...][scratch].
 */
#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ss_runtime_export.h"

#define SS_FS_OK 0
#define SS_FS_ERR 1
#define SS_FS_MAX_PATH 4096
#define SS_FS_MAX_CHUNK (1024 * 1024)
#define SS_FS_MAX_WHOLE (1024 * 1024)
#define SS_FS_DECODE_PASSES 8

typedef struct {
    FILE *file;
    int live;
} ss_fs_handle;

typedef struct {
    ss_fs_handle **items;
    size_t count;
    size_t cap;
} ss_fs_handle_registry;

typedef struct {
    char **items;
    size_t count;
    size_t cap;
} ss_fs_string_registry;

static ss_fs_handle_registry g_fs_handles;
static ss_fs_string_registry g_fs_strings;

static int ss_fs_track_handle(ss_fs_handle *handle) {
    ss_fs_handle **grown;
    size_t next;
    if (handle == NULL) return 0;
    if (g_fs_handles.count == g_fs_handles.cap) {
        next = g_fs_handles.cap == 0 ? 16 : g_fs_handles.cap * 2;
        if (g_fs_handles.cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(ss_fs_handle *)) {
            return 0;
        }
        grown = (ss_fs_handle **)realloc(g_fs_handles.items, next * sizeof(ss_fs_handle *));
        if (grown == NULL) return 0;
        g_fs_handles.items = grown;
        g_fs_handles.cap = next;
    }
    g_fs_handles.items[g_fs_handles.count++] = handle;
    return 1;
}

static ss_fs_handle *ss_fs_live_handle(int64_t raw) {
    size_t i;
    ss_fs_handle *handle = (ss_fs_handle *)(intptr_t)raw;
    if (handle == NULL) return NULL;
    for (i = 0; i < g_fs_handles.count; i++) {
        if (g_fs_handles.items[i] == handle) {
            return handle->live && handle->file != NULL ? handle : NULL;
        }
    }
    return NULL;
}

static int ss_fs_track_string(char *buffer) {
    char **grown;
    size_t next;
    if (buffer == NULL) return 0;
    if (g_fs_strings.count == g_fs_strings.cap) {
        next = g_fs_strings.cap == 0 ? 16 : g_fs_strings.cap * 2;
        if (g_fs_strings.cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(char *)) {
            return 0;
        }
        grown = (char **)realloc(g_fs_strings.items, next * sizeof(char *));
        if (grown == NULL) return 0;
        g_fs_strings.items = grown;
        g_fs_strings.cap = next;
    }
    g_fs_strings.items[g_fs_strings.count++] = buffer;
    return 1;
}

static int ss_fs_untrack_string(const char *buffer) {
    size_t i;
    for (i = 0; i < g_fs_strings.count; i++) {
        if (g_fs_strings.items[i] == buffer) {
            g_fs_strings.items[i] = g_fs_strings.items[g_fs_strings.count - 1];
            g_fs_strings.count--;
            return 1;
        }
    }
    return 0;
}

static int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
    if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
    return -1;
}

static int percent_decode_once(const char *input, char *out, int *changed) {
    size_t i = 0;
    size_t j = 0;
    *changed = 0;
    while (input[i] != '\0') {
        if (j >= SS_FS_MAX_PATH) return 0;
        if (input[i] == '%') {
            int hi;
            int lo;
            if (input[i + 1] == '\0' || input[i + 2] == '\0') return 0;
            hi = hex_value(input[i + 1]);
            lo = hex_value(input[i + 2]);
            if (hi < 0 || lo < 0) return 0;
            out[j++] = (char)((hi << 4) | lo);
            i += 3;
            *changed = 1;
        } else {
            out[j++] = input[i++];
        }
    }
    out[j] = '\0';
    return 1;
}

static int validate_path_form(const char *path) {
    size_t i;
    if (path == NULL || path[0] == '\0') return 0;
    if (path[0] == '/' || path[0] == '\\') return 0;
    if (isalpha((unsigned char)path[0]) && path[1] == ':') return 0;
    if ((path[0] == '\\' && path[1] == '\\') || (path[0] == '/' && path[1] == '/')) return 0;
    for (i = 0; path[i] != '\0'; i++) {
        unsigned char ch = (unsigned char)path[i];
        if (i >= SS_FS_MAX_PATH || ch < 0x20 || path[i] == ':') return 0;
        if ((path[i] == '.' && path[i + 1] == '.')
                && (i == 0 || path[i - 1] == '/' || path[i - 1] == '\\')
                && (path[i + 2] == '\0' || path[i + 2] == '/' || path[i + 2] == '\\')) {
            return 0;
        }
    }
    return 1;
}

static int ss_fs_path_is_safe(const char *path) {
    char cur[SS_FS_MAX_PATH + 1];
    char next[SS_FS_MAX_PATH + 1];
    size_t n;
    int pass;
    if (!validate_path_form(path)) return 0;
    n = strlen(path);
    if (n > SS_FS_MAX_PATH) return 0;
    memcpy(cur, path, n + 1);
    for (pass = 0; pass < SS_FS_DECODE_PASSES; pass++) {
        int changed = 0;
        if (!percent_decode_once(cur, next, &changed)) return 0;
        if (!validate_path_form(next)) return 0;
        memcpy(cur, next, strlen(next) + 1);
        if (!changed) return 1;
    }
    return 0;
}

static int64_t ss_fs_file_size(FILE *file) {
#if defined(_WIN32)
    __int64 cur;
    __int64 end;
    cur = _ftelli64(file);
    if (cur < 0) return -1;
    if (_fseeki64(file, 0, SEEK_END) != 0) return -1;
    end = _ftelli64(file);
    if (end < 0) return -1;
    if (_fseeki64(file, cur, SEEK_SET) != 0) return -1;
    return (int64_t)end;
#else
    long cur;
    long end;
    cur = ftell(file);
    if (cur < 0) return -1;
    if (fseek(file, 0, SEEK_END) != 0) return -1;
    end = ftell(file);
    if (end < 0) return -1;
    if (fseek(file, cur, SEEK_SET) != 0) return -1;
    return (int64_t)end;
#endif
}

SS_EXPORT int64_t ss_fs_open_read(const char *safe_path) {
    FILE *file;
    ss_fs_handle *handle;
    if (!ss_fs_path_is_safe(safe_path)) return 0;
    file = fopen(safe_path, "rb");
    if (file == NULL) return 0;
    handle = (ss_fs_handle *)calloc(1, sizeof(ss_fs_handle));
    if (handle == NULL) {
        fclose(file);
        return 0;
    }
    handle->file = file;
    handle->live = 1;
    if (!ss_fs_track_handle(handle)) {
        fclose(file);
        free(handle);
        return 0;
    }
    return (int64_t)(intptr_t)handle;
}

SS_EXPORT int64_t ss_fs_size(int64_t raw_handle) {
    ss_fs_handle *handle = ss_fs_live_handle(raw_handle);
    if (handle == NULL) return -1;
    return ss_fs_file_size(handle->file);
}

SS_EXPORT int32_t ss_fs_close(int64_t raw_handle) {
    ss_fs_handle *handle = ss_fs_live_handle(raw_handle);
    if (handle == NULL) return SS_FS_ERR;
    if (fclose(handle->file) != 0) {
        handle->file = NULL;
        handle->live = 0;
        return SS_FS_ERR;
    }
    handle->file = NULL;
    handle->live = 0;
    return SS_FS_OK;
}

SS_EXPORT int64_t ss_fs_read_chunk(int64_t raw_handle, void *buffer, int64_t maximum_bytes) {
    ss_fs_handle *handle = ss_fs_live_handle(raw_handle);
    int64_t buffer_len;
    int64_t want;
    size_t got;
    unsigned char *data;
    if (handle == NULL || buffer == NULL) return -1;
    if (maximum_bytes <= 0 || maximum_bytes > SS_FS_MAX_CHUNK) return -1;
    buffer_len = *((int64_t *)buffer);
    if (buffer_len < 0) return -1;
    want = maximum_bytes;
    if (want > buffer_len) want = buffer_len;
    if (want > SS_FS_MAX_CHUNK) want = SS_FS_MAX_CHUNK;
    data = ((unsigned char *)buffer) + 8;
    got = fread(data, 1, (size_t)want, handle->file);
    if (got == 0 && ferror(handle->file)) return -1;
    return (int64_t)got;
}

SS_EXPORT const char *ss_fs_read_text_limit(const char *safe_path, int64_t maximum_bytes) {
    FILE *file;
    int64_t size;
    char *buffer;
    if (!ss_fs_path_is_safe(safe_path)) return NULL;
    if (maximum_bytes < 0 || maximum_bytes > SS_FS_MAX_WHOLE) return NULL;
    file = fopen(safe_path, "rb");
    if (file == NULL) return NULL;
    size = ss_fs_file_size(file);
    if (size < 0 || size > maximum_bytes || size > SS_FS_MAX_WHOLE) {
        fclose(file);
        return NULL;
    }
    if (fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return NULL;
    }
    buffer = (char *)malloc((size_t)size + 1);
    if (buffer == NULL) {
        fclose(file);
        return NULL;
    }
    if (fread(buffer, 1, (size_t)size, file) != (size_t)size) {
        free(buffer);
        fclose(file);
        return NULL;
    }
    fclose(file);
    if (memchr(buffer, '\0', (size_t)size) != NULL) {
        free(buffer);
        return NULL;
    }
    buffer[size] = '\0';
    if (!ss_fs_track_string(buffer)) {
        free(buffer);
        return NULL;
    }
    return buffer;
}

SS_EXPORT int32_t ss_fs_release_text(const char *text) {
    if (text == NULL || !ss_fs_untrack_string(text)) return 0;
    free((void *)text);
    return 1;
}
