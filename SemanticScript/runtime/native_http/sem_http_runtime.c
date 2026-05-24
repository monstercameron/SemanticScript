#include "sem_http_runtime.h"

#include <ctype.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Keep the fallback backend's full-request buffer bounded. Applications should
 * enforce their own smaller body policy with ss_http_request_body_length; this
 * transport ceiling only prevents unbounded allocation in the blocking adapter.
 */
#define SS_HTTP_MAX_REQUEST_BYTES (1024 * 1024)
#define SS_HTTP_MAX_HEADERS 32
#define SS_HTTP_MAX_QUERY_PARAMS 32
#define SS_HTTP_MAX_MULTIPART_PARTS 16
#define SS_HTTP_MULTIPART_BOUNDARY_MAX 128
#define SS_HTTP_SHUTDOWN_POLL_MILLIS 250

/* Pattern-route knobs. SS_HTTP_MAX_PATH_PARAMS bounds the number of
 * :name segments per request — 8 is more than any realistic REST path.
 * The scratch buffer holds null-terminated copies of every captured
 * segment so the caller can pass them around without lifetime concerns
 * and the original request->path stays intact (so http.requestPath
 * still returns the full URL path including the captured ids). */
#define SS_HTTP_MAX_PATH_PARAMS 8
#define SS_HTTP_PATH_PARAMS_BUFFER_SIZE 512
#define SS_HTTP_MAX_ROUTE_SEGMENTS 16

typedef struct SSHttpNameValue {
    const char *name;
    const char *value;
} SSHttpNameValue;

typedef struct SSHttpMultipartPart {
    const char *name;
    const char *filename;
    const char *content_type;
    const char *body;
    size_t body_length;
} SSHttpMultipartPart;

typedef struct SSHttpPathParam {
    const char *name;   /* points into a compiled-route segment (stable across the server's lifetime) */
    const char *value;  /* points into the request's path_params_buffer */
} SSHttpPathParam;

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>          /* FILETIME, GetSystemTimeAsFileTime, CreateDirectoryA */
typedef SOCKET ss_socket_t;
#define SS_INVALID_SOCKET INVALID_SOCKET
static void ss_close_socket(ss_socket_t socket_handle) {
    closesocket(socket_handle);
}
#else
#include <arpa/inet.h>
#include <errno.h>
#include <sys/stat.h>          /* mkdir for ss_http_filesystem_ensure_directory */
#include <sys/select.h>
#include <time.h>              /* clock_gettime for ss_http_now_millis */
#include <netdb.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
typedef int ss_socket_t;
#define SS_INVALID_SOCKET (-1)
static void ss_close_socket(ss_socket_t socket_handle) {
    close(socket_handle);
}
#endif

typedef struct SSHttpResponseBackend {
    ss_socket_t socket_handle;
    int stream_started;
    int stream_closed;
    int stream_error;
} SSHttpResponseBackend;

static volatile sig_atomic_t g_http_shutdown_requested = 0;

static void request_http_shutdown_from_signal(int signal_number) {
    (void)signal_number;
    g_http_shutdown_requested = 1;
}

static void reset_http_shutdown_state(void) {
    g_http_shutdown_requested = 0;
}

static int http_shutdown_requested(void) {
    return g_http_shutdown_requested != 0;
}

int ss_http_server_is_shutting_down(void) {
    return http_shutdown_requested();
}

#ifdef _WIN32
static BOOL WINAPI http_console_ctrl_handler(DWORD ctrl_type) {
    switch (ctrl_type) {
    case CTRL_C_EVENT:
    case CTRL_BREAK_EVENT:
    case CTRL_CLOSE_EVENT:
    case CTRL_SHUTDOWN_EVENT:
        g_http_shutdown_requested = 1;
        return TRUE;
    default:
        return FALSE;
    }
}
#endif

static void install_http_shutdown_handlers(void) {
    signal(SIGINT, request_http_shutdown_from_signal);
    signal(SIGTERM, request_http_shutdown_from_signal);
#ifdef _WIN32
    SetConsoleCtrlHandler(http_console_ctrl_handler, TRUE);
#endif
}

struct SSHttpRequest {
    const char *method;
    const char *path;
    const char *query;
    const char *body;
    size_t body_length;
    SSHttpNameValue headers[SS_HTTP_MAX_HEADERS];
    size_t header_count;
    SSHttpNameValue query_params[SS_HTTP_MAX_QUERY_PARAMS];
    size_t query_param_count;
    SSHttpMultipartPart multipart_parts[SS_HTTP_MAX_MULTIPART_PARTS];
    size_t multipart_part_count;
    int multipart_parsed;
    SSHttpPathParam path_params[SS_HTTP_MAX_PATH_PARAMS];
    size_t path_param_count;
    /* Per-request scratch arena for null-terminated copies of captured
     * path-parameter values. path_params[i].value points into this
     * buffer so callers can treat values as ordinary C strings without
     * worrying about which bytes of the request line they came from. */
    char path_params_buffer[SS_HTTP_PATH_PARAMS_BUFFER_SIZE];
    size_t path_params_buffer_used;
    void *backend_request;
};

struct SSHttpResponse {
    int status;
    const char *body;
    size_t body_length;
    const char *content_type;
    SSHttpNameValue headers[SS_HTTP_MAX_HEADERS];
    size_t header_count;
    char *owned_body;
    char *owned_content_type;
    char *owned_header_names[SS_HTTP_MAX_HEADERS];
    char *owned_header_values[SS_HTTP_MAX_HEADERS];
    void *backend_response;
};

static int has_valid_route_table(const SSHttpServerConfig *config) {
    size_t index;

    if (config == NULL || config->host == NULL || config->port == 0) {
        return 0;
    }
    if (config->route_count > 0 && config->routes == NULL) {
        return 0;
    }

    for (index = 0; index < config->route_count; ++index) {
        const SSHttpRoute *route = &config->routes[index];
        if (route->method == NULL || route->path == NULL || route->handler == NULL) {
            return 0;
        }
    }

    return 1;
}

