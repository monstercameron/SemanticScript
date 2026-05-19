#include "sem_bcrypt_runtime.h"

/*
 * Important naming-collision note: this file uses TWO things both
 * called "bcrypt":
 *
 *   1. The bcrypt password hashing algorithm (Niels Provos / David
 *      Mazières, 1999). Implementation lives in
 *      third_party/bcrypt/crypt_blowfish.c. Symbol prefix:
 *      `_crypt_blowfish_rn` / `_crypt_gensalt_blowfish_rn`.
 *
 *   2. Windows's Cryptography Next-Generation (CNG) API, which
 *      exposes BCryptGenRandom through bcrypt.dll for platform
 *      randomness. Symbol prefix: `BCryptGenRandom`.
 *
 * The two are unrelated and the symbol prefixes don't overlap, so
 * including both is safe — but reviewers should not assume the
 * Windows CNG entry points perform the password hash.
 */

#include "../../../third_party/bcrypt/crypt_blowfish.h"
#include "../../../third_party/bcrypt/crypt_gensalt.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  include <bcrypt.h>     /* Windows CNG — provides BCryptGenRandom */
#  pragma comment(lib, "bcrypt.lib")
#elif defined(__linux__)
#  include <sys/random.h>  /* getrandom(2) */
#  include <errno.h>
#else
#  include <fcntl.h>
#  include <unistd.h>
#endif

/* ----- random bytes ----- */

int ss_random_bytes(unsigned char *out_buffer, int byte_count) {
    if (out_buffer == NULL || byte_count <= 0) {
        return SS_BCRYPT_ERR_CONFIG;
    }

#if defined(_WIN32)
    NTSTATUS status = BCryptGenRandom(
        NULL, out_buffer, (ULONG)byte_count,
        BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    if (status != 0) {
        return SS_BCRYPT_ERR_RANDOM;
    }
    return SS_BCRYPT_OK;
#elif defined(__linux__)
    /* getrandom can be interrupted; loop until we've filled the
     * buffer or hit a non-EINTR error. */
    int total_read = 0;
    while (total_read < byte_count) {
        ssize_t step = getrandom(
            out_buffer + total_read,
            (size_t)(byte_count - total_read),
            0);
        if (step < 0) {
            if (errno == EINTR) continue;
            return SS_BCRYPT_ERR_RANDOM;
        }
        total_read += (int)step;
    }
    return SS_BCRYPT_OK;
#else
    /* /dev/urandom fallback for any POSIX target without getrandom. */
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) return SS_BCRYPT_ERR_RANDOM;
    int total_read = 0;
    while (total_read < byte_count) {
        ssize_t step = read(fd, out_buffer + total_read,
                            (size_t)(byte_count - total_read));
        if (step <= 0) {
            close(fd);
            return SS_BCRYPT_ERR_RANDOM;
        }
        total_read += (int)step;
    }
    close(fd);
    return SS_BCRYPT_OK;
#endif
}

/* ----- bcrypt hash ----- */

int ss_bcrypt_hash(
    const char *plaintext_password,
    int cost_factor,
    char *out_hash_buffer,
    int out_hash_buffer_capacity
) {
    if (plaintext_password == NULL
        || out_hash_buffer == NULL
        || out_hash_buffer_capacity < SS_BCRYPT_HASH_OUTPUT_SIZE) {
        return SS_BCRYPT_ERR_CONFIG;
    }
    if (cost_factor < SS_BCRYPT_MIN_COST
        || cost_factor > SS_BCRYPT_MAX_COST) {
        return SS_BCRYPT_ERR_CONFIG;
    }

    /* Generate 16 bytes of salt entropy. crypt_blowfish's
     * _crypt_gensalt_blowfish_rn accepts exactly 16 bytes of input
     * regardless of cost. */
    unsigned char salt_entropy[16];
    int random_status = ss_random_bytes(salt_entropy, sizeof(salt_entropy));
    if (random_status != SS_BCRYPT_OK) {
        return SS_BCRYPT_ERR_RANDOM;
    }

    /* Build the salt setting string: "$2b$NN$<22 base64 chars>". */
    char salt_setting[64];
    char *salt_result = _crypt_gensalt_blowfish_rn(
        "$2b$",
        (unsigned long)cost_factor,
        (const char *)salt_entropy,
        (int)sizeof(salt_entropy),
        salt_setting,
        (int)sizeof(salt_setting));
    if (salt_result == NULL) {
        return SS_BCRYPT_ERR_HASH;
    }

    /* Run the eksblowfish key schedule + hash. Output goes directly
     * into the caller's buffer; on failure the function returns NULL
     * and we surface that as ERR_HASH. */
    char *hash_result = _crypt_blowfish_rn(
        plaintext_password,
        salt_setting,
        out_hash_buffer,
        out_hash_buffer_capacity);
    if (hash_result == NULL) {
        return SS_BCRYPT_ERR_HASH;
    }
    return SS_BCRYPT_OK;
}

/* ----- bcrypt verify -----
 *
 * Strategy: hash the plaintext using the stored hash AS the salt
 * setting (bcrypt re-derives the salt + cost from the leading 29
 * characters), then constant-time compare the recomputed hash with
 * the stored hash. crypt_blowfish accepts the full 60-char stored
 * hash as the `setting` argument and only inspects the first 29
 * chars for the salt.
 */

