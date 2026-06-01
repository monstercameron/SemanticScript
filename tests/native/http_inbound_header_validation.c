/*
 * R-209 focused inbound HTTP header validation test. Includes the runtime source
 * so the fallback request parser and dispatch boundary can be exercised directly.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../semanticscript/runtime/native_http/sem_http_runtime.c"

static int handler_call_count = 0;

static void require_condition(int condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "%s\n", message);
        exit(1);
    }
}

static int reflect_header_handler(SSHttpRequest *request, SSHttpResponse *response) {
    const char *value;

    ++handler_call_count;
    value = ss_http_request_header(request, "X-Good");
    if (value == NULL) {
        value = "missing";
    }
    return ss_http_response_text(response, 200, value, "text/plain; charset=utf-8");
}

static void socket_runtime_start(void) {
#ifdef _WIN32
    WSADATA wsa_data;
    require_condition(WSAStartup(MAKEWORD(2, 2), &wsa_data) == 0, "WSAStartup failed");
#endif
}

static void socket_runtime_stop(void) {
#ifdef _WIN32
    WSACleanup();
#endif
}

static void make_connected_pair(ss_socket_t *client_out, ss_socket_t *server_out) {
    ss_socket_t listener;
    ss_socket_t client;
    ss_socket_t server;
    struct sockaddr_in address;
#ifdef _WIN32
    int address_length;
#else
    socklen_t address_length;
#endif
    int reuse = 1;

    listener = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    require_condition(listener != SS_INVALID_SOCKET, "listener socket failed");
    require_condition(
        setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, (const char *)&reuse, (int)sizeof(reuse)) == 0,
        "setsockopt failed"
    );

    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = 0;

    require_condition(
        bind(listener, (struct sockaddr *)&address, (int)sizeof(address)) == 0,
        "bind failed"
    );
    require_condition(listen(listener, 1) == 0, "listen failed");

#ifdef _WIN32
    address_length = (int)sizeof(address);
#else
    address_length = (socklen_t)sizeof(address);
#endif
    require_condition(
        getsockname(listener, (struct sockaddr *)&address, &address_length) == 0,
        "getsockname failed"
    );

    client = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    require_condition(client != SS_INVALID_SOCKET, "client socket failed");
    require_condition(
        connect(client, (struct sockaddr *)&address, (int)sizeof(address)) == 0,
        "connect failed"
    );

    server = accept(listener, NULL, NULL);
    require_condition(server != SS_INVALID_SOCKET, "accept failed");
    ss_close_socket(listener);

    *client_out = client;
    *server_out = server;
}

static void send_all_request(ss_socket_t socket_handle, const char *request) {
    size_t sent = 0;
    size_t length = strlen(request);

    while (sent < length) {
        int chunk = send(socket_handle, request + sent, (int)(length - sent), 0);
        require_condition(chunk > 0, "request send failed");
        sent += (size_t)chunk;
    }
#ifdef _WIN32
    shutdown(socket_handle, SD_SEND);
#else
    shutdown(socket_handle, SHUT_WR);
#endif
}

static void read_response(ss_socket_t socket_handle, char *response, size_t response_capacity) {
    size_t total = 0;

    while (total + 1 < response_capacity) {
        int chunk = recv(socket_handle, response + total, (int)(response_capacity - 1 - total), 0);
        if (chunk <= 0) {
            break;
        }
        total += (size_t)chunk;
    }
    response[total] = '\0';
}

static void exercise_request(
    const SSHttpServerConfig *config,
    const char *request,
    char *response,
    size_t response_capacity
) {
    ss_socket_t client;
    ss_socket_t server;
    int status;

    make_connected_pair(&client, &server);
    send_all_request(client, request);
    status = handle_client(server, config);
    require_condition(status == SS_HTTP_OK, "handle_client failed");
    ss_close_socket(server);
    read_response(client, response, response_capacity);
    ss_close_socket(client);
}

static void assert_response_contains(const char *response, const char *needle) {
    if (strstr(response, needle) == NULL) {
        fprintf(stderr, "missing response fragment: %s\nresponse was:\n%s\n", needle, response);
        exit(1);
    }
}

static void assert_request_result(
    const SSHttpServerConfig *config,
    const char *request,
    const char *status_line,
    const char *body_fragment,
    int expected_handler_delta
) {
    char response[1024];
    int before = handler_call_count;

    exercise_request(config, request, response, sizeof(response));
    assert_response_contains(response, status_line);
    if (body_fragment != NULL) {
        assert_response_contains(response, body_fragment);
    }
    require_condition(
        handler_call_count == before + expected_handler_delta,
        "handler dispatch count mismatch"
    );
}

int main(void) {
    SSHttpRoute routes[] = {
        {"GET", "/", reflect_header_handler, NULL},
    };
    SSHttpServerConfig config;

    memset(&config, 0, sizeof(config));
    config.host = "127.0.0.1";
    config.port = 1;
    config.routes = routes;
    config.route_count = sizeof(routes) / sizeof(routes[0]);

    socket_runtime_start();
    assert(compile_routes(&config) == SS_HTTP_OK);

    assert_request_result(
        &config,
        "GET / HTTP/1.1\r\nHost: local\r\nX-Good:\t preserved value \t\r\n\r\n",
        "HTTP/1.1 200 OK\r\n",
        "\r\n\r\npreserved value",
        1
    );
    assert_request_result(
        &config,
        "GET / HTTP/1.1\r\nHost: local\r\nBad Name: value\r\n\r\n",
        "HTTP/1.1 400 Bad Request\r\n",
        "\r\n\r\nbad request\n",
        0
    );
    assert_request_result(
        &config,
        "GET / HTTP/1.1\r\nHost: local\r\nX-Good: ok\rbad\r\n\r\n",
        "HTTP/1.1 400 Bad Request\r\n",
        "\r\n\r\nbad request\n",
        0
    );
    assert_request_result(
        &config,
        "GET / HTTP/1.1\r\nHost: local\r\nX-Good: bad\vvalue\r\n\r\n",
        "HTTP/1.1 400 Bad Request\r\n",
        "\r\n\r\nbad request\n",
        0
    );
    assert_request_result(
        &config,
        "GET / HTTP/1.1\r\nHost: local\r\n: value\r\n\r\n",
        "HTTP/1.1 400 Bad Request\r\n",
        "\r\n\r\nbad request\n",
        0
    );
    assert_request_result(
        &config,
        "GET / HTTP/1.1\r\nHost: local\r\n X-Good: folded\r\n\r\n",
        "HTTP/1.1 400 Bad Request\r\n",
        "\r\n\r\nbad request\n",
        0
    );

    free_compiled_routes();
    socket_runtime_stop();
    printf("http_inbound_header_validation: OK\n");
    return 0;
}