static int ascii_case_equal(const char *left, const char *right) {
    while (*left != '\0' && *right != '\0') {
        unsigned char left_ch = (unsigned char)*left;
        unsigned char right_ch = (unsigned char)*right;
        if (tolower(left_ch) != tolower(right_ch)) {
            return 0;
        }
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

static int ascii_case_prefix_equal(const char *text, const char *prefix) {
    while (*prefix != '\0') {
        unsigned char text_ch = (unsigned char)*text;
        unsigned char prefix_ch = (unsigned char)*prefix;
        if (*text == '\0' || tolower(text_ch) != tolower(prefix_ch)) {
            return 0;
        }
        ++text;
        ++prefix;
    }
    return 1;
}

static char *trim_left(char *text) {
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') {
        ++text;
    }
    return text;
}

static void trim_right(char *text) {
    size_t length = strlen(text);
    while (length > 0) {
        char ch = text[length - 1];
        if (ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n') {
            break;
        }
        text[length - 1] = '\0';
        --length;
    }
}

static void clear_owned_response_body(SSHttpResponse *response) {
    if (response == NULL) {
        return;
    }
    if (response->owned_body != NULL) {
        free(response->owned_body);
        response->owned_body = NULL;
    }
    response->body = NULL;
    response->body_length = 0;
}

static void clear_owned_response_content_type(SSHttpResponse *response) {
    if (response == NULL) {
        return;
    }
    if (response->owned_content_type != NULL) {
        free(response->owned_content_type);
        response->owned_content_type = NULL;
    }
    response->content_type = NULL;
}

static void clear_owned_response_headers(SSHttpResponse *response) {
    size_t index;

    if (response == NULL) {
        return;
    }
    for (index = 0; index < response->header_count; ++index) {
        free(response->owned_header_names[index]);
        free(response->owned_header_values[index]);
        response->owned_header_names[index] = NULL;
        response->owned_header_values[index] = NULL;
        response->headers[index].name = NULL;
        response->headers[index].value = NULL;
    }
    response->header_count = 0;
}

static void clear_owned_response(SSHttpResponse *response) {
    clear_owned_response_body(response);
    clear_owned_response_content_type(response);
    clear_owned_response_headers(response);
}

static char *copy_bytes_with_nul(const char *source, size_t length) {
    char *copy;

    if (source == NULL && length > 0) {
        return NULL;
    }
    if (length == (size_t)-1) {
        return NULL;
    }
    copy = (char *)malloc(length + 1);
    if (copy == NULL) {
        return NULL;
    }
    if (length > 0) {
        memcpy(copy, source, length);
    }
    copy[length] = '\0';
    return copy;
}

static char *copy_c_string(const char *source) {
    if (source == NULL) {
        return NULL;
    }
    return copy_bytes_with_nul(source, strlen(source));
}

int ss_http_response_text(
    SSHttpResponse *response,
    int status,
    const char *body,
    const char *content_type
) {
    char *owned_body;
    char *owned_content_type = NULL;

    if (response == NULL || body == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }

    owned_body = copy_c_string(body);
    if (owned_body == NULL) {
        return SS_HTTP_ERR_ENGINE;
    }
    if (content_type != NULL) {
        owned_content_type = copy_c_string(content_type);
        if (owned_content_type == NULL) {
            free(owned_body);
            return SS_HTTP_ERR_ENGINE;
        }
    }

    clear_owned_response_body(response);
    clear_owned_response_content_type(response);
    response->owned_body = owned_body;
    response->owned_content_type = owned_content_type;
    response->status = status;
    response->body = owned_body;
    response->body_length = strlen(owned_body);
    response->content_type = owned_content_type != NULL
        ? owned_content_type
        : "text/plain; charset=utf-8";
    return SS_HTTP_OK;
}

int ss_http_response_bytes(
    SSHttpResponse *response,
    int status,
    const void *body,
    size_t body_length,
    const char *content_type
) {
    char *owned_body;
    char *owned_content_type = NULL;

    if (response == NULL || (body == NULL && body_length > 0)) {
        return SS_HTTP_ERR_CONFIG;
    }

    owned_body = copy_bytes_with_nul((const char *)body, body_length);
    if (owned_body == NULL) {
        return SS_HTTP_ERR_ENGINE;
    }
    if (content_type != NULL) {
        owned_content_type = copy_c_string(content_type);
        if (owned_content_type == NULL) {
            free(owned_body);
            return SS_HTTP_ERR_ENGINE;
        }
    }

    clear_owned_response_body(response);
    clear_owned_response_content_type(response);
    response->owned_body = owned_body;
    response->owned_content_type = owned_content_type;
    response->status = status;
    response->body = owned_body;
    response->body_length = body_length;
    response->content_type = owned_content_type != NULL
        ? owned_content_type
        : "application/octet-stream";
    return SS_HTTP_OK;
}

static int is_valid_sse_event_name(const char *event_name) {
    const unsigned char *cursor = (const unsigned char *)event_name;

    if (event_name == NULL || *event_name == '\0') {
        return 0;
    }
    while (*cursor != '\0') {
        if (*cursor == '\r' || *cursor == '\n' || *cursor == ':') {
            return 0;
        }
        ++cursor;
    }
    return 1;
}

static size_t sse_data_wire_length(const char *event_data) {
    size_t length = 0;
    const char *cursor = event_data;

    while (*cursor != '\0') {
        length += strlen("data: ");
        while (*cursor != '\0' && *cursor != '\r' && *cursor != '\n') {
            ++length;
            ++cursor;
        }
        length += 1;
        if (*cursor == '\r') {
            ++cursor;
            if (*cursor == '\n') {
                ++cursor;
            }
        } else if (*cursor == '\n') {
            ++cursor;
        }
    }

    if (*event_data == '\0') {
        length += strlen("data: \n");
    }

    return length;
}

static char *write_sse_data_lines(char *out, const char *event_data) {
    const char *cursor = event_data;

    if (*event_data == '\0') {
        memcpy(out, "data: \n", strlen("data: \n"));
        return out + strlen("data: \n");
    }

    while (*cursor != '\0') {
        memcpy(out, "data: ", strlen("data: "));
        out += strlen("data: ");
        while (*cursor != '\0' && *cursor != '\r' && *cursor != '\n') {
            *out++ = *cursor++;
        }
        *out++ = '\n';
        if (*cursor == '\r') {
            ++cursor;
            if (*cursor == '\n') {
                ++cursor;
            }
        } else if (*cursor == '\n') {
            ++cursor;
        }
    }

    return out;
}

int ss_http_response_sse_event(
    SSHttpResponse *response,
    int status,
    const char *event_name,
    const char *event_data
) {
    const char *event_prefix = "event: ";
    const char *content_type = "text/event-stream; charset=utf-8";
    size_t event_name_length;
    size_t payload_length;
    char *payload;
    char *cursor;

    if (response == NULL || !is_valid_sse_event_name(event_name) || event_data == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }

    event_name_length = strlen(event_name);
    payload_length =
        strlen(event_prefix) + event_name_length + 1 +
        sse_data_wire_length(event_data) +
        1;
    payload = (char *)malloc(payload_length + 1);
    if (payload == NULL) {
        return SS_HTTP_ERR_ENGINE;
    }

    cursor = payload;
    memcpy(cursor, event_prefix, strlen(event_prefix));
    cursor += strlen(event_prefix);
    memcpy(cursor, event_name, event_name_length);
    cursor += event_name_length;
    *cursor++ = '\n';
    cursor = write_sse_data_lines(cursor, event_data);
    *cursor++ = '\n';
    *cursor = '\0';

    clear_owned_response_body(response);
    clear_owned_response_content_type(response);
    response->owned_body = payload;
    response->status = status;
    response->body = payload;
    response->body_length = (size_t)(cursor - payload);
    response->content_type = content_type;
    return SS_HTTP_OK;
}

const char *ss_http_request_method(const SSHttpRequest *request) {
    return request != NULL ? request->method : NULL;
}

const char *ss_http_request_path(const SSHttpRequest *request) {
    return request != NULL ? request->path : NULL;
}

const char *ss_http_request_header(const SSHttpRequest *request, const char *name) {
    size_t index;

    if (request == NULL || name == NULL) {
        return NULL;
    }

    for (index = 0; index < request->header_count; ++index) {
        if (request->headers[index].name != NULL &&
                ascii_case_equal(request->headers[index].name, name)) {
            return request->headers[index].value;
        }
    }

    return NULL;
}

const char *ss_http_request_path_param(const SSHttpRequest *request, const char *name) {
    size_t index;
    if (request == NULL || name == NULL) {
        return NULL;
    }
    for (index = 0; index < request->path_param_count; ++index) {
        if (request->path_params[index].name != NULL
            && strcmp(request->path_params[index].name, name) == 0) {
            return request->path_params[index].value;
        }
    }
    return NULL;
}

/* Cookie value scratch — sized so a 32-byte session token base64url
 * (43 chars) fits with ample headroom. Anything longer than this is
 * refused rather than truncated; see the header doc for the rationale. */
#define SS_HTTP_COOKIE_VALUE_MAX 256
static char g_http_cookie_value_scratch[SS_HTTP_COOKIE_VALUE_MAX];

const char *ss_http_request_cookie(const SSHttpRequest *request, const char *cookie_name) {
    if (request == NULL || cookie_name == NULL) {
        return NULL;
    }
    const char *cookie_header = ss_http_request_header(request, "cookie");
    if (cookie_header == NULL) {
        return NULL;
    }
    size_t name_length = strlen(cookie_name);
    if (name_length == 0) return NULL;

    const char *scan = cookie_header;
    while (*scan != '\0') {
        /* Skip leading whitespace + semicolons between cookie pairs. */
        while (*scan == ' ' || *scan == '\t' || *scan == ';') {
            ++scan;
        }
        if (*scan == '\0') return NULL;

        const char *pair_name_start = scan;
        while (*scan != '\0' && *scan != '=' && *scan != ';') {
            ++scan;
        }
        size_t pair_name_length = (size_t)(scan - pair_name_start);
        const char *pair_value_start = "";
        size_t pair_value_length = 0;
        if (*scan == '=') {
            ++scan;
            pair_value_start = scan;
            while (*scan != '\0' && *scan != ';') {
                ++scan;
            }
            pair_value_length = (size_t)(scan - pair_value_start);
        }
        if (pair_name_length == name_length
            && memcmp(pair_name_start, cookie_name, name_length) == 0) {
            if (pair_value_length == 0) return "";
            if (pair_value_length >= SS_HTTP_COOKIE_VALUE_MAX) {
                /* Refuse to truncate — caller treats this as "absent" so
                 * an oversize attacker-controlled cookie doesn't pass an
                 * incomplete prefix into the session lookup. */
                return NULL;
            }
            memcpy(g_http_cookie_value_scratch, pair_value_start, pair_value_length);
            g_http_cookie_value_scratch[pair_value_length] = '\0';
            return g_http_cookie_value_scratch;
        }
    }
    return NULL;
}

/* ----- ss_http_response_file ----- */

#define SS_HTTP_FILE_MAX_BYTES (16 * 1024 * 1024)

static int response_file_path_is_safe(const char *requested_relative_path) {
    if (requested_relative_path == NULL || requested_relative_path[0] == '\0') {
        return 0;
    }
    /* Absolute paths refused. */
    if (requested_relative_path[0] == '/'
        || requested_relative_path[0] == '\\') {
        return 0;
    }
#ifdef _WIN32
    /* Drive-letter prefix refused (`C:`, `d:` etc.). */
    if (requested_relative_path[1] == ':' && requested_relative_path[2] != '\0') {
        return 0;
    }
#endif
    /* Walk the path checking each segment for `..`. We don't need to
     * normalize; any literal `..` segment is refused regardless of
     * surrounding context (so even `static/foo/../../etc/passwd`
     * fails the moment we see the first `..`). */
    const char *segment_start = requested_relative_path;
    const char *scan = requested_relative_path;
    while (1) {
        if (*scan == '/' || *scan == '\\' || *scan == '\0') {
            size_t seg_length = (size_t)(scan - segment_start);
            if (seg_length == 2
                && segment_start[0] == '.'
                && segment_start[1] == '.') {
                return 0;
            }
            if (*scan == '\0') break;
            segment_start = scan + 1;
        }
        ++scan;
    }
    return 1;
}

static const char *content_type_for_extension(const char *path) {
    const char *dot = strrchr(path, '.');
    if (dot == NULL || dot[1] == '\0') {
        return "application/octet-stream";
    }
    /* Lowercase compare for the well-known web extensions. */
    const char *ext = dot + 1;
    if (ascii_case_equal(ext, "html") || ascii_case_equal(ext, "htm")) {
        return "text/html; charset=utf-8";
    }
    if (ascii_case_equal(ext, "css"))  return "text/css; charset=utf-8";
    if (ascii_case_equal(ext, "js"))   return "text/javascript; charset=utf-8";
    if (ascii_case_equal(ext, "json")) return "application/json; charset=utf-8";
    if (ascii_case_equal(ext, "svg"))  return "image/svg+xml";
    if (ascii_case_equal(ext, "png"))  return "image/png";
    if (ascii_case_equal(ext, "jpg") || ascii_case_equal(ext, "jpeg")) {
        return "image/jpeg";
    }
    if (ascii_case_equal(ext, "gif"))  return "image/gif";
    if (ascii_case_equal(ext, "webp")) return "image/webp";
    if (ascii_case_equal(ext, "ico"))  return "image/x-icon";
    if (ascii_case_equal(ext, "txt"))  return "text/plain; charset=utf-8";
    if (ascii_case_equal(ext, "woff2")) return "font/woff2";
    if (ascii_case_equal(ext, "woff"))  return "font/woff";
    return "application/octet-stream";
}

int ss_http_response_file(
    SSHttpResponse *response,
    int status,
    const char *root_directory,
    const char *requested_relative_path
) {
    if (response == NULL || root_directory == NULL
        || requested_relative_path == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }
    if (!response_file_path_is_safe(requested_relative_path)) {
        return SS_HTTP_ERR_CONFIG;
    }

    char absolute_path[1024];
    int written = snprintf(absolute_path, sizeof(absolute_path),
                           "%s/%s", root_directory, requested_relative_path);
    if (written < 0 || written >= (int)sizeof(absolute_path)) {
        return SS_HTTP_ERR_CONFIG;
    }

    FILE *file_handle = fopen(absolute_path, "rb");
    if (file_handle == NULL) {
        return SS_HTTP_ERR_ENGINE;
    }
    if (fseek(file_handle, 0, SEEK_END) != 0) {
        fclose(file_handle);
        return SS_HTTP_ERR_ENGINE;
    }
    long file_size = ftell(file_handle);
    if (file_size < 0 || file_size > SS_HTTP_FILE_MAX_BYTES) {
        fclose(file_handle);
        return SS_HTTP_ERR_CONFIG;
    }
    if (fseek(file_handle, 0, SEEK_SET) != 0) {
        fclose(file_handle);
        return SS_HTTP_ERR_ENGINE;
    }

    char *body_bytes = (char *)malloc((size_t)file_size + 1);
    if (body_bytes == NULL) {
        fclose(file_handle);
        return SS_HTTP_ERR_ENGINE;
    }
    size_t bytes_read = fread(body_bytes, 1, (size_t)file_size, file_handle);
    fclose(file_handle);
    if (bytes_read != (size_t)file_size) {
        free(body_bytes);
        return SS_HTTP_ERR_ENGINE;
    }
    body_bytes[file_size] = '\0';

    /* Free the previous owned body if any, then take ownership. The
     * response dispatch path frees owned_body after sending. */
    clear_owned_response_body(response);
    clear_owned_response_content_type(response);
    response->status = status;
    response->content_type = content_type_for_extension(requested_relative_path);
    response->body = body_bytes;
    response->body_length = (size_t)file_size;
    response->owned_body = body_bytes;
    return SS_HTTP_OK;
}

/* ----- ss_http_now_millis ----- */

long long ss_http_now_millis(void) {
#ifdef _WIN32
    FILETIME file_time;
    GetSystemTimeAsFileTime(&file_time);
    /* FILETIME is 100ns intervals since 1601-01-01. Convert to
     * milliseconds since 1970-01-01. */
    ULARGE_INTEGER as_uint64;
    as_uint64.LowPart  = file_time.dwLowDateTime;
    as_uint64.HighPart = file_time.dwHighDateTime;
    static const long long epoch_offset_100ns_units = 116444736000000000LL;
    long long since_unix_epoch_100ns = (long long)as_uint64.QuadPart - epoch_offset_100ns_units;
    return since_unix_epoch_100ns / 10000LL;
#else
    struct timespec now_ts;
    if (clock_gettime(CLOCK_REALTIME, &now_ts) != 0) {
        return 0;
    }
    return (long long)now_ts.tv_sec * 1000LL
         + (long long)(now_ts.tv_nsec / 1000000L);
#endif
}

/* ----- outbound HTTP/1.1 client (ss_http_client_fetch) -----
 *
 * A minimal blocking HTTP/1.1 client so SemanticScript apps can call other
 * services over HTTP (the runtime previously exposed only the server side).
 * Connects to host:port, sends `method path` with a Host header, an optional
 * caller-supplied header line (e.g. "Authorization: Bearer ..."), and an
 * optional JSON body, then reads the whole response (Connection: close).
 *
 * Returns a malloc'd, null-terminated copy of the RESPONSE BODY on a 2xx
 * status, or NULL on transport error / non-2xx. The caller owns the buffer and
 * must free it (c.free). Does not handle chunked transfer-encoding; the bundled
 * native server replies with Content-Length + close, which this reads in full. */
#ifdef _WIN32
static int ss_http_client_winsock_ready(void) {
    static int initialized = 0;
    if (!initialized) {
        WSADATA wsa_data;
        if (WSAStartup(MAKEWORD(2, 2), &wsa_data) != 0) {
            return 0;
        }
        initialized = 1;
    }
    return 1;
}
#endif

static char *ss_http_client_dup(const char *text) {
    size_t length = strlen(text);
    char *copy = (char *)malloc(length + 1);
    if (copy == NULL) {
        return NULL;
    }
    memcpy(copy, text, length + 1);
    return copy;
}

const char *ss_http_client_fetch(
    const char *method,
    const char *host,
    int port,
    const char *path,
    const char *header_line,
    const char *body
) {
    if (method == NULL || host == NULL || path == NULL) {
        return NULL;
    }
#ifdef _WIN32
    if (!ss_http_client_winsock_ready()) {
        return NULL;
    }
#endif

    char port_text[16];
    snprintf(port_text, sizeof(port_text), "%d", port);

    struct addrinfo hints;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    struct addrinfo *resolved = NULL;
    if (getaddrinfo(host, port_text, &hints, &resolved) != 0 || resolved == NULL) {
        return NULL;
    }

    ss_socket_t client_socket = SS_INVALID_SOCKET;
    for (struct addrinfo *candidate = resolved; candidate != NULL; candidate = candidate->ai_next) {
        client_socket = socket(candidate->ai_family, candidate->ai_socktype, candidate->ai_protocol);
        if (client_socket == SS_INVALID_SOCKET) {
            continue;
        }
        if (connect(client_socket, candidate->ai_addr, (int)candidate->ai_addrlen) == 0) {
            break;
        }
        ss_close_socket(client_socket);
        client_socket = SS_INVALID_SOCKET;
    }
    freeaddrinfo(resolved);
    if (client_socket == SS_INVALID_SOCKET) {
        return NULL;
    }

    /* Bound the blocking calls so a hung upstream cannot freeze the single
     * server thread indefinitely (review N2). */
#ifdef _WIN32
    DWORD client_timeout_ms = 5000;
    setsockopt(client_socket, SOL_SOCKET, SO_RCVTIMEO, (const char *)&client_timeout_ms, sizeof(client_timeout_ms));
    setsockopt(client_socket, SOL_SOCKET, SO_SNDTIMEO, (const char *)&client_timeout_ms, sizeof(client_timeout_ms));
#else
    struct timeval client_timeout;
    client_timeout.tv_sec = 5;
    client_timeout.tv_usec = 0;
    setsockopt(client_socket, SOL_SOCKET, SO_RCVTIMEO, &client_timeout, sizeof(client_timeout));
    setsockopt(client_socket, SOL_SOCKET, SO_SNDTIMEO, &client_timeout, sizeof(client_timeout));
#endif

    const char *body_text = body ? body : "";
    size_t body_length = strlen(body_text);
    int has_body = body_length > 0;

    size_t request_capacity = strlen(method) + strlen(path) + strlen(host)
        + (header_line ? strlen(header_line) : 0) + body_length + 256;
    char *request = (char *)malloc(request_capacity);
    if (request == NULL) {
        ss_close_socket(client_socket);
        return NULL;
    }
    int written = snprintf(request, request_capacity,
        "%s %s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n",
        method, path, host);
    if (header_line != NULL && header_line[0] != '\0') {
        written += snprintf(request + written, request_capacity - (size_t)written,
            "%s\r\n", header_line);
    }
    if (has_body) {
        written += snprintf(request + written, request_capacity - (size_t)written,
            "Content-Type: application/json\r\nContent-Length: %zu\r\n\r\n%s",
            body_length, body_text);
    } else {
        written += snprintf(request + written, request_capacity - (size_t)written, "\r\n");
    }

    size_t sent_total = 0;
    int send_failed = 0;
    while (sent_total < (size_t)written) {
        int sent_now = send(client_socket, request + sent_total, (int)((size_t)written - sent_total), 0);
        if (sent_now <= 0) {
            send_failed = 1;
            break;
        }
        sent_total += (size_t)sent_now;
    }
    free(request);
    if (send_failed) {
        ss_close_socket(client_socket);
        return NULL;
    }

    size_t response_capacity = 8192;
    size_t response_length = 0;
    char *response = (char *)malloc(response_capacity);
    if (response == NULL) {
        ss_close_socket(client_socket);
        return NULL;
    }
    for (;;) {
        if (response_length + 4096 >= response_capacity) {
            size_t next_capacity = response_capacity * 2;
            char *grown = (char *)realloc(response, next_capacity);
            if (grown == NULL) {
                free(response);
                ss_close_socket(client_socket);
                return NULL;
            }
            response = grown;
            response_capacity = next_capacity;
        }
        int read_now = recv(client_socket, response + response_length,
            (int)(response_capacity - response_length - 1), 0);
        if (read_now <= 0) {
            break;
        }
        response_length += (size_t)read_now;
    }
    ss_close_socket(client_socket);
    response[response_length] = '\0';

    int status_code = 0;
    /* Only trust the status line when the response actually begins with the
     * HTTP version token (review S2). */
    if (response_length >= 5 && strncmp(response, "HTTP/", 5) == 0) {
        const char *status_space = strchr(response, ' ');
        if (status_space != NULL) {
            status_code = atoi(status_space + 1);
        }
    }

    char *body_start = strstr(response, "\r\n\r\n");
    char *result = NULL;
    if (body_start != NULL && status_code >= 200 && status_code < 300) {
        result = ss_http_client_dup(body_start + 4);
    }
    free(response);
    return result;
}

/* ----- ss_http_html_escape -----
 * Escape the HTML special characters & < > " ' into entities, writing into the
 * caller's bounded scratch buffer (always null-terminated; truncates rather
 * than overflows). Returns the scratch pointer, or NULL on bad args. Used by
 * SSR clients to render untrusted text into HTML safely. */
const char *ss_http_html_escape(const char *input, char *out, int out_capacity) {
    if (input == NULL || out == NULL || out_capacity <= 0) {
        return NULL;
    }
    int oi = 0;
    for (int i = 0; input[i] != '\0'; i++) {
        const char *replacement = NULL;
        int replacement_length = 0;
        switch (input[i]) {
            case '&': replacement = "&amp;"; replacement_length = 5; break;
            case '<': replacement = "&lt;"; replacement_length = 4; break;
            case '>': replacement = "&gt;"; replacement_length = 4; break;
            case '"': replacement = "&quot;"; replacement_length = 6; break;
            case '\'': replacement = "&#39;"; replacement_length = 5; break;
            default: break;
        }
        if (replacement != NULL) {
            if (oi + replacement_length >= out_capacity) {
                break;
            }
            memcpy(out + oi, replacement, (size_t)replacement_length);
            oi += replacement_length;
        } else {
            if (oi + 1 >= out_capacity) {
                break;
            }
            out[oi++] = input[i];
        }
    }
    out[oi] = '\0';
    return out;
}

/* ----- ss_http_filesystem_ensure_directory ----- */

/* ----- ss_http_form_find_field ----- */

static int hex_to_nibble(char c, int *out) {
    if (c >= '0' && c <= '9') { *out = c - '0'; return 1; }
    if (c >= 'a' && c <= 'f') { *out = 10 + (c - 'a'); return 1; }
    if (c >= 'A' && c <= 'F') { *out = 10 + (c - 'A'); return 1; }
    return 0;
}

const char *ss_http_form_find_field(
    const char *body_text,
    const char *field_name,
    char *scratch_buffer,
    size_t scratch_capacity
) {
    if (body_text == NULL || field_name == NULL
        || scratch_buffer == NULL || scratch_capacity == 0) {
        return NULL;
    }
    size_t name_length = strlen(field_name);
    if (name_length == 0) return NULL;

    const char *scan = body_text;
    while (*scan != '\0') {
        /* Skip leading separator (& or initial position). */
        while (*scan == '&') ++scan;
        if (*scan == '\0') return NULL;

        const char *pair_name_start = scan;
        while (*scan != '\0' && *scan != '=' && *scan != '&') ++scan;
        size_t pair_name_length = (size_t)(scan - pair_name_start);
        const char *pair_value_start = "";
        const char *pair_value_end = pair_value_start;
        if (*scan == '=') {
            ++scan;
            pair_value_start = scan;
            while (*scan != '\0' && *scan != '&') ++scan;
            pair_value_end = scan;
        }
        if (pair_name_length == name_length
            && memcmp(pair_name_start, field_name, name_length) == 0) {
            /* Decode value into scratch. `+` -> space, `%XX` -> byte. */
            size_t written = 0;
            const char *src = pair_value_start;
            while (src < pair_value_end) {
                if (written + 1 >= scratch_capacity) return NULL;
                char c = *src;
                if (c == '+') {
                    scratch_buffer[written++] = ' ';
                    ++src;
                } else if (c == '%' && (pair_value_end - src) >= 3) {
                    int hi = 0, lo = 0;
                    if (!hex_to_nibble(src[1], &hi)) return NULL;
                    if (!hex_to_nibble(src[2], &lo)) return NULL;
                    scratch_buffer[written++] = (char)((hi << 4) | lo);
                    src += 3;
                } else if (c == '%') {
                    /* Truncated escape — refuse rather than emit garbage. */
                    return NULL;
                } else {
                    scratch_buffer[written++] = c;
                    ++src;
                }
            }
            scratch_buffer[written] = '\0';
            return scratch_buffer;
        }
    }
    return NULL;
}

int ss_http_filesystem_ensure_directory(const char *directory_path) {
    if (directory_path == NULL || directory_path[0] == '\0') {
        return SS_HTTP_ERR_CONFIG;
    }
#ifdef _WIN32
    if (CreateDirectoryA(directory_path, NULL) == 0) {
        DWORD last_error = GetLastError();
        if (last_error != ERROR_ALREADY_EXISTS) {
            return SS_HTTP_ERR_ENGINE;
        }
    }
    return SS_HTTP_OK;
#else
    if (mkdir(directory_path, 0755) != 0) {
        if (errno != EEXIST) {
            return SS_HTTP_ERR_ENGINE;
        }
    }
    return SS_HTTP_OK;
#endif
}

const char *ss_http_request_query_param(const SSHttpRequest *request, const char *name) {
    size_t index;

    if (request == NULL || name == NULL) {
        return NULL;
    }

    for (index = 0; index < request->query_param_count; ++index) {
        if (request->query_params[index].name != NULL &&
                strcmp(request->query_params[index].name, name) == 0) {
            return request->query_params[index].value;
        }
    }

    return NULL;
}

const char *ss_http_request_body_text(const SSHttpRequest *request) {
    if (request == NULL || request->body == NULL) {
        return "";
    }
    return request->body;
}

const void *ss_http_request_body_bytes(const SSHttpRequest *request) {
    if (request == NULL || request->body == NULL) {
        return NULL;
    }
    return request->body;
}

size_t ss_http_request_body_length(const SSHttpRequest *request) {
    return request != NULL ? request->body_length : 0;
}

static const char *find_bytes(
    const char *haystack,
    size_t haystack_length,
    const char *needle,
    size_t needle_length
) {
    size_t index;

    if (needle_length == 0 || haystack_length < needle_length) {
        return NULL;
    }
    for (index = 0; index <= haystack_length - needle_length; ++index) {
        if (memcmp(haystack + index, needle, needle_length) == 0) {
            return haystack + index;
        }
    }
    return NULL;
}

static const char *find_multipart_header_end(
    const char *buffer,
    size_t buffer_length,
    size_t *header_text_length_out,
    size_t *header_separator_length_out
) {
    const char *end = find_bytes(buffer, buffer_length, "\r\n\r\n", 4);
    if (end != NULL) {
        *header_text_length_out = (size_t)(end - buffer);
        *header_separator_length_out = 4;
        return end;
    }

    end = find_bytes(buffer, buffer_length, "\n\n", 2);
    if (end != NULL) {
        *header_text_length_out = (size_t)(end - buffer);
        *header_separator_length_out = 2;
        return end;
    }

    *header_text_length_out = 0;
    *header_separator_length_out = 0;
    return NULL;
}

static const char *find_next_multipart_boundary(
    const char *body,
    size_t body_length,
    const char *boundary_marker,
    size_t boundary_marker_length,
    size_t *line_prefix_length_out
) {
    const char *candidate = body;
    size_t remaining = body_length;

    while (remaining >= boundary_marker_length + 1) {
        const char *marker = find_bytes(candidate, remaining, boundary_marker, boundary_marker_length);
        if (marker == NULL) {
            break;
        }
        if (marker > body && marker[-1] == '\n') {
            if (marker > body + 1 && marker[-2] == '\r') {
                *line_prefix_length_out = 2;
                return marker - 2;
            }
            *line_prefix_length_out = 1;
            return marker - 1;
        }
        remaining -= (size_t)(marker + 1 - candidate);
        candidate = marker + 1;
    }

    *line_prefix_length_out = 0;
    return NULL;
}

static int extract_boundary_value(
    const char *content_type,
    char *boundary_out,
    size_t boundary_capacity
) {
    const char *boundary;
    const char *cursor;
    size_t length = 0;

    if (content_type == NULL || boundary_out == NULL || boundary_capacity == 0) {
        return 0;
    }

    boundary = strstr(content_type, "boundary=");
    if (boundary == NULL) {
        return 0;
    }
    cursor = boundary + strlen("boundary=");
    if (*cursor == '"') {
        ++cursor;
        while (cursor[length] != '\0' && cursor[length] != '"' && length + 1 < boundary_capacity) {
            ++length;
        }
    } else {
        while (cursor[length] != '\0' &&
                cursor[length] != ';' &&
                cursor[length] != ' ' &&
                cursor[length] != '\t' &&
                length + 1 < boundary_capacity) {
            ++length;
        }
    }

    if (length == 0 || length + 1 >= boundary_capacity) {
        return 0;
    }
    memcpy(boundary_out, cursor, length);
    boundary_out[length] = '\0';
    return 1;
}

static char *extract_quoted_header_parameter(char *header_value, const char *parameter_name) {
    char pattern[64];
    char *start;
    char *end;
    int pattern_length;

    if (header_value == NULL || parameter_name == NULL) {
        return NULL;
    }
    pattern_length = snprintf(pattern, sizeof(pattern), "%s=\"", parameter_name);
    if (pattern_length <= 0 || (size_t)pattern_length >= sizeof(pattern)) {
        return NULL;
    }
    start = strstr(header_value, pattern);
    if (start == NULL) {
        return NULL;
    }
    start += pattern_length;
    end = strchr(start, '"');
    if (end == NULL) {
        return NULL;
    }
    *end = '\0';
    return start;
}

static void extract_part_header_values(
    char *headers,
    char **content_disposition_out,
    char **content_type_out
) {
    char *cursor = headers;

    *content_disposition_out = NULL;
    *content_type_out = NULL;

    while (cursor != NULL && *cursor != '\0') {
        char *line = cursor;
        char *line_end = strchr(line, '\n');
        char *colon;
        char *name;
        char *value;

        if (line_end != NULL) {
            *line_end = '\0';
            cursor = line_end + 1;
        } else {
            cursor = NULL;
        }
        trim_right(line);
        name = trim_left(line);
        colon = strchr(name, ':');
        if (colon == NULL) {
            continue;
        }
        *colon = '\0';
        trim_right(name);
        value = trim_left(colon + 1);
        trim_right(value);
        if (ascii_case_equal(name, "Content-Disposition")) {
            *content_disposition_out = value;
        } else if (ascii_case_equal(name, "Content-Type")) {
            *content_type_out = value;
        }
    }
}

static void parse_multipart_request(SSHttpRequest *request) {
    char boundary[SS_HTTP_MULTIPART_BOUNDARY_MAX];
    char boundary_marker[SS_HTTP_MULTIPART_BOUNDARY_MAX + 2];
    size_t boundary_marker_length;
    const char *content_type;
    const char *cursor;
    const char *body_end;

    if (request == NULL || request->multipart_parsed) {
        return;
    }
    request->multipart_parsed = 1;

    content_type = ss_http_request_header(request, "Content-Type");
    if (content_type == NULL ||
            !ascii_case_prefix_equal(content_type, "multipart/form-data") ||
            !extract_boundary_value(content_type, boundary, sizeof(boundary))) {
        return;
    }

    boundary_marker[0] = '-';
    boundary_marker[1] = '-';
    strcpy(boundary_marker + 2, boundary);
    boundary_marker_length = strlen(boundary_marker);
    cursor = request->body;
    body_end = request->body + request->body_length;

    while (cursor != NULL &&
            cursor < body_end &&
            request->multipart_part_count < SS_HTTP_MAX_MULTIPART_PARTS) {
        const char *marker = find_bytes(
            cursor,
            (size_t)(body_end - cursor),
            boundary_marker,
            boundary_marker_length
        );
        const char *part_header_start;
        const char *part_header_end;
        const char *part_body_start;
        const char *next_boundary_line;
        size_t header_text_length = 0;
        size_t header_separator_length = 0;
        size_t line_prefix_length = 0;
        char *headers_mutable;
        char *disposition;
        char *part_name;
        char *part_filename;
        char *part_content_type;
        SSHttpMultipartPart *part;

        if (marker == NULL) {
            return;
        }
        marker += boundary_marker_length;
        if (marker + 1 < body_end && marker[0] == '-' && marker[1] == '-') {
            return;
        }
        if (marker + 1 < body_end && marker[0] == '\r' && marker[1] == '\n') {
            part_header_start = marker + 2;
        } else if (marker < body_end && marker[0] == '\n') {
            part_header_start = marker + 1;
        } else {
            cursor = marker;
            continue;
        }

        part_header_end = find_multipart_header_end(
            part_header_start,
            (size_t)(body_end - part_header_start),
            &header_text_length,
            &header_separator_length
        );
        if (part_header_end == NULL) {
            return;
        }
        part_body_start = part_header_end + header_separator_length;
        next_boundary_line = find_next_multipart_boundary(
            part_body_start,
            (size_t)(body_end - part_body_start),
            boundary_marker,
            boundary_marker_length,
            &line_prefix_length
        );
        if (next_boundary_line == NULL) {
            return;
        }

        headers_mutable = (char *)part_header_start;
        headers_mutable[header_text_length] = '\0';
        extract_part_header_values(headers_mutable, &disposition, &part_content_type);
        if (disposition == NULL) {
            cursor = next_boundary_line + line_prefix_length;
            continue;
        }

        part_filename = extract_quoted_header_parameter(disposition, "filename");
        part_name = extract_quoted_header_parameter(disposition, "name");
        if (part_name == NULL || *part_name == '\0') {
            cursor = next_boundary_line + line_prefix_length;
            continue;
        }
        ((char *)next_boundary_line)[0] = '\0';

        part = &request->multipart_parts[request->multipart_part_count];
        part->name = part_name;
        part->filename = part_filename != NULL ? part_filename : "";
        part->content_type = part_content_type != NULL ? part_content_type : "";
        part->body = part_body_start;
        part->body_length = (size_t)(next_boundary_line - part_body_start);
        ++request->multipart_part_count;

        cursor = next_boundary_line + line_prefix_length;
    }
}

static const SSHttpMultipartPart *find_multipart_part(SSHttpRequest *request, const char *name) {
    size_t index;

    if (request == NULL || name == NULL) {
        return NULL;
    }
    parse_multipart_request(request);
    for (index = 0; index < request->multipart_part_count; ++index) {
        if (request->multipart_parts[index].name != NULL &&
                strcmp(request->multipart_parts[index].name, name) == 0) {
            return &request->multipart_parts[index];
        }
    }
    return NULL;
}

const char *ss_http_multipart_part_text(SSHttpRequest *request, const char *name) {
    const SSHttpMultipartPart *part = find_multipart_part(request, name);
    return part != NULL && part->body != NULL ? part->body : NULL;
}

const void *ss_http_multipart_part_bytes(SSHttpRequest *request, const char *name) {
    const SSHttpMultipartPart *part = find_multipart_part(request, name);
    return part != NULL ? part->body : NULL;
}

size_t ss_http_multipart_part_length(SSHttpRequest *request, const char *name) {
    const SSHttpMultipartPart *part = find_multipart_part(request, name);
    return part != NULL ? part->body_length : 0;
}

const char *ss_http_multipart_part_filename(SSHttpRequest *request, const char *name) {
    const SSHttpMultipartPart *part = find_multipart_part(request, name);
    return part != NULL && part->filename != NULL ? part->filename : NULL;
}

const char *ss_http_multipart_part_content_type(SSHttpRequest *request, const char *name) {
    const SSHttpMultipartPart *part = find_multipart_part(request, name);
    return part != NULL && part->content_type != NULL ? part->content_type : NULL;
}

static int is_valid_header_name(const char *name) {
    const unsigned char *cursor = (const unsigned char *)name;

    if (name == NULL || *name == '\0') {
        return 0;
    }

    while (*cursor != '\0') {
        if (!(isalnum(*cursor) || *cursor == '-' || *cursor == '_')) {
            return 0;
        }
        ++cursor;
    }

    return 1;
}

static int is_valid_header_value(const char *value) {
    if (value == NULL) {
        return 0;
    }
    return strchr(value, '\r') == NULL && strchr(value, '\n') == NULL;
}

int ss_http_response_header(
    SSHttpResponse *response,
    const char *name,
    const char *value
) {
    char *owned_name;
    char *owned_value;

    if (response == NULL ||
            !is_valid_header_name(name) ||
            !is_valid_header_value(value) ||
            ascii_case_equal(name, "Content-Length") ||
            ascii_case_equal(name, "Connection") ||
            ascii_case_equal(name, "Content-Type") ||
            response->header_count >= SS_HTTP_MAX_HEADERS) {
        return SS_HTTP_ERR_CONFIG;
    }

    owned_name = copy_c_string(name);
    owned_value = copy_c_string(value);
    if (owned_name == NULL || owned_value == NULL) {
        free(owned_name);
        free(owned_value);
        return SS_HTTP_ERR_ENGINE;
    }

    response->owned_header_names[response->header_count] = owned_name;
    response->owned_header_values[response->header_count] = owned_value;
    response->headers[response->header_count].name = owned_name;
    response->headers[response->header_count].value = owned_value;
    ++response->header_count;
    return SS_HTTP_OK;
}

#ifdef SEM_HTTP_WITH_H2O

#include "h2o.h"

int ss_http_server_run(const SSHttpServerConfig *config) {
    if (!has_valid_route_table(config)) {
        return SS_HTTP_ERR_CONFIG;
    }

    /*
     * The H2O include path is wired behind SEM_HTTP_WITH_H2O, but the actual
     * socket accept loop and h2o_context_t lifecycle are intentionally staged
     * behind the stable ABI. The next patch should replace this explicit
     * unavailable return with libh2o-evloop setup.
     */
    (void)config;
    return SS_HTTP_ERR_RUNTIME_UNAVAILABLE;
}

#else

static const char *find_header_end(const char *buffer, size_t read_count, size_t *header_bytes_out) {
    const char *end = strstr(buffer, "\r\n\r\n");
    if (end != NULL) {
        *header_bytes_out = (size_t)(end - buffer) + 4;
        return end + 4;
    }

    end = strstr(buffer, "\n\n");
    if (end != NULL) {
        *header_bytes_out = (size_t)(end - buffer) + 2;
        return end + 2;
    }

    (void)read_count;
    *header_bytes_out = 0;
    return NULL;
}

static long parse_content_length(const char *buffer, const char *header_end) {
    const char *line = buffer;

    while (line < header_end && *line != '\0') {
        const char *line_end = strstr(line, "\n");
        if (line_end == NULL || line_end > header_end) {
            line_end = header_end;
        }

        while (*line == '\r' || *line == '\n') {
            ++line;
        }

        if (ascii_case_prefix_equal(line, "Content-Length:")) {
            const char *value = line + strlen("Content-Length:");
            while (*value == ' ' || *value == '\t') {
                ++value;
            }
            return strtol(value, NULL, 10);
        }

        line = line_end;
        while (*line == '\r' || *line == '\n') {
            ++line;
        }
    }

    return 0;
}

static void parse_query_params(char *query, SSHttpRequest *request) {
    char *cursor = query;

    if (query == NULL || request == NULL) {
        return;
    }

    while (*cursor != '\0' && request->query_param_count < SS_HTTP_MAX_QUERY_PARAMS) {
        char *pair = cursor;
        char *separator = strchr(pair, '&');
        char *equals;

        if (separator != NULL) {
            *separator = '\0';
            cursor = separator + 1;
        } else {
            cursor = pair + strlen(pair);
        }

        if (*pair == '\0') {
            continue;
        }

        equals = strchr(pair, '=');
        if (equals != NULL) {
            *equals = '\0';
            request->query_params[request->query_param_count].name = pair;
            request->query_params[request->query_param_count].value = equals + 1;
        } else {
            request->query_params[request->query_param_count].name = pair;
            request->query_params[request->query_param_count].value = "";
        }
        ++request->query_param_count;
    }
}

static void parse_headers(char *header_start, char *body_start, SSHttpRequest *request) {
    char *cursor = header_start;

    while (cursor != NULL && cursor < body_start && request->header_count < SS_HTTP_MAX_HEADERS) {
        char *line = trim_left(cursor);
        char *line_end;
        char *colon;
        char *name;
        char *value;

        if (line >= body_start || *line == '\0') {
            break;
        }

        line_end = memchr(line, '\n', (size_t)(body_start - line));
        if (line_end == NULL) {
            line_end = body_start;
        }
        cursor = line_end + (line_end < body_start ? 1 : 0);
        *line_end = '\0';
        trim_right(line);

        if (*line == '\0') {
            break;
        }

        colon = strchr(line, ':');
        if (colon == NULL) {
            continue;
        }

        *colon = '\0';
        name = trim_left(line);
        trim_right(name);
        value = trim_left(colon + 1);
        trim_right(value);
        if (*name == '\0') {
            continue;
        }

        request->headers[request->header_count].name = name;
        request->headers[request->header_count].value = value;
        ++request->header_count;
    }
}

static const char *reason_phrase_for_status(int status) {
    switch (status) {
    case 200:
        return "OK";
    case 201:
        return "Created";
    case 204:
        return "No Content";
    case 302:
        return "Found";
    case 400:
        return "Bad Request";
    case 401:
        return "Unauthorized";
    case 403:
        return "Forbidden";
    case 404:
        return "Not Found";
    case 405:
        return "Method Not Allowed";
    case 413:
        return "Payload Too Large";
    case 500:
        return "Internal Server Error";
    case 503:
        return "Service Unavailable";
    default:
        return "OK";
    }
}

static int send_all(ss_socket_t socket_handle, const char *data, size_t byte_count) {
    size_t sent_count = 0;

    while (sent_count < byte_count) {
        int chunk_count = send(
            socket_handle,
            data + sent_count,
            (int)(byte_count - sent_count),
            0
        );
        if (chunk_count <= 0) {
            return SS_HTTP_ERR_ENGINE;
        }
        sent_count += (size_t)chunk_count;
    }

    return SS_HTTP_OK;
}

static int send_response(
    ss_socket_t socket_handle,
    int status,
    const char *content_type,
    const char *body,
    const SSHttpResponse *response
) {
    char header[512];
    size_t body_length =
        response != NULL && body != NULL && response->body == body
            ? response->body_length
            : (body != NULL ? strlen(body) : 0);
    size_t index;
    int header_length = snprintf(
        header,
        sizeof(header),
        "HTTP/1.1 %d %s\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %zu\r\n"
        "Connection: close\r\n",
        status,
        reason_phrase_for_status(status),
        content_type != NULL ? content_type : "text/plain; charset=utf-8",
        body_length
    );

    if (header_length <= 0 || (size_t)header_length >= sizeof(header)) {
        return SS_HTTP_ERR_ENGINE;
    }
    if (send_all(socket_handle, header, (size_t)header_length) != SS_HTTP_OK) {
        return SS_HTTP_ERR_ENGINE;
    }
    if (response != NULL) {
        for (index = 0; index < response->header_count; ++index) {
            const char *name = response->headers[index].name;
            const char *value = response->headers[index].value;
            if (name == NULL || value == NULL) {
                continue;
            }
            if (ascii_case_equal(name, "Content-Length") ||
                    ascii_case_equal(name, "Connection") ||
                    ascii_case_equal(name, "Content-Type")) {
                continue;
            }
            header_length = snprintf(header, sizeof(header), "%s: %s\r\n", name, value);
            if (header_length <= 0 || (size_t)header_length >= sizeof(header)) {
                return SS_HTTP_ERR_ENGINE;
            }
            if (send_all(socket_handle, header, (size_t)header_length) != SS_HTTP_OK) {
                return SS_HTTP_ERR_ENGINE;
            }
        }
    }
    if (send_all(socket_handle, "\r\n", 2) != SS_HTTP_OK) {
        return SS_HTTP_ERR_ENGINE;
    }
    if (body_length > 0 && send_all(socket_handle, body, body_length) != SS_HTTP_OK) {
        return SS_HTTP_ERR_ENGINE;
    }

    return SS_HTTP_OK;
}

static SSHttpResponseBackend *response_backend(SSHttpResponse *response) {
    if (response == NULL || response->backend_response == NULL) {
        return NULL;
    }
    return (SSHttpResponseBackend *)response->backend_response;
}

static int send_sse_headers(SSHttpResponse *response, int status) {
    SSHttpResponseBackend *backend = response_backend(response);
    char header[512];
    size_t index;
    int header_length;

    if (backend == NULL || backend->stream_started || backend->stream_closed) {
        return SS_HTTP_ERR_CONFIG;
    }

    header_length = snprintf(
        header,
        sizeof(header),
        "HTTP/1.1 %d %s\r\n"
        "Content-Type: text/event-stream; charset=utf-8\r\n"
        "Connection: close\r\n",
        status,
        reason_phrase_for_status(status)
    );
    if (header_length <= 0 || (size_t)header_length >= sizeof(header)) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }
    if (send_all(backend->socket_handle, header, (size_t)header_length) != SS_HTTP_OK) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }
    for (index = 0; index < response->header_count; ++index) {
        const char *name = response->headers[index].name;
        const char *value = response->headers[index].value;
        if (name == NULL || value == NULL) {
            continue;
        }
        if (ascii_case_equal(name, "Content-Length") ||
                ascii_case_equal(name, "Connection") ||
                ascii_case_equal(name, "Content-Type")) {
            continue;
        }
        header_length = snprintf(header, sizeof(header), "%s: %s\r\n", name, value);
        if (header_length <= 0 || (size_t)header_length >= sizeof(header)) {
            backend->stream_error = 1;
            return SS_HTTP_ERR_ENGINE;
        }
        if (send_all(backend->socket_handle, header, (size_t)header_length) != SS_HTTP_OK) {
            backend->stream_error = 1;
            return SS_HTTP_ERR_ENGINE;
        }
    }
    if (send_all(backend->socket_handle, "\r\n", 2) != SS_HTTP_OK) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }
    backend->stream_started = 1;
    response->status = status;
    response->body = "";
    response->body_length = 0;
    response->content_type = "text/event-stream; charset=utf-8";
    return SS_HTTP_OK;
}

