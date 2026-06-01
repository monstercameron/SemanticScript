#ifndef SEM_BCRYPT_RUNTIME_H
#define SEM_BCRYPT_RUNTIME_H

/*
 * SemanticScript-owned C ABI for password hashing + cryptographic
 * randomness + base64url encoding. The actual hashing comes from the
 * vendored crypt_blowfish 1.3 amalgamation at third_party/bcrypt/;
 * this adapter is the only thing in the project that talks to it
 * directly.
 *
 * Surface design
 *
 *   - All entry points return an `int` status code from the
 *     SS_BCRYPT_* enums below.
 *   - The verify entry point ALSO returns the match outcome through
 *     the integer return value: SS_BCRYPT_MATCH (1) on hash equality,
 *     SS_BCRYPT_MISMATCH (2) on inequality, or a negative SS_BCRYPT_ERR_*
 *     code on malformed input. We deliberately collapse "do they match"
 *     and "did the verify succeed" into one return value because the
 *     two questions are inseparable for a constant-time check — there
 *     is no "verify succeeded but the answer is no" path that a caller
 *     could meaningfully distinguish from a malformed-input failure.
 *
 *   - The hash entry point writes a 60-character bcrypt string
 *     ($2b$<cost>$<22-char-base64-salt><31-char-base64-hash>) plus a
 *     terminating NUL into the caller's buffer. The buffer must be at
 *     least SS_BCRYPT_HASH_OUTPUT_SIZE bytes; smaller buffers return
 *     SS_BCRYPT_ERR_CONFIG.
 *
 *   - random_bytes uses the runtime-wide native_platform CSPRNG helper.
 *     It does NOT call the bcrypt hasher; bcrypt is only one consumer of
 *     the shared entropy backend used for salts, session tokens, CSRF
 *     tokens, and future random-capability APIs.
 *
 *   - base64url_encode emits the URL-safe alphabet (-, _) with NO
 *     padding. Output is null-terminated. Same return-int-status
 *     convention; output_length_out reports the bytes actually written
 *     (excluding the terminator).
 */

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    SS_BCRYPT_OK              = 0,
    SS_BCRYPT_MATCH           = 1,   /* verify: the password matches the hash */
    /* R-255: MISMATCH is DISTINCT from OK (0). Sharing 0 with OK was an
     * auth-bypass footgun — a caller following the dominant "0 == success"
     * convention would treat a wrong password (mismatch) as success. A verify
     * caller MUST test `== SS_BCRYPT_MATCH`; any other non-negative value is a
     * non-match, and negatives are errors. */
    SS_BCRYPT_MISMATCH        = 2,
    SS_BCRYPT_ERR_CONFIG      = -1,  /* NULL inputs, undersized buffers, out-of-range cost */
    SS_BCRYPT_ERR_HASH        = -2,  /* crypt_blowfish returned NULL */
    SS_BCRYPT_ERR_RANDOM      = -3,  /* platform CSPRNG failed */
    SS_BCRYPT_ERR_MALFORMED   = -4   /* verify saw a stored hash that isn't a valid bcrypt setting */
};

/*
 * Exact byte count required by the bcrypt hash output buffer (60
 * format chars + 1 NUL terminator). Callers that allocate exactly
 * this much will fit any valid $2b$ output for cost 4..31.
 */
#define SS_BCRYPT_HASH_OUTPUT_SIZE 61

/*
 * The supported cost range. Cost 4 is the absolute minimum the
 * format permits; cost 31 is the format ceiling. Cost 12 is the
 * recommended production value in 2026 (~250ms per hash on a typical
 * server CPU).
 */
#define SS_BCRYPT_MIN_COST 4
#define SS_BCRYPT_MAX_COST 31

int ss_bcrypt_hash(
    const char *plaintext_password,
    int cost_factor,
    char *out_hash_buffer,
    int out_hash_buffer_capacity
);

int ss_bcrypt_verify(
    const char *plaintext_password,
    const char *expected_hash_60_chars
);

int ss_random_bytes(unsigned char *out_buffer, int byte_count);

int ss_base64url_encode(
    const unsigned char *input_buffer,
    int input_byte_count,
    char *output_buffer,
    int output_buffer_capacity,
    int *output_length_out
);

int ss_issue_session_token(
    unsigned char *random_scratch,
    char *token_buffer,
    int token_buffer_capacity,
    int *token_length_out
);

int ss_issue_csrf_token(
    unsigned char *random_scratch,
    char *token_buffer,
    int token_buffer_capacity,
    int *token_length_out
);

/* R-202: owned-output variants — allocate the output themselves (no caller
 * buffer, so an overflow is structurally impossible) and return an OpaquePointer
 * (i64) the caller frees with ss_bcrypt_free_string. Returns 0 on failure. */
long long ss_bcrypt_hash_owned(const char *plaintext_password, int cost_factor);
long long ss_bcrypt_session_token_owned(void);
void ss_bcrypt_free_string(long long pointer);

#ifdef __cplusplus
}
#endif

#endif
