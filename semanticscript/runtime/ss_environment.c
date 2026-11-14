/*
 * ss_environment.c - standard.environment runtime helpers (WS3-108).
 *
 * The ABI follows the stdlib out-param convention:
 *   int fn(args..., const char **out)
 * returns 0 on success and non-zero on EnvironmentError. Successful string
 * results are heap-owned by this runtime and are released through
 * ss_environment_release, which ignores stale or foreign pointers.
 */
#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ss_runtime_export.h"

#define SS_ENV_OK 0
#define SS_ENV_ERR 1
#define SS_ENV_MAX_NAME 256
#define SS_ENV_MAX_VALUE (64 * 1024)
#define SS_ENV_MAX_DOTENV (1024 * 1024)

typedef struct { char **items; size_t count; size_t cap; } ss_env_registry;

static ss_env_registry g_env_strings;

static int ss_env_track(char *buffer) {
    if (buffer == NULL) return 0;
    if (g_env_strings.count == g_env_strings.cap) {
        size_t next = g_env_strings.cap == 0 ? 16 : g_env_strings.cap * 2;
        char **grown;
        if (g_env_strings.cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(char *)) {
            return 0;
        }
        grown = (char **)realloc(g_env_strings.items, next * sizeof(char *));
        if (grown == NULL) return 0;
        g_env_strings.items = grown;
        g_env_strings.cap = next;
    }
    g_env_strings.items[g_env_strings.count++] = buffer;
    return 1;
}

static int ss_env_untrack(const char *buffer) {
    size_t i;
    for (i = 0; i < g_env_strings.count; i++) {
        if (g_env_strings.items[i] == buffer) {
            g_env_strings.items[i] = g_env_strings.items[g_env_strings.count - 1];
            g_env_strings.count--;
            return 1;
        }
    }
    return 0;
}

static int ss_env_valid_name(const char *name) {
    size_t i;
    if (name == NULL || name[0] == '\0') return 0;
    if (!(isalpha((unsigned char)name[0]) || name[0] == '_')) return 0;
    for (i = 1; name[i] != '\0'; i++) {
        if (i >= SS_ENV_MAX_NAME) return 0;
        if (!(isalnum((unsigned char)name[i]) || name[i] == '_')) return 0;
    }
    return 1;
}

static char *ss_env_dup_owned(const char *text) {
    size_t n;
    char *out;
    if (text == NULL) return NULL;
    n = strlen(text);
    if (n > SS_ENV_MAX_VALUE) return NULL;
    out = (char *)malloc(n + 1);
    if (out == NULL) return NULL;
    memcpy(out, text, n + 1);
    if (!ss_env_track(out)) {
        free(out);
        return NULL;
    }
    return out;
}

static int ss_env_set_owned_out(const char *text, const char **out) {
    char *owned;
    if (out == NULL) return SS_ENV_ERR;
    *out = NULL;
    owned = ss_env_dup_owned(text);
    if (owned == NULL) return SS_ENV_ERR;
    *out = owned;
    return SS_ENV_OK;
}

static int ss_env_set_process_value(const char *key, const char *value) {
#if defined(_WIN32)
    return _putenv_s(key, value) == 0;
#else
    return setenv(key, value, 1) == 0;
#endif
}

static char *trim_left(char *s) {
    while (*s == ' ' || *s == '\t') s++;
    return s;
}

static void trim_right(char *s) {
    size_t n = strlen(s);
    while (n > 0 && (s[n - 1] == ' ' || s[n - 1] == '\t' ||
                     s[n - 1] == '\r' || s[n - 1] == '\n')) {
        s[--n] = '\0';
    }
}

static int ss_env_path_is_safe(const char *path) {
    size_t i;
    if (path == NULL || path[0] == '\0') return 0;
    if (path[0] == '/' || path[0] == '\\') return 0;
    if (isalpha((unsigned char)path[0]) && path[1] == ':') return 0;
    for (i = 0; path[i] != '\0'; i++) {
        unsigned char ch = (unsigned char)path[i];
        if (ch < 0x20 || path[i] == ':') return 0;
        if ((path[i] == '.' && path[i + 1] == '.')
                && (i == 0 || path[i - 1] == '/' || path[i - 1] == '\\')
                && (path[i + 2] == '\0' || path[i + 2] == '/' || path[i + 2] == '\\')) {
            return 0;
        }
    }
    return 1;
}