int ss_http_sse_open(SSHttpResponse *response, int status) {
    if (response == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }
    return send_sse_headers(response, status);
}

int ss_http_sse_write_event(
    SSHttpResponse *response,
    const char *event_name,
    const char *event_data
) {
    SSHttpResponseBackend *backend = response_backend(response);
    const char *event_prefix = "event: ";
    size_t event_name_length;
    size_t payload_length;
    char *payload;
    char *cursor;
    int status;

    if (backend == NULL || !backend->stream_started || backend->stream_closed ||
            !is_valid_sse_event_name(event_name) || event_data == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }

    event_name_length = strlen(event_name);
    payload_length =
        strlen(event_prefix) + event_name_length + 1 +
        sse_data_wire_length(event_data) +
        1;
    payload = (char *)malloc(payload_length + 1);
    if (payload == NULL) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }

    cursor = payload;
    memcpy(cursor, event_prefix, strlen(event_prefix));
    cursor += strlen(event_prefix);
    memcpy(cursor, event_name, event_name_length);
    cursor += event_name_length;
    *cursor++ = '\n';
    cursor = write_sse_data_lines(cursor, event_data);
    *cursor++ = '\n';
    *cursor = '\0';

    status = send_all(backend->socket_handle, payload, (size_t)(cursor - payload));
    free(payload);
    if (status != SS_HTTP_OK) {
        backend->stream_error = 1;
    }
    return status;
}

