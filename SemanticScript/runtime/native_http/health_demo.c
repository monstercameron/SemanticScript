#include "sem_http_runtime.h"

#include <stdio.h>

static int health_handler(SSHttpRequest *request, SSHttpResponse *response) {
    const char *method = ss_http_request_method(request);
    const char *path = ss_http_request_path(request);

    if (method == NULL || path == NULL) {
        return SS_HTTP_ERR_CONFIG;
    }

    return ss_http_response_text(response, 200, "ok\n", "text/plain; charset=utf-8");
}

int main(void) {
    SSHttpRoute routes[] = {
        {"GET", "/health", health_handler, NULL},
    };
    SSHttpServerConfig config = {
        "127.0.0.1",
        8080,
        routes,
        sizeof(routes) / sizeof(routes[0]),
        NULL,
        NULL,
    };

    int rc = ss_http_server_run(&config);
    if (rc == SS_HTTP_ERR_RUNTIME_UNAVAILABLE) {
        puts("sem_http_health_demo: adapter compiled; H2O backend not linked");
        return 0;
    }

    return rc;
}
