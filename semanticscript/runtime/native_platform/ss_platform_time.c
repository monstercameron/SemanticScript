#include "ss_platform_time.h"

#if defined(_WIN32)
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#else
#  include <errno.h>
#  include <time.h>
#  include <unistd.h>
#endif

long long ss_platform_wall_time_ms(void) {
#if defined(_WIN32)
    FILETIME file_time;
    GetSystemTimeAsFileTime(&file_time);
    ULARGE_INTEGER as_uint64;
    as_uint64.LowPart = file_time.dwLowDateTime;
    as_uint64.HighPart = file_time.dwHighDateTime;
    static const long long epoch_offset_100ns_units = 116444736000000000LL;
    long long since_unix_epoch_100ns =
        (long long)as_uint64.QuadPart - epoch_offset_100ns_units;
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

long long ss_platform_monotonic_ms(void) {
#if defined(_WIN32)
    return (long long)GetTickCount64();
#else
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return 0;
    }
    return (long long)ts.tv_sec * 1000LL
         + (long long)(ts.tv_nsec / 1000000L);
#endif
}

void ss_platform_sleep_ms(unsigned int milliseconds) {
#if defined(_WIN32)
    Sleep((DWORD)milliseconds);
#else
    struct timespec requested;
    struct timespec remaining;
    requested.tv_sec = (time_t)(milliseconds / 1000U);
    requested.tv_nsec = (long)(milliseconds % 1000U) * 1000000L;
    while (nanosleep(&requested, &remaining) != 0) {
        if (errno != EINTR) {
            return;
        }
        requested = remaining;
    }
#endif
}
