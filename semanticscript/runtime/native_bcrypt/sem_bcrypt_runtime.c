#include "sem_bcrypt_runtime.h"
#include "../native_platform/ss_platform_entropy.h"

/*
 * Important naming-collision note: this file uses TWO things both
 * called "bcrypt":
 *
 *   1. The bcrypt password hashing algorithm (Niels Provos / David
 *      Mazières, 1999). Implementation lives in
 *      third_party/bcrypt/crypt_blowfish.c. Symbol prefix:
 *      `_crypt_blowfish_rn` / `_crypt_gensalt_blowfish_rn`.
 *
 *   2. The native_platform entropy API, which owns OS CSPRNG selection
 *      and linker requirements for all runtimes that need randomness.
 *
 * The two are unrelated; platform randomness provides salt/session entropy,
 * not password hashing.
 */

#include "../../../third_party/bcrypt/crypt_blowfish.h"
#include "../../../third_party/bcrypt/crypt_gensalt.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ----- random bytes ----- */

/* R-202: ss_random_bytes has no separate capacity arg — `byte_count` is both the
 * count to write and the caller's implied buffer size, and it is then written in
 * full. An absurd/oversized count (a bug or a hostile caller) would write far past
 * a small allocation. The CSPRNG outputs here are salts (16) and session tokens
 * (32); cap the request to a generous ceiling so an out-of-range count fails
 * closed instead of becoming a large overflow. (Tying the count to the buffer's
 * true allocation size needs a bounds-carrying buffer type across the FFI — the
 * documented R-202 remainder.) */
#define SS_RANDOM_MAX_BYTES 4096