static int constant_time_equals(const char *a, const char *b, size_t length) {
    /* Single-pass XOR-or-fold: guarantees the function runs in time
     * dependent only on `length`, never on the position of the first
     * mismatch. */
    unsigned char accumulator = 0;
    for (size_t i = 0; i < length; ++i) {
        accumulator |= (unsigned char)(a[i] ^ b[i]);
    }
    return accumulator == 0 ? 1 : 0;
}

int ss_bcrypt_verify(
    const char *plaintext_password,
    const char *expected_hash_60_chars
) {
    if (plaintext_password == NULL || expected_hash_60_chars == NULL) {
        return SS_BCRYPT_ERR_CONFIG;
    }
    /* Stored hashes must be exactly 60 chars + NUL — sanity-check the
     * length up front so a truncated DB row can't be mis-hashed into
     * a coincidental match. */
    size_t expected_length = strlen(expected_hash_60_chars);
    if (expected_length != 60) {
        return SS_BCRYPT_ERR_MALFORMED;
    }
    /* Quick prefix check — must start with one of the bcrypt setting
     * prefixes. We're strict and require $2b$ (the format we always
     * write); legacy stores using $2a$ / $2x$ / $2y$ would be
     * rejected here. */
    if (expected_hash_60_chars[0] != '$'
        || expected_hash_60_chars[1] != '2'
        || expected_hash_60_chars[2] != 'b'
        || expected_hash_60_chars[3] != '$') {
        return SS_BCRYPT_ERR_MALFORMED;
    }

    char recomputed[SS_BCRYPT_HASH_OUTPUT_SIZE];
    char *result = _crypt_blowfish_rn(
        plaintext_password,
        expected_hash_60_chars,
        recomputed,
        (int)sizeof(recomputed));
    if (result == NULL) {
        return SS_BCRYPT_ERR_HASH;
    }

    /* Always compare on the full 60 bytes — both strings are known
     * to be that length (we just checked stored, and crypt_blowfish
     * always writes 60 chars for a valid $2b$ setting). */
    return constant_time_equals(recomputed, expected_hash_60_chars, 60);
}

/* ----- base64url encode -----
 *
 * URL-safe alphabet (- and _ in place of + and /). No padding (the
 * '=' suffix is omitted). Output is null-terminated.
 *
 * Encoded length formula: ((input_byte_count * 4) + 2) / 3.
 * For our session tokens (32 input bytes), that's exactly 43 chars
 * plus the NUL, requiring a 44-byte output buffer minimum.
 */

/* 64 alphabet bytes + 1 NUL the C literal carries with it. We don't
 * use the NUL anywhere — but declaring the array without an explicit
 * size silences clang's -Wunterminated-string-initialization warning
 * and is the same shape every standard base64 implementation uses. */
static const char base64url_alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

int ss_base64url_encode(
    const unsigned char *input_buffer,
    int input_byte_count,
    char *output_buffer,
    int output_buffer_capacity,
    int *output_length_out
) {
    if (input_buffer == NULL || output_buffer == NULL || input_byte_count < 0) {
        return SS_BCRYPT_ERR_CONFIG;
    }
    int required_capacity = ((input_byte_count * 4) + 2) / 3 + 1; /* +1 for NUL */
    if (output_buffer_capacity < required_capacity) {
        return SS_BCRYPT_ERR_CONFIG;
    }

    int input_index = 0;
    int output_index = 0;
    while (input_index + 3 <= input_byte_count) {
        unsigned int triplet =
            ((unsigned int)input_buffer[input_index] << 16) |
            ((unsigned int)input_buffer[input_index + 1] << 8) |
            ((unsigned int)input_buffer[input_index + 2]);
        output_buffer[output_index + 0] = base64url_alphabet[(triplet >> 18) & 0x3F];
        output_buffer[output_index + 1] = base64url_alphabet[(triplet >> 12) & 0x3F];
        output_buffer[output_index + 2] = base64url_alphabet[(triplet >> 6) & 0x3F];
        output_buffer[output_index + 3] = base64url_alphabet[triplet & 0x3F];
        input_index += 3;
        output_index += 4;
    }
    int remaining = input_byte_count - input_index;
    if (remaining == 1) {
        unsigned int last = (unsigned int)input_buffer[input_index] << 16;
        output_buffer[output_index + 0] = base64url_alphabet[(last >> 18) & 0x3F];
        output_buffer[output_index + 1] = base64url_alphabet[(last >> 12) & 0x3F];
        output_index += 2;
    } else if (remaining == 2) {
        unsigned int last =
            ((unsigned int)input_buffer[input_index] << 16) |
            ((unsigned int)input_buffer[input_index + 1] << 8);
        output_buffer[output_index + 0] = base64url_alphabet[(last >> 18) & 0x3F];
        output_buffer[output_index + 1] = base64url_alphabet[(last >> 12) & 0x3F];
        output_buffer[output_index + 2] = base64url_alphabet[(last >> 6) & 0x3F];
        output_index += 3;
    }
    output_buffer[output_index] = '\0';
    if (output_length_out != NULL) {
        *output_length_out = output_index;
    }
    return SS_BCRYPT_OK;
}
