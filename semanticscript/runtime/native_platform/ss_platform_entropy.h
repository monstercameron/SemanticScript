#ifndef SS_PLATFORM_ENTROPY_H
#define SS_PLATFORM_ENTROPY_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

int ss_platform_random_bytes(unsigned char *out_buffer, size_t byte_count);

#ifdef __cplusplus
}
#endif

#endif