int ss_http_sse_write_event_with_id(
    SSHttpResponse *response,
    long long event_id,
    const char *event_name,
    const char *event_data
) {
    SSHttpResponseBackend *backend = response_backend(response);
    const char *id_prefix = "id: ";
    const char *event_prefix = "event: ";
    char id_buffer[32];
    int id_length;
    size_t event_name_length;
    size_t payload_length;
    char *payload;
    char *cursor;
    int status;

    if (backend == NULL || !backend->stream_started || backend->stream_closed ||
            event_id < 0 || !is_valid_sse_event_name(event_name) || event_data == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }

    id_length = snprintf(id_buffer, sizeof(id_buffer), "%lld", event_id);
    if (id_length <= 0 || (size_t)id_length >= sizeof(id_buffer)) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }

    event_name_length = strlen(event_name);
    payload_length =
        strlen(id_prefix) + (size_t)id_length + 1 +
        strlen(event_prefix) + event_name_length + 1 +
        sse_data_wire_length(event_data) +
        1;
    payload = (char *)malloc(payload_length + 1);
    if (payload == NULL) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }

    cursor = payload;
    memcpy(cursor, id_prefix, strlen(id_prefix));
    cursor += strlen(id_prefix);
    memcpy(cursor, id_buffer, (size_t)id_length);
    cursor += id_length;
    *cursor++ = '\n';
    memcpy(cursor, event_prefix, strlen(event_prefix));
    cursor += strlen(event_prefix);
    memcpy(cursor, event_name, event_name_length);
    cursor += event_name_length;
    *cursor++ = '\n';
    cursor = write_sse_data_lines(cursor, event_data);
    *cursor++ = '\n';
    *cursor = '\0';

    status = send_all(backend->socket_handle, payload, (size_t)(cursor - payload));
    free(payload);
    if (status != SS_HTTP_OK) {
        backend->stream_error = 1;
    }
    return status;
}

