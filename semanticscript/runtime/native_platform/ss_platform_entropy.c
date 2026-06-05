#include "ss_platform_entropy.h"

#if defined(_WIN32)
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  include <bcrypt.h>
#elif defined(__APPLE__) || defined(__FreeBSD__) || defined(__OpenBSD__) || defined(__NetBSD__)
#  include <stdlib.h>
#elif defined(__linux__)
#  include <errno.h>
#  include <sys/random.h>
#else
#  include <errno.h>
#  include <fcntl.h>
#  include <unistd.h>
#endif

int ss_platform_random_bytes(unsigned char *out_buffer, size_t byte_count) {
    if (byte_count == 0) {
        return 0;
    }
    if (out_buffer == 0) {
        return -1;
    }

#if defined(_WIN32)
    if (byte_count > (size_t)((ULONG)-1)) {
        return -1;
    }
    return BCryptGenRandom(
        0,
        out_buffer,
        (ULONG)byte_count,
        BCRYPT_USE_SYSTEM_PREFERRED_RNG
    ) == 0 ? 0 : -1;
#elif defined(__APPLE__) || defined(__FreeBSD__) || defined(__OpenBSD__) || defined(__NetBSD__)
    arc4random_buf(out_buffer, byte_count);
    return 0;
#elif defined(__linux__)
    size_t total_read = 0;
    while (total_read < byte_count) {
        ssize_t step = getrandom(
            out_buffer + total_read,
            byte_count - total_read,
            0
        );
        if (step < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        if (step == 0) {
            return -1;
        }
        total_read += (size_t)step;
    }
    return 0;
#else
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) {
        return -1;
    }

    size_t total_read = 0;
    while (total_read < byte_count) {
        ssize_t step = read(fd, out_buffer + total_read, byte_count - total_read);
        if (step < 0) {
            if (errno == EINTR) {
                continue;
            }
            close(fd);
            return -1;
        }
        if (step == 0) {
            close(fd);
            return -1;
        }
        total_read += (size_t)step;
    }
    close(fd);
    return 0;
#endif
}
