#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../../semanticscript/runtime/native_bcrypt/sem_bcrypt_runtime.h"

static int any_nonzero(const unsigned char *buffer, size_t length) {
    for (size_t i = 0; i < length; i++) {
        if (buffer[i] != 0) {
            return 1;
        }
    }
    return 0;
}

int main(void) {
    char hash[SS_BCRYPT_HASH_OUTPUT_SIZE];
    unsigned char random[32] = {0};
    unsigned char bytes[] = {0x00, 0x01, 0x02, 0xfb, 0xff};
    char encoded[16];
    int encoded_len = 0;

    assert(ss_bcrypt_hash(NULL, 4, hash, sizeof(hash)) == SS_BCRYPT_ERR_CONFIG);
    assert(ss_bcrypt_hash("correct horse battery staple", 3, hash, sizeof(hash)) == SS_BCRYPT_ERR_CONFIG);
    assert(ss_bcrypt_hash("correct horse battery staple", 4, hash, 16) == SS_BCRYPT_ERR_CONFIG);

    assert(ss_bcrypt_hash("correct horse battery staple", 4, hash, sizeof(hash)) == SS_BCRYPT_OK);
    assert(strlen(hash) == 60);
    assert(strncmp(hash, "$2b$04$", 7) == 0);
    assert(ss_bcrypt_verify("correct horse battery staple", hash) == SS_BCRYPT_MATCH);
    assert(ss_bcrypt_verify("wrong password", hash) == SS_BCRYPT_MISMATCH);
    assert(ss_bcrypt_verify("correct horse battery staple", "$2b$04$short") == SS_BCRYPT_ERR_MALFORMED);

    assert(ss_random_bytes(random, (int)sizeof(random)) == SS_BCRYPT_OK);
    assert(any_nonzero(random, sizeof(random)));

    assert(ss_base64url_encode(bytes, (int)sizeof(bytes), encoded, sizeof(encoded), &encoded_len)
           == SS_BCRYPT_OK);
    assert(encoded_len == 7);
    assert(strcmp(encoded, "AAEC-_8") == 0);
    assert(ss_base64url_encode(bytes, (int)sizeof(bytes), encoded, 4, &encoded_len)
           == SS_BCRYPT_ERR_CONFIG);

    long long owned_hash = ss_bcrypt_hash_owned("correct horse battery staple", 4);
    assert(owned_hash != 0);
    assert(ss_bcrypt_verify("correct horse battery staple", (const char *)(intptr_t)owned_hash)
           == SS_BCRYPT_MATCH);
    ss_bcrypt_free_string(owned_hash);
    ss_bcrypt_free_string(owned_hash);

    long long owned_token = ss_bcrypt_session_token_owned();
    assert(owned_token != 0);
    assert(strlen((const char *)(intptr_t)owned_token) == 43);
    assert(strchr((const char *)(intptr_t)owned_token, '=') == NULL);
    ss_bcrypt_free_string(owned_token);

    printf("harness_bcrypt: OK\n");
    return 0;
}