static int parse_dotenv_line(char *line) {
    char *p = trim_left(line);
    char *eq;
    char *key;
    char *value;
    char *comment;
    if (*p == '\0' || *p == '#') return SS_ENV_OK;
    if (strncmp(p, "export", 6) == 0 && (p[6] == ' ' || p[6] == '\t')) {
        p = trim_left(p + 6);
    }
    eq = strchr(p, '=');
    if (eq == NULL) return SS_ENV_ERR;
    *eq = '\0';
    trim_right(p);
    key = p;
    value = trim_left(eq + 1);
    trim_right(value);
    if (!ss_env_valid_name(key)) return SS_ENV_ERR;
    if (value[0] == '"' || value[0] == '\'') {
        char quote = value[0];
        size_t n = strlen(value);
        if (n < 2 || value[n - 1] != quote) return SS_ENV_ERR;
        value[n - 1] = '\0';
        value++;
    } else {
        comment = strchr(value, '#');
        if (comment != NULL && (comment == value || comment[-1] == ' ' || comment[-1] == '\t')) {
            *comment = '\0';
            trim_right(value);
        }
    }
    if (strlen(value) > SS_ENV_MAX_VALUE) return SS_ENV_ERR;
    return ss_env_set_process_value(key, value) ? SS_ENV_OK : SS_ENV_ERR;
}

SS_EXPORT int32_t ss_environment_get(const char *name, const char **out) {
    const char *value;
    if (out == NULL) return SS_ENV_ERR;
    *out = NULL;
    if (!ss_env_valid_name(name)) return SS_ENV_ERR;
    value = getenv(name);
    if (value == NULL) value = "";
    return ss_env_set_owned_out(value, out);
}

SS_EXPORT int32_t ss_environment_require(const char *name, const char **out) {
    const char *value;
    if (out == NULL) return SS_ENV_ERR;
    *out = NULL;
    if (!ss_env_valid_name(name)) return SS_ENV_ERR;
    value = getenv(name);
    if (value == NULL) return SS_ENV_ERR;
    return ss_env_set_owned_out(value, out);
}

SS_EXPORT int32_t ss_environment_require_secret(const char *name, const char **out) {
    return ss_environment_require(name, out);
}

SS_EXPORT int32_t ss_environment_load_dotenv(const char *safe_path) {
    FILE *f;
    long size;
    char *buf;
    char *line;
    char *next;
    int rc = SS_ENV_OK;
    if (!ss_env_path_is_safe(safe_path)) return SS_ENV_ERR;
    f = fopen(safe_path, "rb");
    if (f == NULL) return SS_ENV_ERR;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return SS_ENV_ERR; }
    size = ftell(f);
    if (size < 0 || size > SS_ENV_MAX_DOTENV) { fclose(f); return SS_ENV_ERR; }
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return SS_ENV_ERR; }
    buf = (char *)malloc((size_t)size + 1);
    if (buf == NULL) { fclose(f); return SS_ENV_ERR; }
    if (fread(buf, 1, (size_t)size, f) != (size_t)size) {
        free(buf);
        fclose(f);
        return SS_ENV_ERR;
    }
    fclose(f);
    buf[size] = '\0';
    line = buf;
    while (line != NULL && *line != '\0') {
        next = strchr(line, '\n');
        if (next != NULL) {
            *next = '\0';
            next++;
        }
        if (parse_dotenv_line(line) != SS_ENV_OK) {
            rc = SS_ENV_ERR;
            break;
        }
        line = next;
    }
    free(buf);
    return rc;
}

SS_EXPORT int32_t ss_environment_release(const char *value) {
    if (value == NULL || !ss_env_untrack(value)) return 0;
    free((void *)value);
    return 1;
}

