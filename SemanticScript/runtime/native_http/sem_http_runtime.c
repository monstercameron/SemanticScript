#include "sem_http_runtime.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SS_HTTP_MAX_REQUEST_BYTES 65536
#define SS_HTTP_MAX_HEADERS 32
#define SS_HTTP_MAX_QUERY_PARAMS 32
#define SS_HTTP_MAX_MULTIPART_PARTS 16
#define SS_HTTP_MULTIPART_BOUNDARY_MAX 128

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

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET ss_socket_t;
#define SS_INVALID_SOCKET INVALID_SOCKET
static void ss_close_socket(ss_socket_t socket_handle) {
    closesocket(socket_handle);
}
#else
#include <arpa/inet.h>
#include <errno.h>
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
    if (response != NULL && response->owned_body != NULL) {
        free(response->owned_body);
        response->owned_body = NULL;
    }
}

int ss_http_response_text(
    SSHttpResponse *response,
    int status,
    const char *body,
    const char *content_type
) {
    if (response == NULL || body == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }

    clear_owned_response_body(response);
    response->status = status;
    response->body = body;
    response->body_length = strlen(body);
    response->content_type = content_type != NULL ? content_type : "text/plain; charset=utf-8";
    return SS_HTTP_OK;
}

int ss_http_response_bytes(
    SSHttpResponse *response,
    int status,
    const void *body,
    size_t body_length,
    const char *content_type
) {
    if (response == NULL || (body == NULL && body_length > 0)) {
        return SS_HTTP_ERR_CONFIG;
    }

    clear_owned_response_body(response);
    response->status = status;
    response->body = (const char *)body;
    response->body_length = body_length;
    response->content_type = content_type != NULL ? content_type : "application/octet-stream";
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
    if (response == NULL ||
            !is_valid_header_name(name) ||
            !is_valid_header_value(value) ||
            ascii_case_equal(name, "Content-Length") ||
            ascii_case_equal(name, "Connection") ||
            ascii_case_equal(name, "Content-Type") ||
            response->header_count >= SS_HTTP_MAX_HEADERS) {
        return SS_HTTP_ERR_CONFIG;
    }

    response->headers[response->header_count].name = name;
    response->headers[response->header_count].value = value;
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
        response != NULL && response->body == body
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

static const SSHttpRoute *find_route(
    const SSHttpServerConfig *config,
    const char *method,
    const char *path
) {
    size_t index;

    for (index = 0; index < config->route_count; ++index) {
        const SSHttpRoute *route = &config->routes[index];
        if (ascii_case_equal(route->method, method) && strcmp(route->path, path) == 0) {
            return route;
        }
    }

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

    route = find_route(config, method, path);
    if (route == NULL) {
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

    memset(&request, 0, sizeof(request));
    request.method = method;
    request.path = path;
    request.query = query;
    request.body = body_start;
    request.body_length = (size_t)content_length;
    request.backend_request = NULL;
    parse_headers(header_start, body_start, &request);
    parse_query_params(query, &request);

    memset(&response, 0, sizeof(response));
    response.status = 200;
    response.body = NULL;
    response.body_length = 0;
    response.content_type = "text/plain; charset=utf-8";
    response.owned_body = NULL;
    response.backend_response = NULL;

    if (route->middleware != NULL) {
        handler_status = route->middleware(&request, &response);
        if (handler_status != SS_HTTP_OK) {
            response_status = send_response(
                client_socket,
                500,
                "text/plain; charset=utf-8",
                response.body != NULL ? response.body : "middleware failed\n",
                &response
            );
            clear_owned_response_body(&response);
            free(request_storage);
            return response_status;
        }
    }

    handler_status = route->handler(&request, &response);
    if (handler_status != SS_HTTP_OK) {
        response_status = send_response(
            client_socket,
            500,
            "text/plain; charset=utf-8",
            "handler failed\n",
            &response
        );
        clear_owned_response_body(&response);
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
        clear_owned_response_body(&response);
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
    clear_owned_response_body(&response);
    free(request_storage);
    return response_status;
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

#ifdef _WIN32
    {
        WSADATA wsa_data;
        if (WSAStartup(MAKEWORD(2, 2), &wsa_data) != 0) {
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
#ifdef _WIN32
        WSACleanup();
#endif
        return SS_HTTP_ERR_ENGINE;
    }

    if (listen(listen_socket, 128) != 0) {
        ss_close_socket(listen_socket);
#ifdef _WIN32
        WSACleanup();
#endif
        return SS_HTTP_ERR_ENGINE;
    }

    printf("SemanticScript HTTP server listening at http://%s:%hu\n", config->host, config->port);
    fflush(stdout);

    for (;;) {
        ss_socket_t client_socket = accept(listen_socket, NULL, NULL);
        if (client_socket == SS_INVALID_SOCKET) {
            continue;
        }
        (void)handle_client(client_socket, config);
        ss_close_socket(client_socket);
    }
}

#endif