int ss_http_sse_heartbeat(SSHttpResponse *response, const char *comment) {
    SSHttpResponseBackend *backend = response_backend(response);
    const char *prefix = ": ";
    char buffer[256];
    int length;
    if (backend == NULL || !backend->stream_started || backend->stream_closed ||
            comment == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }
    if (strchr(comment, '\r') != NULL || strchr(comment, '\n') != NULL) {
        return SS_HTTP_ERR_CONFIG;
    }
    length = snprintf(buffer, sizeof(buffer), "%s%s\n\n", prefix, comment);
    if (length <= 0 || (size_t)length >= sizeof(buffer)) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }
    if (send_all(backend->socket_handle, buffer, (size_t)length) != SS_HTTP_OK) {
        backend->stream_error = 1;
        return SS_HTTP_ERR_ENGINE;
    }
    return SS_HTTP_OK;
}

int ss_http_sse_close(SSHttpResponse *response) {
    SSHttpResponseBackend *backend = response_backend(response);
    if (backend == NULL || !backend->stream_started) {
        return SS_HTTP_ERR_CONFIG;
    }
    backend->stream_closed = 1;
    return backend->stream_error ? SS_HTTP_ERR_ENGINE : SS_HTTP_OK;
}

int ss_http_client_disconnected(SSHttpResponse *response) {
    SSHttpResponseBackend *backend = response_backend(response);
    if (backend == NULL) {
        return 1;
    }
    return backend->stream_error ? 1 : 0;
}

