#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <conio.h>
#include <stdlib.h>

extern int __argc;
extern char **__argv;

static DWORD ss_terminal_original_input_mode = 0;
static DWORD ss_terminal_original_output_mode = 0;
static int ss_terminal_has_input_mode = 0;
static int ss_terminal_has_output_mode = 0;
static int ss_terminal_raw_enabled = 0;

static const unsigned char *ss_terminal_test_keys = 0;
static int ss_terminal_test_keys_initialized = 0;
static unsigned long long ss_terminal_test_key_index = 0;

static int ss_terminal_next_test_key(void) {
    if (!ss_terminal_test_keys_initialized) {
        ss_terminal_test_keys = (const unsigned char *)getenv("SEM_TERMINAL_TEST_KEYS");
        ss_terminal_test_keys_initialized = 1;
        ss_terminal_test_key_index = 0;
    }
    if (!ss_terminal_test_keys) {
        return -1;
    }
    unsigned char value = ss_terminal_test_keys[ss_terminal_test_key_index];
    if (value == 0) {
        return -1;
    }
    ss_terminal_test_key_index += 1;
    return (int)value;
}

int ss_terminal_enable_raw(void) {
    HANDLE input = GetStdHandle(STD_INPUT_HANDLE);
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    DWORD mode = 0;

    if (input != INVALID_HANDLE_VALUE && GetConsoleMode(input, &mode)) {
        ss_terminal_original_input_mode = mode;
        ss_terminal_has_input_mode = 1;
        mode &= ~(ENABLE_ECHO_INPUT | ENABLE_LINE_INPUT | ENABLE_PROCESSED_INPUT);
        mode &= ~(ENABLE_MOUSE_INPUT);
        mode |= ENABLE_WINDOW_INPUT;
        if (!SetConsoleMode(input, mode)) {
            return -1;
        }
    }

    if (output != INVALID_HANDLE_VALUE && GetConsoleMode(output, &mode)) {
        ss_terminal_original_output_mode = mode;
        ss_terminal_has_output_mode = 1;
        mode |= ENABLE_VIRTUAL_TERMINAL_PROCESSING;
#ifdef DISABLE_NEWLINE_AUTO_RETURN
        mode |= DISABLE_NEWLINE_AUTO_RETURN;
#endif
        SetConsoleMode(output, mode);
    }

    ss_terminal_raw_enabled = 1;
    return 0;
}

int ss_terminal_disable_raw(void) {
    if (ss_terminal_has_input_mode) {
        HANDLE input = GetStdHandle(STD_INPUT_HANDLE);
        if (input != INVALID_HANDLE_VALUE) {
            SetConsoleMode(input, ss_terminal_original_input_mode);
        }
    }
    if (ss_terminal_has_output_mode) {
        HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
        if (output != INVALID_HANDLE_VALUE) {
            SetConsoleMode(output, ss_terminal_original_output_mode);
        }
    }
    ss_terminal_raw_enabled = 0;
    return 0;
}

long long ss_terminal_get_window_rows(void) {
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO info;
    if (output != INVALID_HANDLE_VALUE && GetConsoleScreenBufferInfo(output, &info)) {
        return (long long)(info.srWindow.Bottom - info.srWindow.Top + 1);
    }
    return 24;
}

long long ss_terminal_get_window_cols(void) {
    HANDLE output = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO info;
    if (output != INVALID_HANDLE_VALUE && GetConsoleScreenBufferInfo(output, &info)) {
        return (long long)(info.srWindow.Right - info.srWindow.Left + 1);
    }
    return 80;
}

char *ss_terminal_first_argument(void) {
    if (__argc > 1 && __argv && __argv[1] && __argv[1][0]) {
        return __argv[1];
    }
    return 0;
}

int ss_terminal_read_key(void) {
    int first = ss_terminal_next_test_key();
    if (first < 0) {
        first = _getch();
    }

    if (first == 0 || first == 224) {
        int second = ss_terminal_next_test_key();
        if (second < 0) {
            second = _getch();
        }
        switch (second) {
            case 71: return 1005;
            case 72: return 1002;
            case 73: return 1007;
            case 75: return 1000;
            case 77: return 1001;
            case 79: return 1006;
            case 80: return 1003;
            case 81: return 1008;
            case 83: return 1004;
            default: return 27;
        }
    }

    return first;
}

#else
#include <stdio.h>
#include <stdlib.h>

int ss_terminal_enable_raw(void) {
    return 0;
}

int ss_terminal_disable_raw(void) {
    return 0;
}

long long ss_terminal_get_window_rows(void) {
    const char *value = getenv("LINES");
    long rows = value ? strtol(value, 0, 10) : 0;
    return rows > 0 ? (long long)rows : 24;
}

long long ss_terminal_get_window_cols(void) {
    const char *value = getenv("COLUMNS");
    long cols = value ? strtol(value, 0, 10) : 0;
    return cols > 0 ? (long long)cols : 80;
}

char *ss_terminal_first_argument(void) {
    return 0;
}

int ss_terminal_read_key(void) {
    const unsigned char *test_keys = (const unsigned char *)getenv("SEM_TERMINAL_TEST_KEYS");
    static unsigned long long index = 0;
    if (test_keys && test_keys[index]) {
        return (int)test_keys[index++];
    }
    return getchar();
}
#endif