int ss_random_bytes(unsigned char *out_buffer, int byte_count) {
    if (out_buffer == NULL || byte_count <= 0 || byte_count > SS_RANDOM_MAX_BYTES) {
        return SS_BCRYPT_ERR_CONFIG;
    }

    return ss_platform_random_bytes(out_buffer, (size_t)byte_count) == 0
        ? SS_BCRYPT_OK
        : SS_BCRYPT_ERR_RANDOM;
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

/* R-256: production-floor-enforcing hash. A cost below the enforced safe floor
 * is refused (SS_BCRYPT_ERR_WEAK_COST) BEFORE any hashing, so a defaulted /
 * uninitialized / dynamically-computed weak cost cannot silently produce a
 * trivially brute-forceable credential. ss_bcrypt_hash itself still accepts the
 * full format range (4..31) for verify-side re-derivation and fast tests. */
int ss_bcrypt_hash_checked(
    const char *plaintext_password,
    int cost_factor,
    char *out_hash_buffer,
    int out_hash_buffer_capacity
) {
    if (cost_factor < SS_BCRYPT_SAFE_MIN_COST) {
        return SS_BCRYPT_ERR_WEAK_COST;
    }
    return ss_bcrypt_hash(plaintext_password, cost_factor,
                          out_hash_buffer, out_hash_buffer_capacity);
}

/* R-256: no-cost-arg safe default — there is no cost parameter to omit or
 * mis-set, so the result is always at least the recommended production cost. */
int ss_bcrypt_hash_default(
    const char *plaintext_password,
    char *out_hash_buffer,
    int out_hash_buffer_capacity
) {
    return ss_bcrypt_hash(plaintext_password, SS_BCRYPT_DEFAULT_COST,
                          out_hash_buffer, out_hash_buffer_capacity);
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
    /* R-254: accept every standard bcrypt setting variant on VERIFY, not just the
     * $2b$ we write. $2a$ (original), $2b$ (current), $2x$ (bug-compat for the
     * 2011 sign-extension bug), and $2y$ (PHP's $2b$ alias) are all valid bcrypt
     * settings that crypt_blowfish recomputes and constant-time-compares
     * identically — rejecting them locked out any imported/interop password
     * corpus for no security gain. (We still only ever WRITE $2b$.) */
    char variant = expected_hash_60_chars[2];
    if (expected_hash_60_chars[0] != '$'
        || expected_hash_60_chars[1] != '2'
        || (variant != 'a' && variant != 'b' && variant != 'x' && variant != 'y')
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
    /* R-255: return the explicit MATCH/MISMATCH symbols, not the raw 0/1 — so a
     * non-match is SS_BCRYPT_MISMATCH (2), never 0, and cannot be mistaken for
     * SS_BCRYPT_OK by a "0 == success" caller. */
    return constant_time_equals(recomputed, expected_hash_60_chars, 60)
        ? SS_BCRYPT_MATCH
        : SS_BCRYPT_MISMATCH;
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
    /* R-145: compute the required capacity in a wide type so `input_byte_count *
     * 4` cannot overflow signed int — an overflow would produce a small/negative
     * capacity that slips past the bounds check below and overflows the output
     * buffer. A genuinely too-large input then fails the capacity check cleanly. */
    long long required_capacity =
        (((long long)input_byte_count * 4) + 2) / 3 + 1; /* +1 for NUL */
    if ((long long)output_buffer_capacity < required_capacity) {
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

/* ----- one-step token issue helpers ----- */

#define SS_TOKEN_ENTROPY_BYTE_COUNT 32

static int issue_base64url_token(
    unsigned char *random_scratch,
    char *token_buffer,
    int token_buffer_capacity,
    int *token_length_out
) {
    int random_status = ss_random_bytes(
        random_scratch,
        SS_TOKEN_ENTROPY_BYTE_COUNT);
    if (random_status != SS_BCRYPT_OK) {
        return random_status;
    }
    return ss_base64url_encode(
        random_scratch,
        SS_TOKEN_ENTROPY_BYTE_COUNT,
        token_buffer,
        token_buffer_capacity,
        token_length_out);
}

int ss_issue_session_token(
    unsigned char *random_scratch,
    char *token_buffer,
    int token_buffer_capacity,
    int *token_length_out
) {
    return issue_base64url_token(
        random_scratch,
        token_buffer,
        token_buffer_capacity,
        token_length_out);
}

int ss_issue_csrf_token(
    unsigned char *random_scratch,
    char *token_buffer,
    int token_buffer_capacity,
    int *token_length_out
) {
    return issue_base64url_token(
        random_scratch,
        token_buffer,
        token_buffer_capacity,
        token_length_out);
}

/* ----- R-202: owned-output helpers (safe-by-construction) -----
 *
 * The buffer-based entry points (ss_bcrypt_hash / ss_base64url_encode /
 * ss_random_bytes) trust a caller-supplied buffer plus a declared capacity, so a
 * caller that under-allocates while over-declaring the capacity overflows — the
 * runtime cannot know the buffer's true size (it lives in another allocator). These
 * owned-output variants ALLOCATE the output themselves at exactly the size the
 * operation needs, so there is no caller buffer to mis-size and an overflow is
 * structurally impossible. They return a heap pointer as an OpaquePointer (i64);
 * the caller frees it with ss_bcrypt_free_string. A small registry tracks the
 * strings WE handed out so the free is double-free / foreign-pointer safe (the
 * sqlite R-139 / event R-196 / json R-198 tombstone pattern). Single-threaded; no
 * lock. */
static void **ss_bcrypt_owned = NULL;
static size_t ss_bcrypt_owned_count = 0;
static size_t ss_bcrypt_owned_cap = 0;

static int ss_bcrypt_owned_track(void *pointer) {
    if (ss_bcrypt_owned_count == ss_bcrypt_owned_cap) {
        size_t next = ss_bcrypt_owned_cap == 0 ? 8 : ss_bcrypt_owned_cap * 2;
        if (ss_bcrypt_owned_cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(void *)) {
            return 0;
        }
        void **grown = (void **)realloc(ss_bcrypt_owned, next * sizeof(void *));
        if (grown == NULL) {
            return 0;
        }
        ss_bcrypt_owned = grown;
        ss_bcrypt_owned_cap = next;
    }
    ss_bcrypt_owned[ss_bcrypt_owned_count++] = pointer;
    return 1;
}

static int ss_bcrypt_owned_untrack(void *pointer) {
    for (size_t i = 0; i < ss_bcrypt_owned_count; i++) {
        if (ss_bcrypt_owned[i] == pointer) {
            ss_bcrypt_owned[i] = ss_bcrypt_owned[ss_bcrypt_owned_count - 1];
            ss_bcrypt_owned_count--;
            return 1;
        }
    }
    return 0;
}

long long ss_bcrypt_hash_owned(const char *plaintext_password, int cost_factor) {
    char *buffer = (char *)malloc(SS_BCRYPT_HASH_OUTPUT_SIZE);
    if (buffer == NULL) {
        return 0;
    }
    int status = ss_bcrypt_hash(plaintext_password, cost_factor,
                                buffer, SS_BCRYPT_HASH_OUTPUT_SIZE);
    if (status != SS_BCRYPT_OK || !ss_bcrypt_owned_track(buffer)) {
        free(buffer);
        return 0;
    }
    return (long long)(intptr_t)buffer;
}

/* R-256: owned no-cost-arg safe default — same allocation contract as
 * ss_bcrypt_hash_owned but pinned to SS_BCRYPT_DEFAULT_COST. */
long long ss_bcrypt_hash_owned_default(const char *plaintext_password) {
    return ss_bcrypt_hash_owned(plaintext_password, SS_BCRYPT_DEFAULT_COST);
}

long long ss_bcrypt_session_token_owned(void) {
    unsigned char scratch[SS_TOKEN_ENTROPY_BYTE_COUNT];
    /* base64url of 32 entropy bytes = 43 chars + NUL. Compute from the entropy
     * count so the allocation always matches what issue_base64url_token writes. */
    int capacity = (((SS_TOKEN_ENTROPY_BYTE_COUNT * 4) + 2) / 3) + 1;
    char *buffer = (char *)malloc((size_t)capacity);
    if (buffer == NULL) {
        return 0;
    }
    int token_length = 0;
    int status = issue_base64url_token(scratch, buffer, capacity, &token_length);
    if (status != SS_BCRYPT_OK || !ss_bcrypt_owned_track(buffer)) {
        free(buffer);
        return 0;
    }
    return (long long)(intptr_t)buffer;
}

void ss_bcrypt_free_string(long long pointer) {
    void *block = (void *)(intptr_t)pointer;
    if (block == NULL || !ss_bcrypt_owned_untrack(block)) {
        return;  /* double free / foreign pointer -> no-op */
    }
    free(block);
}