/* -------------------------------------------------------------------
 * Pattern-route compilation.
 *
 * The route table is compiled into segments once at server startup so
 * each incoming request only does a cheap segment-walk + literal/param
 * comparison. Each ":name" segment in the route's path string becomes
 * a parametric slot whose name lives in a heap-allocated null-terminated
 * string; literal segments point into the original route->path text.
 *
 * Matching is order-preserving: routes are scanned in declaration order
 * and the first match wins. Callers who declare both `/api/todos` and
 * `/api/todos/:id` should put the literal one first if they want
 * `/api/todos` to short-circuit before `:id` captures the empty trailing
 * segment. The ABI header documents this contract on
 * ss_http_request_path_param.
 * ------------------------------------------------------------------- */

typedef struct SSCompiledRouteSegment {
    int is_param;            /* 0 = literal, 1 = :name capture */
    const char *literal;     /* literal segment text (points into route->path); not null-terminated */
    size_t literal_length;
    char *param_name;        /* heap-allocated null-terminated name (only when is_param=1) */
} SSCompiledRouteSegment;

typedef struct SSCompiledRoute {
    const SSHttpRoute *route;
    SSCompiledRouteSegment segments[SS_HTTP_MAX_ROUTE_SEGMENTS];
    size_t segment_count;
} SSCompiledRoute;

/* Module-static so the dispatcher loop in handle_client can reach it
 * without threading another argument through every helper. The server
 * is single-threaded today; if multi-listener support lands later this
 * should be moved into a per-server context struct. */
static SSCompiledRoute *g_compiled_routes = NULL;
static size_t g_compiled_route_count = 0;

static void free_compiled_routes(void) {
    if (g_compiled_routes == NULL) {
        return;
    }
    for (size_t route_index = 0; route_index < g_compiled_route_count; ++route_index) {
        SSCompiledRoute *compiled = &g_compiled_routes[route_index];
        for (size_t segment_index = 0; segment_index < compiled->segment_count; ++segment_index) {
            SSCompiledRouteSegment *segment = &compiled->segments[segment_index];
            if (segment->is_param && segment->param_name != NULL) {
                free(segment->param_name);
                segment->param_name = NULL;
            }
        }
    }
    free(g_compiled_routes);
    g_compiled_routes = NULL;
    g_compiled_route_count = 0;
}

