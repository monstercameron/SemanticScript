#include "sem_bcrypt_runtime.h"

#include <stdio.h>
#include <string.h>

/*
 * Smoke demo for the native_bcrypt adapter. Verifies:
 *
 *   1. ss_bcrypt_hash produces a 60-char $2b$… string at cost 12.
 *   2. The same plaintext + a NEW call produces a DIFFERENT hash
 *      (proving salt randomness is non-deterministic across calls).
 *   3. ss_bcrypt_verify matches the correct plaintext (returns 1).
 *   4. ss_bcrypt_verify rejects a wrong plaintext (returns 0).
 *   5. ss_bcrypt_verify rejects a malformed stored hash (returns negative).
 *   6. ss_random_bytes fills exactly the requested count and is
 *      non-zero (statistically — extremely unlikely to be all zeros
 *      across 32 bytes).
 *   7. ss_base64url_encode produces the right length and uses only
 *      the URL-safe alphabet (no padding, no + or /).
 *
 * Exit 0 on success; non-zero with a stage tag on any failure.
 */

static int fail(const char *stage, int status) {
    fprintf(stderr, "sem_bcrypt_health_demo: %s failed status=%d\n", stage, status);
    return 1;
}

int main(void) {
    int rc;

    /* (1) hash at cost 12 (production-grade) */
    char hash_a[SS_BCRYPT_HASH_OUTPUT_SIZE];
    rc = ss_bcrypt_hash("correct-horse-battery-staple", 12,
                        hash_a, sizeof(hash_a));
    if (rc != SS_BCRYPT_OK) return fail("hash-cost-12", rc);
    if (strlen(hash_a) != 60) return fail("hash-length", (int)strlen(hash_a));
    if (memcmp(hash_a, "$2b$12$", 7) != 0) return fail("hash-prefix", 0);

    /* (2) re-hash same plaintext — must produce different output */
    char hash_b[SS_BCRYPT_HASH_OUTPUT_SIZE];
    rc = ss_bcrypt_hash("correct-horse-battery-staple", 12,
                        hash_b, sizeof(hash_b));
    if (rc != SS_BCRYPT_OK) return fail("hash-rerun", rc);
    if (memcmp(hash_a, hash_b, 60) == 0) {
        return fail("salt-randomness", 0);  /* salts collided */
    }

    /* (3) verify against the correct plaintext */
    rc = ss_bcrypt_verify("correct-horse-battery-staple", hash_a);
    if (rc != SS_BCRYPT_MATCH) return fail("verify-correct", rc);

    /* (4) reject wrong plaintext */
    rc = ss_bcrypt_verify("wrong-password", hash_a);
    if (rc != SS_BCRYPT_MISMATCH) return fail("verify-wrong", rc);

    /* (5) reject malformed stored hash */
    rc = ss_bcrypt_verify("anything",
                          "not-a-real-bcrypt-hash-and-the-wrong-length-too-zz");
    if (rc != SS_BCRYPT_ERR_MALFORMED) {
        return fail("verify-malformed", rc);
    }

    /* (6) random bytes — non-zero, exact-count */
    unsigned char random_buf[32];
    memset(random_buf, 0, sizeof(random_buf));
    rc = ss_random_bytes(random_buf, sizeof(random_buf));
    if (rc != SS_BCRYPT_OK) return fail("random-bytes", rc);
    int any_nonzero = 0;
    for (size_t i = 0; i < sizeof(random_buf); ++i) {
        if (random_buf[i] != 0) {
            any_nonzero = 1;
            break;
        }
    }
    if (!any_nonzero) return fail("random-bytes-all-zero", 0);

    /* (7) base64url encode the 32 random bytes — must produce exactly
     * 43 chars, no padding, alphabet limited to A-Za-z0-9-_. */
    char encoded[64];
    int encoded_length = 0;
    rc = ss_base64url_encode(random_buf, (int)sizeof(random_buf),
                              encoded, sizeof(encoded),
                              &encoded_length);
    if (rc != SS_BCRYPT_OK) return fail("base64url-encode", rc);
    if (encoded_length != 43) return fail("base64url-length", encoded_length);
    for (int i = 0; i < encoded_length; ++i) {
        char c = encoded[i];
        int valid = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')
                 || (c >= '0' && c <= '9') || c == '-' || c == '_';
        if (!valid) return fail("base64url-alphabet", (int)(unsigned char)c);
    }

    printf("sem_bcrypt_health_demo: hash=%s\n", hash_a);
    printf("sem_bcrypt_health_demo: token=%s\n", encoded);
    printf("sem_bcrypt_health_demo: ok\n");
    return 0;
}
