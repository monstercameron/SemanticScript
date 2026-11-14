#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../../semanticscript/runtime/native_log/sem_log_runtime.c"

static void assert_file_contains(const char *path, const char *needle) {
    FILE *fp = fopen(path, "rb");
    char buffer[4096];
    size_t n;

    assert(fp != NULL);
    n = fread(buffer, 1, sizeof(buffer) - 1, fp);
    buffer[n] = '\0';
    fclose(fp);

    assert(strstr(buffer, needle) != NULL);
}

int main(void) {
    assert(ss_log_set_path("../escape.log") == SS_LOG_ERR_CONFIG);
    assert(ss_log_set_path("/escape.log") == SS_LOG_ERR_CONFIG);
    assert(ss_log_set_path("\\\\server\\share\\escape.log") == SS_LOG_ERR_CONFIG);
    assert(ss_log_set_path("C:\\escape.log") == SS_LOG_ERR_CONFIG);

    assert(ss_log_set_path("logs/a/b/audit.log") == SS_LOG_OK);
    assert(ss_log_info("hello") == SS_LOG_OK);
    assert(ss_log_warn("careful") == SS_LOG_OK);

    assert(ss_log_set_path("other.log") == SS_LOG_ERR_CONFIG);
    assert_file_contains("logs/a/b/audit.log", "\"level\":\"info\"");
    assert_file_contains("logs/a/b/audit.log", "\"message\":\"hello\"");
    assert_file_contains("logs/a/b/audit.log", "\"level\":\"warn\"");
    assert_file_contains("logs/a/b/audit.log", "\"message\":\"careful\"");

    printf("harness_log: OK\n");
    return 0;
}