static int compile_routes(const SSHttpServerConfig *config) {
    free_compiled_routes();
    if (config->route_count == 0) {
        return SS_HTTP_OK;
    }

    g_compiled_routes = (SSCompiledRoute *)calloc(
        config->route_count, sizeof(SSCompiledRoute));
    if (g_compiled_routes == NULL) {
        return SS_HTTP_ERR_ENGINE;
    }
    g_compiled_route_count = config->route_count;

    for (size_t route_index = 0; route_index < config->route_count; ++route_index) {
        const SSHttpRoute *route = &config->routes[route_index];
        SSCompiledRoute *compiled = &g_compiled_routes[route_index];
        compiled->route = route;
        compiled->segment_count = 0;

        if (route->path == NULL) {
            free_compiled_routes();
            return SS_HTTP_ERR_CONFIG;
        }
        /* Wildcard route ("*") is a registered convention for the
         * not-found-handler slot — semsc-side codegen pulls its handler
         * into config->not_found_handler. Skip it during pattern
         * compilation; leave segment_count at 0 with a special marker
         * so the matcher never falls back to it on real lookups. */
        if (route->path[0] == '*' && route->path[1] == '\0') {
            compiled->segment_count = 0;
            /* Mark with a sentinel literal so try_match_compiled_route
             * doesn't accept "/" (zero-segment match) as a hit on this
             * pseudo-route. */
            compiled->segments[0].is_param = 0;
            compiled->segments[0].literal = "__wildcard_not_found__";
            compiled->segments[0].literal_length = 22;
            compiled->segments[0].param_name = NULL;
            compiled->segment_count = 1;
            continue;
        }
        if (route->path[0] != '/') {
            free_compiled_routes();
            return SS_HTTP_ERR_CONFIG;
        }

        const char *scan = route->path + 1;
        /* Empty body after the leading slash means root "/" — zero segments. */
        if (*scan == '\0') {
            continue;
        }

        while (*scan != '\0') {
            if (compiled->segment_count >= SS_HTTP_MAX_ROUTE_SEGMENTS) {
                free_compiled_routes();
                return SS_HTTP_ERR_CONFIG;
            }
            const char *segment_start = scan;
            while (*scan != '/' && *scan != '\0') {
                ++scan;
            }
            size_t segment_length = (size_t)(scan - segment_start);
            if (segment_length == 0) {
                /* Empty segment ("//" inside the path or trailing "/") is a
                 * router-config error — reject early rather than letting
                 * undefined behavior leak into matching. */
                free_compiled_routes();
                return SS_HTTP_ERR_CONFIG;
            }
            SSCompiledRouteSegment *segment = &compiled->segments[compiled->segment_count++];
            if (*segment_start == ':') {
                if (segment_length < 2) {
                    /* Bare ":" with no name. */
                    free_compiled_routes();
                    return SS_HTTP_ERR_CONFIG;
                }
                segment->is_param = 1;
                segment->literal = NULL;
                segment->literal_length = 0;
                segment->param_name = (char *)malloc(segment_length);
                if (segment->param_name == NULL) {
                    free_compiled_routes();
                    return SS_HTTP_ERR_ENGINE;
                }
                memcpy(segment->param_name, segment_start + 1, segment_length - 1);
                segment->param_name[segment_length - 1] = '\0';
            } else {
                segment->is_param = 0;
                segment->literal = segment_start;
                segment->literal_length = segment_length;
                segment->param_name = NULL;
            }
            if (*scan == '/') {
                ++scan;
            }
        }
    }
    return SS_HTTP_OK;
}

/* Try to match one compiled route against the incoming path. On success
 * populates request->path_params (names borrowed from the compiled-route
 * segment, values copied into request->path_params_buffer so the caller
 * can treat them as ordinary C strings). On no-match the request's
 * path-param state is reset to empty. */
static int try_match_compiled_route(
    const SSCompiledRoute *compiled,
    const char *actual_path,
    SSHttpRequest *request
) {
    request->path_param_count = 0;
    request->path_params_buffer_used = 0;

    if (actual_path == NULL || actual_path[0] != '/') {
        return 0;
    }

    const char *scan = actual_path + 1;

    /* Root "/" — both expected and actual must have zero segments. */
    if (compiled->segment_count == 0) {
        return (*scan == '\0') ? 1 : 0;
    }

    for (size_t segment_index = 0; segment_index < compiled->segment_count; ++segment_index) {
        if (*scan == '\0') {
            /* Actual path ran out before route did. */
            request->path_param_count = 0;
            request->path_params_buffer_used = 0;
            return 0;
        }
        const SSCompiledRouteSegment *segment = &compiled->segments[segment_index];
        const char *segment_start = scan;
        while (*scan != '/' && *scan != '\0') {
            ++scan;
        }
        size_t segment_length = (size_t)(scan - segment_start);
        if (segment_length == 0) {
            request->path_param_count = 0;
            request->path_params_buffer_used = 0;
            return 0;
        }
        if (segment->is_param) {
            size_t value_storage_needed = segment_length + 1;
            if (request->path_params_buffer_used + value_storage_needed
                > SS_HTTP_PATH_PARAMS_BUFFER_SIZE) {
                /* Captured value is too long to fit in the per-request
                 * scratch arena — refuse the match rather than truncate. */
                request->path_param_count = 0;
                request->path_params_buffer_used = 0;
                return 0;
            }
            if (request->path_param_count >= SS_HTTP_MAX_PATH_PARAMS) {
                request->path_param_count = 0;
                request->path_params_buffer_used = 0;
                return 0;
            }
            char *value_destination =
                request->path_params_buffer + request->path_params_buffer_used;
            memcpy(value_destination, segment_start, segment_length);
            value_destination[segment_length] = '\0';
            request->path_params_buffer_used += value_storage_needed;

            request->path_params[request->path_param_count].name = segment->param_name;
            request->path_params[request->path_param_count].value = value_destination;
            ++request->path_param_count;
        } else {
            if (segment_length != segment->literal_length
                || memcmp(segment_start, segment->literal, segment_length) != 0) {
                request->path_param_count = 0;
                request->path_params_buffer_used = 0;
                return 0;
            }
        }
        if (*scan == '/') {
            if (segment_index == compiled->segment_count - 1) {
                /* A trailing slash is an extra empty segment. Routes are exact:
                 * /todos and /todos/ are intentionally different paths. */
                request->path_param_count = 0;
                request->path_params_buffer_used = 0;
                return 0;
            }
            ++scan;
        }
    }
    if (*scan != '\0') {
        request->path_param_count = 0;
        request->path_params_buffer_used = 0;
        return 0;
    }
    return 1;
}

static const SSHttpRoute *find_route(
    const SSHttpServerConfig *config,
    const char *method,
    const char *path
) {
    /* Kept for any caller that doesn't need path-param capture (none in
     * this translation unit today, but the signature is part of the
     * file's internal contract). Falls through to a degenerate path-only
     * compare without populating path_params — handle_client always uses
     * the param-aware path through find_compiled_route below. */
    size_t index;

    for (index = 0; index < config->route_count; ++index) {
        const SSHttpRoute *route = &config->routes[index];
        if (ascii_case_equal(route->method, method) && strcmp(route->path, path) == 0) {
            return route;
        }
    }

    return NULL;
}

static const SSHttpRoute *find_compiled_route(
    const char *method,
    const char *path,
    SSHttpRequest *request
) {
    for (size_t route_index = 0; route_index < g_compiled_route_count; ++route_index) {
        const SSCompiledRoute *compiled = &g_compiled_routes[route_index];
        if (!ascii_case_equal(compiled->route->method, method)) {
            continue;
        }
        if (try_match_compiled_route(compiled, path, request)) {
            return compiled->route;
        }
    }
    /* No match — ensure the request's path-param state is empty so a
     * stale capture from a previous attempt doesn't bleed through. */
    request->path_param_count = 0;
    request->path_params_buffer_used = 0;
    return NULL;
}

static const SSHttpRoute *find_compiled_method_mismatch(
    const char *method,
    const char *path,
    SSHttpRequest *request
) {
    for (size_t route_index = 0; route_index < g_compiled_route_count; ++route_index) {
        const SSCompiledRoute *compiled = &g_compiled_routes[route_index];
        if (ascii_case_equal(compiled->route->method, method)) {
            continue;
        }
        if (try_match_compiled_route(compiled, path, request)) {
            return compiled->route;
        }
    }
    request->path_param_count = 0;
    request->path_params_buffer_used = 0;
    return NULL;
}

static int parse_request_line(
    char *buffer,
    char **method_out,
    char **path_out,
    char **query_out,
    char **header_start_out
) {
    char *method = buffer;
    char *path;
    char *version;
    char *query_start;
    char *line_end = strstr(buffer, "\r\n");

    if (line_end == NULL) {
        line_end = strchr(buffer, '\n');
    }
    if (line_end == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }
    if (line_end != NULL) {
        *line_end = '\0';
    }

    path = strchr(method, ' ');
    if (path == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }
    *path = '\0';
    ++path;

    version = strchr(path, ' ');
    if (version == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }
    *version = '\0';

    query_start = strchr(path, '?');
    if (query_start != NULL) {
        *query_start = '\0';
        ++query_start;
    }

    *method_out = method;
    *path_out = path;
    *query_out = query_start;
    *header_start_out = line_end + 1;
    if (**header_start_out == '\n') {
        ++*header_start_out;
    }
    return SS_HTTP_OK;
}

