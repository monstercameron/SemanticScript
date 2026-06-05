/*
 * R-028 native entropy harness. The platform API owns OS CSPRNG selection;
 * bcrypt remains a consumer through ss_random_bytes.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../../semanticscript/runtime/native_platform/ss_platform_entropy.h"
#include "../../semanticscript/runtime/native_bcrypt/sem_bcrypt_runtime.h"

static int any_nonzero(const unsigned char *buffer, size_t length) {
    size_t index;
    for (index = 0; index < length; ++index) {
        if (buffer[index] != 0) {
            return 1;
        }
    }
    return 0;
}

int main(void) {
    unsigned char first[32] = {0};
    unsigned char second[32] = {0};
    unsigned char wrapper[32] = {0};
    unsigned char marker = 0x5a;

    assert(ss_platform_random_bytes(NULL, sizeof(first)) != 0);
    assert(ss_platform_random_bytes(&marker, 0) == 0);
    assert(marker == 0x5a);

    assert(ss_platform_random_bytes(first, sizeof(first)) == 0);
    assert(ss_platform_random_bytes(second, sizeof(second)) == 0);
    assert(any_nonzero(first, sizeof(first)));
    assert(any_nonzero(second, sizeof(second)));
    assert(memcmp(first, second, sizeof(first)) != 0);

    assert(ss_random_bytes(NULL, 1) == SS_BCRYPT_ERR_CONFIG);
    assert(ss_random_bytes(wrapper, 0) == SS_BCRYPT_ERR_CONFIG);
    assert(ss_random_bytes(wrapper, 4097) == SS_BCRYPT_ERR_CONFIG);
    assert(ss_random_bytes(wrapper, (int)sizeof(wrapper)) == SS_BCRYPT_OK);
    assert(any_nonzero(wrapper, sizeof(wrapper)));

    printf("harness_entropy: OK\n");
    return 0;
}