static int handle_client(ss_socket_t client_socket, const SSHttpServerConfig *config) {
    char request_buffer[8192];
    char *request_storage = NULL;
    char *method = NULL;
    char *path = NULL;
    char *query = NULL;
    char *header_start = NULL;
    char *body_start = NULL;
    size_t header_bytes = 0;
    long content_length;
    size_t total_expected;
    size_t total_read;
    int read_count = recv(client_socket, request_buffer, (int)(sizeof(request_buffer) - 1), 0);
    const SSHttpRoute *route;
    SSHttpRequest request;
    SSHttpResponse response;
    SSHttpResponseBackend stream_backend;
    int handler_status;
    int response_status;

    if (read_count <= 0) {
        return SS_HTTP_ERR_ENGINE;
    }
    request_buffer[read_count] = '\0';

    body_start = (char *)find_header_end(request_buffer, (size_t)read_count, &header_bytes);
    if (body_start == NULL || header_bytes > (size_t)read_count) {
        return send_response(
            client_socket,
            400,
            "text/plain; charset=utf-8",
            "bad request\n",
            NULL
        );
    }

    content_length = parse_content_length(request_buffer, body_start);
    if (content_length < 0 ||
            (size_t)content_length > SS_HTTP_MAX_REQUEST_BYTES ||
            header_bytes + (size_t)content_length > SS_HTTP_MAX_REQUEST_BYTES) {
        return send_response(
            client_socket,
            413,
            "text/plain; charset=utf-8",
            "payload too large\n",
            NULL
        );
    }

    total_expected = header_bytes + (size_t)content_length;
    request_storage = (char *)malloc(total_expected + 1);
    if (request_storage == NULL) {
        return send_response(
            client_socket,
            503,
            "text/plain; charset=utf-8",
            "request allocation failed\n",
            NULL
        );
    }

    total_read = (size_t)read_count > total_expected ? total_expected : (size_t)read_count;
    memcpy(request_storage, request_buffer, total_read);
    while (total_read < total_expected) {
        int next_read = recv(
            client_socket,
            request_storage + total_read,
            (int)(total_expected - total_read),
            0
        );
        if (next_read <= 0) {
            free(request_storage);
            return send_response(
                client_socket,
                400,
                "text/plain; charset=utf-8",
                "bad request\n",
                NULL
            );
        }
        total_read += (size_t)next_read;
    }
    request_storage[total_expected] = '\0';
    body_start = request_storage + header_bytes;

    if (parse_request_line(request_storage, &method, &path, &query, &header_start) != SS_HTTP_OK) {
        free(request_storage);
        return send_response(
            client_socket,
            400,
            "text/plain; charset=utf-8",
            "bad request\n",
            NULL
        );
    }

    /* Initialize the request struct BEFORE route matching so the
     * pattern-route matcher can populate path_params on a successful
     * match. handle_client previously deferred memset until after
     * find_route returned a hit; the path-param path needs the empty
     * request buffer available up front. */
    memset(&request, 0, sizeof(request));
    request.method = method;
    request.path = path;
    request.query = query;
    request.body = body_start;
    request.body_length = (size_t)content_length;
    request.backend_request = NULL;
    parse_headers(header_start, body_start, &request);
    parse_query_params(query, &request);
    memset(&stream_backend, 0, sizeof(stream_backend));
    stream_backend.socket_handle = client_socket;

    route = find_compiled_route(method, path, &request);
    if (route == NULL) {
        if (config->method_not_allowed_handler != NULL &&
                find_compiled_method_mismatch(method, path, &request) != NULL) {
            memset(&response, 0, sizeof(response));
            response.status = 405;
            response.body = NULL;
            response.body_length = 0;
            response.content_type = "text/plain; charset=utf-8";
            response.owned_body = NULL;
            response.owned_content_type = NULL;
            response.backend_response = &stream_backend;
            int mna_status = config->method_not_allowed_handler(&request, &response);
            if (mna_status == SS_HTTP_OK && stream_backend.stream_started) {
                response_status = stream_backend.stream_error ? SS_HTTP_ERR_ENGINE : SS_HTTP_OK;
            } else if (mna_status == SS_HTTP_OK && response.body != NULL) {
                response_status = send_response(
                    client_socket,
                    response.status,
                    response.content_type,
                    response.body,
                    &response);
            } else {
                response_status = send_response(
                    client_socket,
                    405,
                    "text/plain; charset=utf-8",
                    response.body != NULL ? response.body : "method not allowed\n",
                    &response);
            }
            clear_owned_response(&response);
            free(request_storage);
            return response_status;
        }
        /* If the caller registered a not-found handler, give it the
         * same (request, response) pair every route handler sees so it
         * can return an HTML page, JSON envelope, or whatever shape
         * the app wants. Falls back to the historic plaintext body
         * when no handler is configured (compat with old apps). */
        if (config->not_found_handler != NULL) {
            memset(&response, 0, sizeof(response));
            response.status = 404;
            response.body = NULL;
            response.body_length = 0;
            response.content_type = "text/plain; charset=utf-8";
            response.owned_body = NULL;
            response.owned_content_type = NULL;
            response.backend_response = &stream_backend;
            int nf_status = config->not_found_handler(&request, &response);
            if (nf_status == SS_HTTP_OK && stream_backend.stream_started) {
                response_status = stream_backend.stream_error ? SS_HTTP_ERR_ENGINE : SS_HTTP_OK;
            } else if (nf_status == SS_HTTP_OK && response.body != NULL) {
                response_status = send_response(
                    client_socket,
                    response.status,
                    response.content_type,
                    response.body,
                    &response);
            } else {
                response_status = send_response(
                    client_socket,
                    404,
                    "text/plain; charset=utf-8",
                    response.body != NULL ? response.body : "not found\n",
                    &response);
            }
            clear_owned_response(&response);
            free(request_storage);
            return response_status;
        }
        response_status = send_response(
            client_socket,
            404,
            "text/plain; charset=utf-8",
            "not found\n",
            NULL
        );
        free(request_storage);
        return response_status;
    }

    memset(&response, 0, sizeof(response));
    response.status = 200;
    response.body = NULL;
    response.body_length = 0;
    response.content_type = "text/plain; charset=utf-8";
    response.owned_body = NULL;
    response.owned_content_type = NULL;
    response.backend_response = &stream_backend;

    if (route->middleware != NULL) {
        handler_status = route->middleware(&request, &response);
        if (handler_status == SS_HTTP_MIDDLEWARE_SHORT_CIRCUIT) {
            /* Middleware took ownership of the response: skip the route
             * handler and send what middleware wrote. This is the
             * `shortCircuitMiddlewareControl` arm of the MiddlewareControl
             * contract (see docs/reference/syntax-inventory.md `MiddlewareControl`). If middleware
             * returned short-circuit but never wrote a body, that's a
             * silent dispatcher gap — surface it as a 500 with an
             * explicit reason so the regression shows up at the client
             * instead of producing an empty 200 (or worse, a malformed
             * response from an uninitialized field). */
            if (stream_backend.stream_started) {
                response_status = stream_backend.stream_error ? SS_HTTP_ERR_ENGINE : SS_HTTP_OK;
            } else if (response.body == NULL) {
                response_status = send_response(
                    client_socket,
                    500,
                    "text/plain; charset=utf-8",
                    "middleware short-circuited without writing a response\n",
                    &response
                );
            } else {
                response_status = send_response(
                    client_socket,
                    response.status,
                    response.content_type,
                    response.body,
                    &response
                );
            }
            clear_owned_response(&response);
            free(request_storage);
            return response_status;
        }
        if (handler_status != SS_HTTP_OK) {
            /* Any other non-zero return is an unhandled middleware
             * failure. The 500 here is the legacy dispatcher behavior
             * the gauntlet's `/reflect/required-header-or-fail` route
             * pins via `pinsNullBodyFailurePath` — do not collapse it
             * with the short-circuit arm above. */
            response_status = send_response(
                client_socket,
                500,
                "text/plain; charset=utf-8",
                response.body != NULL ? response.body : "middleware failed\n",
                &response
            );
            clear_owned_response(&response);
            free(request_storage);
            return response_status;
        }
    }

    handler_status = route->handler(&request, &response);
    if (stream_backend.stream_started) {
        response_status = stream_backend.stream_error ? SS_HTTP_ERR_ENGINE : SS_HTTP_OK;
        clear_owned_response(&response);
        free(request_storage);
        return response_status;
    }
    if (handler_status != SS_HTTP_OK) {
        response_status = send_response(
            client_socket,
            500,
            "text/plain; charset=utf-8",
            "handler failed\n",
            &response
        );
        clear_owned_response(&response);
        free(request_storage);
        return response_status;
    }
    if (response.body == NULL) {
        response_status = send_response(
            client_socket,
            500,
            "text/plain; charset=utf-8",
            "handler did not write a response\n",
            &response
        );
        clear_owned_response(&response);
        free(request_storage);
        return response_status;
    }

    response_status = send_response(
        client_socket,
        response.status,
        response.content_type,
        response.body,
        &response
    );
    clear_owned_response(&response);
    free(request_storage);
    return response_status;
}

static int wait_for_listen_socket(ss_socket_t listen_socket) {
    fd_set read_set;
    struct timeval timeout;
    int ready;

    FD_ZERO(&read_set);
    FD_SET(listen_socket, &read_set);
    timeout.tv_sec = SS_HTTP_SHUTDOWN_POLL_MILLIS / 1000;
    timeout.tv_usec = (SS_HTTP_SHUTDOWN_POLL_MILLIS % 1000) * 1000;

    ready = select((int)(listen_socket + 1), &read_set, NULL, NULL, &timeout);
    if (ready <= 0) {
        return ready;
    }
    return FD_ISSET(listen_socket, &read_set) ? 1 : 0;
}

int ss_http_server_run(const SSHttpServerConfig *config) {
    struct addrinfo hints;
    struct addrinfo *result = NULL;
    struct addrinfo *current = NULL;
    char port_text[16];
    ss_socket_t listen_socket = SS_INVALID_SOCKET;

    if (!has_valid_route_table(config)) {
        return SS_HTTP_ERR_CONFIG;
    }

    reset_http_shutdown_state();
    install_http_shutdown_handlers();

    /* Pre-parse every route path into segment tables exactly once. A
     * compile failure (bad pattern, malloc OOM) aborts startup with the
     * matching error code before we even bind the socket. */
    {
        int compile_status = compile_routes(config);
        if (compile_status != SS_HTTP_OK) {
            return compile_status;
        }
    }

#ifdef _WIN32
    {
        WSADATA wsa_data;
        if (WSAStartup(MAKEWORD(2, 2), &wsa_data) != 0) {
            free_compiled_routes();
            return SS_HTTP_ERR_ENGINE;
        }
    }
#endif

    snprintf(port_text, sizeof(port_text), "%hu", config->port);
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    hints.ai_flags = AI_PASSIVE;

    if (getaddrinfo(config->host, port_text, &hints, &result) != 0) {
        free_compiled_routes();
#ifdef _WIN32
        WSACleanup();
#endif
        return SS_HTTP_ERR_ENGINE;
    }

    for (current = result; current != NULL; current = current->ai_next) {
        int reuse = 1;
        listen_socket = socket(current->ai_family, current->ai_socktype, current->ai_protocol);
        if (listen_socket == SS_INVALID_SOCKET) {
            continue;
        }
        setsockopt(
            listen_socket,
            SOL_SOCKET,
            SO_REUSEADDR,
            (const char *)&reuse,
            (int)sizeof(reuse)
        );
        if (bind(listen_socket, current->ai_addr, (int)current->ai_addrlen) == 0) {
            break;
        }
        ss_close_socket(listen_socket);
        listen_socket = SS_INVALID_SOCKET;
    }

    freeaddrinfo(result);

    if (listen_socket == SS_INVALID_SOCKET) {
        free_compiled_routes();
#ifdef _WIN32
        WSACleanup();
#endif
        return SS_HTTP_ERR_ENGINE;
    }

    if (listen(listen_socket, 128) != 0) {
        ss_close_socket(listen_socket);
        free_compiled_routes();
#ifdef _WIN32
        WSACleanup();
#endif
        return SS_HTTP_ERR_ENGINE;
    }

    printf("SemanticScript HTTP server listening at http://%s:%hu\n", config->host, config->port);
    fflush(stdout);

    while (!http_shutdown_requested()) {
        int ready = wait_for_listen_socket(listen_socket);
        ss_socket_t client_socket;
        if (ready == 0) {
            continue;
        }
        if (ready < 0) {
#ifndef _WIN32
            if (errno == EINTR) {
                continue;
            }
#endif
            if (http_shutdown_requested()) {
                break;
            }
            continue;
        }

        client_socket = accept(listen_socket, NULL, NULL);
        if (client_socket == SS_INVALID_SOCKET) {
            continue;
        }
        (void)handle_client(client_socket, config);
        ss_close_socket(client_socket);
    }

    ss_close_socket(listen_socket);
    free_compiled_routes();
#ifdef _WIN32
    WSACleanup();
#endif
    return SS_HTTP_OK;
}

#endif
