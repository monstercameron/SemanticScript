#include "sem_jwt_runtime.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#  define WIN32_LEAN_AND_MEAN
#  include <windows.h>
#  include <bcrypt.h>
#  pragma comment(lib, "bcrypt.lib")
#elif defined(__linux__)
#  include <errno.h>
#  include <sys/random.h>
#else
#  include <fcntl.h>
#  include <unistd.h>
#endif

#define SHA256_BLOCK_SIZE 64
#define SHA256_DIGEST_SIZE 32

typedef struct SSJwtSha256Ctx {
    uint8_t data[SHA256_BLOCK_SIZE];
    uint32_t datalen;
    uint64_t bitlen;
    uint32_t state[8];
} SSJwtSha256Ctx;

static const uint32_t sha256_k[64] = {
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U,
    0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
    0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U,
    0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
    0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU,
    0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U,
    0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
    0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U,
    0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
    0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U,
    0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U,
    0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
    0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U,
    0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U
};

static uint32_t rotr32(uint32_t value, uint32_t count) {
    return (value >> count) | (value << (32U - count));
}

static uint32_t choose32(uint32_t x, uint32_t y, uint32_t z) {
    return (x & y) ^ (~x & z);
}

static uint32_t majority32(uint32_t x, uint32_t y, uint32_t z) {
    return (x & y) ^ (x & z) ^ (y & z);
}

static void sha256_transform(SSJwtSha256Ctx *ctx, const uint8_t data[]) {
    uint32_t message[64];
    for (uint32_t i = 0; i < 16; ++i) {
        message[i] =
            ((uint32_t)data[i * 4] << 24) |
            ((uint32_t)data[i * 4 + 1] << 16) |
            ((uint32_t)data[i * 4 + 2] << 8) |
            ((uint32_t)data[i * 4 + 3]);
    }
    for (uint32_t i = 16; i < 64; ++i) {
        uint32_t s0 =
            rotr32(message[i - 15], 7) ^
            rotr32(message[i - 15], 18) ^
            (message[i - 15] >> 3);
        uint32_t s1 =
            rotr32(message[i - 2], 17) ^
            rotr32(message[i - 2], 19) ^
            (message[i - 2] >> 10);
        message[i] = message[i - 16] + s0 + message[i - 7] + s1;
    }

    uint32_t a = ctx->state[0];
    uint32_t b = ctx->state[1];
    uint32_t c = ctx->state[2];
    uint32_t d = ctx->state[3];
    uint32_t e = ctx->state[4];
    uint32_t f = ctx->state[5];
    uint32_t g = ctx->state[6];
    uint32_t h = ctx->state[7];

    for (uint32_t i = 0; i < 64; ++i) {
        uint32_t s1 = rotr32(e, 6) ^ rotr32(e, 11) ^ rotr32(e, 25);
        uint32_t temp1 = h + s1 + choose32(e, f, g) + sha256_k[i] + message[i];
        uint32_t s0 = rotr32(a, 2) ^ rotr32(a, 13) ^ rotr32(a, 22);
        uint32_t temp2 = s0 + majority32(a, b, c);
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    ctx->state[0] += a;
    ctx->state[1] += b;
    ctx->state[2] += c;
    ctx->state[3] += d;
    ctx->state[4] += e;
    ctx->state[5] += f;
    ctx->state[6] += g;
    ctx->state[7] += h;
}

static void sha256_init(SSJwtSha256Ctx *ctx) {
    ctx->datalen = 0;
    ctx->bitlen = 0;
    ctx->state[0] = 0x6a09e667U;
    ctx->state[1] = 0xbb67ae85U;
    ctx->state[2] = 0x3c6ef372U;
    ctx->state[3] = 0xa54ff53aU;
    ctx->state[4] = 0x510e527fU;
    ctx->state[5] = 0x9b05688cU;
    ctx->state[6] = 0x1f83d9abU;
    ctx->state[7] = 0x5be0cd19U;
}

static void sha256_update(SSJwtSha256Ctx *ctx, const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        ctx->data[ctx->datalen++] = data[i];
        if (ctx->datalen == SHA256_BLOCK_SIZE) {
            sha256_transform(ctx, ctx->data);
            ctx->bitlen += 512;
            ctx->datalen = 0;
        }
    }
}

static void sha256_final(SSJwtSha256Ctx *ctx, uint8_t hash[SHA256_DIGEST_SIZE]) {
    uint32_t i = ctx->datalen;

    ctx->data[i++] = 0x80;
    if (i > 56) {
        while (i < 64) {
            ctx->data[i++] = 0x00;
        }
        sha256_transform(ctx, ctx->data);
        i = 0;
    }
    while (i < 56) {
        ctx->data[i++] = 0x00;
    }

    ctx->bitlen += ((uint64_t)ctx->datalen) * 8U;
    ctx->data[63] = (uint8_t)(ctx->bitlen);
    ctx->data[62] = (uint8_t)(ctx->bitlen >> 8);
    ctx->data[61] = (uint8_t)(ctx->bitlen >> 16);
    ctx->data[60] = (uint8_t)(ctx->bitlen >> 24);
    ctx->data[59] = (uint8_t)(ctx->bitlen >> 32);
    ctx->data[58] = (uint8_t)(ctx->bitlen >> 40);
    ctx->data[57] = (uint8_t)(ctx->bitlen >> 48);
    ctx->data[56] = (uint8_t)(ctx->bitlen >> 56);
    sha256_transform(ctx, ctx->data);

    for (i = 0; i < 4; ++i) {
        hash[i] = (uint8_t)((ctx->state[0] >> (24 - i * 8)) & 0xff);
        hash[i + 4] = (uint8_t)((ctx->state[1] >> (24 - i * 8)) & 0xff);
        hash[i + 8] = (uint8_t)((ctx->state[2] >> (24 - i * 8)) & 0xff);
        hash[i + 12] = (uint8_t)((ctx->state[3] >> (24 - i * 8)) & 0xff);
        hash[i + 16] = (uint8_t)((ctx->state[4] >> (24 - i * 8)) & 0xff);
        hash[i + 20] = (uint8_t)((ctx->state[5] >> (24 - i * 8)) & 0xff);
        hash[i + 24] = (uint8_t)((ctx->state[6] >> (24 - i * 8)) & 0xff);
        hash[i + 28] = (uint8_t)((ctx->state[7] >> (24 - i * 8)) & 0xff);
    }
}

static void sha256_bytes(
    const uint8_t *data,
    size_t data_len,
    uint8_t hash[SHA256_DIGEST_SIZE]
) {
    SSJwtSha256Ctx ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, data, data_len);
    sha256_final(&ctx, hash);
}

static void hmac_sha256(
    const uint8_t *key,
    size_t key_len,
    const uint8_t *message,
    size_t message_len,
    uint8_t out[SHA256_DIGEST_SIZE]
) {
    uint8_t normalized_key[SHA256_BLOCK_SIZE];
    uint8_t inner_pad[SHA256_BLOCK_SIZE];
    uint8_t outer_pad[SHA256_BLOCK_SIZE];
    uint8_t inner_hash[SHA256_DIGEST_SIZE];
    memset(normalized_key, 0, sizeof(normalized_key));
    if (key_len > SHA256_BLOCK_SIZE) {
        sha256_bytes(key, key_len, normalized_key);
    } else {
        memcpy(normalized_key, key, key_len);
    }

    for (size_t i = 0; i < SHA256_BLOCK_SIZE; ++i) {
        inner_pad[i] = (uint8_t)(normalized_key[i] ^ 0x36U);
        outer_pad[i] = (uint8_t)(normalized_key[i] ^ 0x5cU);
    }

    SSJwtSha256Ctx ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, inner_pad, sizeof(inner_pad));
    sha256_update(&ctx, message, message_len);
    sha256_final(&ctx, inner_hash);

    sha256_init(&ctx);
    sha256_update(&ctx, outer_pad, sizeof(outer_pad));
    sha256_update(&ctx, inner_hash, sizeof(inner_hash));
    sha256_final(&ctx, out);
}

static const char base64url_alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

static int base64url_encode(
    const uint8_t *input,
    int input_len,
    char *output,
    int output_capacity
) {
    if (input == NULL || output == NULL || input_len < 0) {
        return SS_JWT_ERR_CONFIG;
    }
    int required = ((input_len * 4) + 2) / 3 + 1;
    if (output_capacity < required) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }

    int input_index = 0;
    int output_index = 0;
    while (input_index + 3 <= input_len) {
        uint32_t triplet =
            ((uint32_t)input[input_index] << 16) |
            ((uint32_t)input[input_index + 1] << 8) |
            ((uint32_t)input[input_index + 2]);
        output[output_index++] = base64url_alphabet[(triplet >> 18) & 0x3fU];
        output[output_index++] = base64url_alphabet[(triplet >> 12) & 0x3fU];
        output[output_index++] = base64url_alphabet[(triplet >> 6) & 0x3fU];
        output[output_index++] = base64url_alphabet[triplet & 0x3fU];
        input_index += 3;
    }
    int remaining = input_len - input_index;
    if (remaining == 1) {
        uint32_t last = (uint32_t)input[input_index] << 16;
        output[output_index++] = base64url_alphabet[(last >> 18) & 0x3fU];
        output[output_index++] = base64url_alphabet[(last >> 12) & 0x3fU];
    } else if (remaining == 2) {
        uint32_t last =
            ((uint32_t)input[input_index] << 16) |
            ((uint32_t)input[input_index + 1] << 8);
        output[output_index++] = base64url_alphabet[(last >> 18) & 0x3fU];
        output[output_index++] = base64url_alphabet[(last >> 12) & 0x3fU];
        output[output_index++] = base64url_alphabet[(last >> 6) & 0x3fU];
    }
    output[output_index] = '\0';
    return SS_JWT_OK;
}

static int base64url_decode_value(char ch) {
    if (ch >= 'A' && ch <= 'Z') {
        return ch - 'A';
    }
    if (ch >= 'a' && ch <= 'z') {
        return ch - 'a' + 26;
    }
    if (ch >= '0' && ch <= '9') {
        return ch - '0' + 52;
    }
    if (ch == '-') {
        return 62;
    }
    if (ch == '_') {
        return 63;
    }
    return -1;
}

static int base64url_decode(
    const char *input,
    int input_len,
    uint8_t *output,
    int output_capacity,
    int *output_len
) {
    if (input == NULL || output == NULL || output_len == NULL || input_len < 0) {
        return SS_JWT_ERR_CONFIG;
    }
    if ((input_len % 4) == 1) {
        return SS_JWT_ERR_MALFORMED;
    }

    int input_index = 0;
    int output_index = 0;
    while (input_index < input_len) {
        int remaining = input_len - input_index;
        int chunk = remaining >= 4 ? 4 : remaining;
        int values[4] = {0, 0, 0, 0};
        for (int index = 0; index < chunk; ++index) {
            values[index] = base64url_decode_value(input[input_index + index]);
            if (values[index] < 0) {
                return SS_JWT_ERR_MALFORMED;
            }
        }

        if (output_index + 3 > output_capacity) {
            return SS_JWT_ERR_OUTPUT_TOO_SMALL;
        }
        uint32_t triple =
            ((uint32_t)values[0] << 18) |
            ((uint32_t)values[1] << 12) |
            ((uint32_t)values[2] << 6) |
            ((uint32_t)values[3]);
        output[output_index++] = (uint8_t)((triple >> 16) & 0xffU);
        if (chunk >= 3) {
            output[output_index++] = (uint8_t)((triple >> 8) & 0xffU);
        }
        if (chunk == 4) {
            output[output_index++] = (uint8_t)(triple & 0xffU);
        }
        input_index += chunk;
    }
    *output_len = output_index;
    return SS_JWT_OK;
}

static const char *jwt_skip_ws(const char *cursor) {
    while (*cursor == ' ' || *cursor == '\n' || *cursor == '\r' || *cursor == '\t') {
        ++cursor;
    }
    return cursor;
}

static int decode_jwt_payload_json(
    const char *token,
    char *out_payload_buffer,
    int out_payload_capacity
) {
    if (token == NULL || out_payload_buffer == NULL || out_payload_capacity <= 0) {
        return SS_JWT_ERR_CONFIG;
    }
    const char *first_dot = strchr(token, '.');
    if (first_dot == NULL) {
        return SS_JWT_ERR_MALFORMED;
    }
    const char *second_dot = strchr(first_dot + 1, '.');
    if (second_dot == NULL || strchr(second_dot + 1, '.') != NULL) {
        return SS_JWT_ERR_MALFORMED;
    }

    int payload_len = (int)(second_dot - first_dot - 1);
    int decoded_len = 0;
    int status = base64url_decode(
        first_dot + 1,
        payload_len,
        (uint8_t *)out_payload_buffer,
        out_payload_capacity - 1,
        &decoded_len);
    if (status != SS_JWT_OK) {
        return status;
    }
    out_payload_buffer[decoded_len] = '\0';
    return SS_JWT_OK;
}

static const char *skip_json_string(const char *cursor) {
    if (cursor == NULL || *cursor != '"') {
        return NULL;
    }
    ++cursor;
    while (*cursor != '\0') {
        if (*cursor == '"') {
            return cursor + 1;
        }
        if (*cursor == '\\') {
            ++cursor;
            if (*cursor == '\0') {
                return NULL;
            }
            if (*cursor == 'u') {
                for (int i = 0; i < 4; ++i) {
                    ++cursor;
                    if (*cursor == '\0') {
                        return NULL;
                    }
                }
            }
            ++cursor;
            continue;
        }
        ++cursor;
    }
    return NULL;
}

static const char *skip_json_value(const char *cursor) {
    cursor = jwt_skip_ws(cursor);
    if (*cursor == '"') {
        return skip_json_string(cursor);
    }
    if (*cursor == '{' || *cursor == '[') {
        char opener = *cursor;
        char closer = opener == '{' ? '}' : ']';
        int depth = 1;
        ++cursor;
        while (*cursor != '\0' && depth > 0) {
            if (*cursor == '"') {
                cursor = skip_json_string(cursor);
                if (cursor == NULL) {
                    return NULL;
                }
                continue;
            }
            if (*cursor == opener) {
                ++depth;
            } else if (*cursor == closer) {
                --depth;
            } else if ((opener == '{' && *cursor == '[')
                || (opener == '[' && *cursor == '{')) {
                const char *nested = skip_json_value(cursor);
                if (nested == NULL) {
                    return NULL;
                }
                cursor = nested;
                continue;
            }
            ++cursor;
        }
        return depth == 0 ? cursor : NULL;
    }
    while (*cursor != '\0'
        && *cursor != ','
        && *cursor != '}'
        && *cursor != ']'
        && *cursor != ' '
        && *cursor != '\n'
        && *cursor != '\r'
        && *cursor != '\t') {
        ++cursor;
    }
    return cursor;
}

static int json_simple_field_name_equals(
    const char *field_string,
    const char *claim_name
) {
    if (field_string == NULL || claim_name == NULL || *field_string != '"') {
        return 0;
    }
    const char *cursor = field_string + 1;
    const char *name = claim_name;
    while (*cursor != '\0' && *cursor != '"') {
        if (*cursor == '\\') {
            return 0;
        }
        if (*name == '\0' || *cursor != *name) {
            return 0;
        }
        ++cursor;
        ++name;
    }
    return *cursor == '"' && *name == '\0';
}

static const char *find_top_level_claim_value(
    const char *payload_json,
    const char *claim_name
) {
    const char *cursor = jwt_skip_ws(payload_json);
    if (*cursor != '{') {
        return NULL;
    }
    ++cursor;
    while (*cursor != '\0') {
        cursor = jwt_skip_ws(cursor);
        if (*cursor == '}') {
            return NULL;
        }
        if (*cursor != '"') {
            return NULL;
        }
        int matches = json_simple_field_name_equals(cursor, claim_name);
        cursor = skip_json_string(cursor);
        if (cursor == NULL) {
            return NULL;
        }
        cursor = jwt_skip_ws(cursor);
        if (*cursor != ':') {
            return NULL;
        }
        ++cursor;
        const char *value = jwt_skip_ws(cursor);
        if (matches) {
            return value;
        }
        cursor = skip_json_value(value);
        if (cursor == NULL) {
            return NULL;
        }
        cursor = jwt_skip_ws(cursor);
        if (*cursor == ',') {
            ++cursor;
            continue;
        }
        if (*cursor == '}') {
            return NULL;
        }
        return NULL;
    }
    return NULL;
}

static int hex_digit_value(char ch) {
    if (ch >= '0' && ch <= '9') {
        return ch - '0';
    }
    if (ch >= 'a' && ch <= 'f') {
        return ch - 'a' + 10;
    }
    if (ch >= 'A' && ch <= 'F') {
        return ch - 'A' + 10;
    }
    return -1;
}

static const char *copy_json_string_claim(
    const char *value,
    char *out_claim_buffer,
    int out_claim_capacity
) {
    if (value == NULL
        || out_claim_buffer == NULL
        || out_claim_capacity <= 0
        || *value != '"') {
        return NULL;
    }
    ++value;
    int out_index = 0;
    while (*value != '\0') {
        if (*value == '"') {
            if (out_index >= out_claim_capacity) {
                return NULL;
            }
            out_claim_buffer[out_index] = '\0';
            return out_claim_buffer;
        }
        char next = *value;
        if (next == '\\') {
            ++value;
            switch (*value) {
                case '"': next = '"'; break;
                case '\\': next = '\\'; break;
                case '/': next = '/'; break;
                case 'b': next = '\b'; break;
                case 'f': next = '\f'; break;
                case 'n': next = '\n'; break;
                case 'r': next = '\r'; break;
                case 't': next = '\t'; break;
                case 'u': {
                    int code = 0;
                    for (int i = 0; i < 4; ++i) {
                        ++value;
                        int digit = hex_digit_value(*value);
                        if (digit < 0) {
                            return NULL;
                        }
                        code = (code << 4) | digit;
                    }
                    next = (code >= 0 && code <= 0x7f) ? (char)code : '?';
                    break;
                }
                default:
                    return NULL;
            }
        }
        if (out_index + 1 >= out_claim_capacity) {
            return NULL;
        }
        out_claim_buffer[out_index++] = next;
        ++value;
    }
    return NULL;
}

static int jwt_random_bytes(uint8_t *out, int byte_count) {
    if (out == NULL || byte_count <= 0) {
        return SS_JWT_ERR_CONFIG;
    }
#if defined(_WIN32)
    NTSTATUS status = BCryptGenRandom(
        NULL, out, (ULONG)byte_count, BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    return status == 0 ? SS_JWT_OK : SS_JWT_ERR_RANDOM;
#elif defined(__linux__)
    int total_read = 0;
    while (total_read < byte_count) {
        ssize_t step = getrandom(
            out + total_read, (size_t)(byte_count - total_read), 0);
        if (step < 0) {
            if (errno == EINTR) {
                continue;
            }
            return SS_JWT_ERR_RANDOM;
        }
        total_read += (int)step;
    }
    return SS_JWT_OK;
#else
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) {
        return SS_JWT_ERR_RANDOM;
    }
    int total_read = 0;
    while (total_read < byte_count) {
        ssize_t step = read(
            fd, out + total_read, (size_t)(byte_count - total_read));
        if (step <= 0) {
            close(fd);
            return SS_JWT_ERR_RANDOM;
        }
        total_read += (int)step;
    }
    close(fd);
    return SS_JWT_OK;
#endif
}

static int constant_time_equal(const char *left, const char *right, size_t len) {
    unsigned char diff = 0;
    for (size_t i = 0; i < len; ++i) {
        diff |= (unsigned char)(left[i] ^ right[i]);
    }
    return diff == 0 ? 1 : 0;
}

static int payload_template_has_exactly_one_string_placeholder(
    const char *template_text
) {
    int placeholder_count = 0;

    if (template_text == NULL) {
        return 0;
    }

    for (const char *cursor = template_text; *cursor != '\0'; ++cursor) {
        if (*cursor != '%') {
            continue;
        }

        ++cursor;
        if (*cursor == '\0') {
            return 0;
        }
        if (*cursor == '%') {
            continue;
        }
        if (*cursor == 's') {
            ++placeholder_count;
            if (placeholder_count > 1) {
                return 0;
            }
            continue;
        }
        return 0;
    }

    return placeholder_count == 1;
}

static int sign_header_payload(
    const char *header_payload,
    const char *secret,
    char *out_token_buffer,
    int out_token_capacity
) {
    if (header_payload == NULL || secret == NULL || out_token_buffer == NULL) {
        return SS_JWT_ERR_CONFIG;
    }

    size_t header_payload_len = strlen(header_payload);
    uint8_t mac[SHA256_DIGEST_SIZE];
    hmac_sha256(
        (const uint8_t *)secret,
        strlen(secret),
        (const uint8_t *)header_payload,
        header_payload_len,
        mac);

    char signature[44];
    int encode_status = base64url_encode(
        mac, SHA256_DIGEST_SIZE, signature, (int)sizeof(signature));
    if (encode_status != SS_JWT_OK) {
        return encode_status;
    }

    int required = (int)header_payload_len + 1 + 43 + 1;
    if (out_token_capacity < required) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }
    int written = snprintf(
        out_token_buffer,
        (size_t)out_token_capacity,
        "%s.%s",
        header_payload,
        signature);
    if (written < 0 || written >= out_token_capacity) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }
    return SS_JWT_OK;
}

int ss_jwt_hs256_sign_json_payload_with_random_jti(
    const char *secret,
    const char *payload_template,
    char *out_token_buffer,
    int out_token_capacity
) {
    if (secret == NULL || payload_template == NULL || out_token_buffer == NULL) {
        return SS_JWT_ERR_CONFIG;
    }
    if (out_token_capacity <= 0) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }
    if (!payload_template_has_exactly_one_string_placeholder(payload_template)) {
        return SS_JWT_ERR_CONFIG;
    }

    static const char header_json[] =
        "{\"alg\":\"HS256\",\"typ\":\"JWT\"}";
    char encoded_header[96];
    int header_status = base64url_encode(
        (const uint8_t *)header_json,
        (int)strlen(header_json),
        encoded_header,
        (int)sizeof(encoded_header));
    if (header_status != SS_JWT_OK) {
        return header_status;
    }

    uint8_t jti_entropy[16];
    int random_status = jwt_random_bytes(jti_entropy, (int)sizeof(jti_entropy));
    if (random_status != SS_JWT_OK) {
        return random_status;
    }
    char jti[24];
    int jti_status = base64url_encode(
        jti_entropy, (int)sizeof(jti_entropy), jti, (int)sizeof(jti));
    if (jti_status != SS_JWT_OK) {
        return jti_status;
    }

    char payload_json[512];
    int payload_written = snprintf(
        payload_json,
        sizeof(payload_json),
        payload_template,
        jti);
    if (payload_written < 0 || payload_written >= (int)sizeof(payload_json)) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }

    char encoded_payload[768];
    int payload_status = base64url_encode(
        (const uint8_t *)payload_json,
        payload_written,
        encoded_payload,
        (int)sizeof(encoded_payload));
    if (payload_status != SS_JWT_OK) {
        return payload_status;
    }

    char header_payload[900];
    int header_payload_written = snprintf(
        header_payload,
        sizeof(header_payload),
        "%s.%s",
        encoded_header,
        encoded_payload);
    if (header_payload_written < 0
        || header_payload_written >= (int)sizeof(header_payload)) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }

    return sign_header_payload(
        header_payload,
        secret,
        out_token_buffer,
        out_token_capacity);
}

int ss_jwt_hs256_verify_token(
    const char *token,
    const char *secret
) {
    if (token == NULL || secret == NULL) {
        return SS_JWT_ERR_CONFIG;
    }
    const char *first_dot = strchr(token, '.');
    if (first_dot == NULL) {
        return SS_JWT_ERR_MALFORMED;
    }
    const char *second_dot = strchr(first_dot + 1, '.');
    if (second_dot == NULL || strchr(second_dot + 1, '.') != NULL) {
        return SS_JWT_ERR_MALFORMED;
    }

    size_t header_payload_len = (size_t)(second_dot - token);
    const char *signature = second_dot + 1;
    size_t signature_len = strlen(signature);
    if (signature_len != 43) {
        return SS_JWT_MISMATCH;
    }

    uint8_t mac[SHA256_DIGEST_SIZE];
    hmac_sha256(
        (const uint8_t *)secret,
        strlen(secret),
        (const uint8_t *)token,
        header_payload_len,
        mac);
    char expected_signature[44];
    int encode_status = base64url_encode(
        mac, SHA256_DIGEST_SIZE,
        expected_signature, (int)sizeof(expected_signature));
    if (encode_status != SS_JWT_OK) {
        return encode_status;
    }
    return constant_time_equal(signature, expected_signature, 43)
        ? SS_JWT_MATCH
        : SS_JWT_MISMATCH;
}

const char *ss_jwt_read_string_claim(
    const char *token,
    const char *claim_name,
    char *out_claim_buffer,
    int out_claim_capacity
) {
    char payload_json[1024];
    int decode_status = decode_jwt_payload_json(
        token, payload_json, (int)sizeof(payload_json));
    if (decode_status != SS_JWT_OK) {
        return NULL;
    }
    const char *value = find_top_level_claim_value(payload_json, claim_name);
    return copy_json_string_claim(value, out_claim_buffer, out_claim_capacity);
}

long long ss_jwt_read_int64_claim(
    const char *token,
    const char *claim_name,
    long long missing_default
) {
    char payload_json[1024];
    int decode_status = decode_jwt_payload_json(
        token, payload_json, (int)sizeof(payload_json));
    if (decode_status != SS_JWT_OK) {
        return missing_default;
    }
    const char *value = find_top_level_claim_value(payload_json, claim_name);
    if (value == NULL) {
        return missing_default;
    }
    char *end = NULL;
    long long parsed = strtoll(value, &end, 10);
    if (end == value) {
        return missing_default;
    }
    return parsed;
}

int ss_jwt_format_bearer_login_envelope(
    const char *access_token,
    const char *refresh_token,
    const char *user_id,
    const char *username,
    const char *display_name,
    const char *role_name,
    const char *scopes_json,
    char *out_body_buffer,
    int out_body_capacity
) {
    if (access_token == NULL
        || refresh_token == NULL
        || user_id == NULL
        || username == NULL
        || display_name == NULL
        || role_name == NULL
        || scopes_json == NULL
        || out_body_buffer == NULL) {
        return SS_JWT_ERR_CONFIG;
    }
    if (out_body_capacity <= 0) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }
    int written = snprintf(
        out_body_buffer,
        (size_t)out_body_capacity,
        "{\"apiVersion\":\"v1\",\"requestId\":\"req_runtime_header_unavailable\","
        "\"ok\":true,\"data\":{\"tokenType\":\"Bearer\","
        "\"accessToken\":\"%s\",\"expiresInSeconds\":900,"
        "\"refreshToken\":\"%s\","
        "\"user\":{\"id\":\"%s\",\"username\":\"%s\","
        "\"displayName\":\"%s\",\"role\":\"%s\","
        "\"scopes\":%s},"
        "\"crypto\":\"HS256\"},\"error\":null}\n",
        access_token,
        refresh_token,
        user_id,
        username,
        display_name,
        role_name,
        scopes_json);
    if (written < 0 || written >= out_body_capacity) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }
    return SS_JWT_OK;
}

int ss_jwt_format_bearer_refresh_envelope(
    const char *access_token,
    const char *refresh_token,
    char *out_body_buffer,
    int out_body_capacity
) {
    if (access_token == NULL || refresh_token == NULL || out_body_buffer == NULL) {
        return SS_JWT_ERR_CONFIG;
    }
    if (out_body_capacity <= 0) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }
    int written = snprintf(
        out_body_buffer,
        (size_t)out_body_capacity,
        "{\"apiVersion\":\"v1\",\"requestId\":\"req_runtime_header_unavailable\","
        "\"ok\":true,\"data\":{\"tokenType\":\"Bearer\","
        "\"accessToken\":\"%s\",\"expiresInSeconds\":900,"
        "\"refreshToken\":\"%s\",\"rotated\":true},\"error\":null}\n",
        access_token,
        refresh_token);
    if (written < 0 || written >= out_body_capacity) {
        return SS_JWT_ERR_OUTPUT_TOO_SMALL;
    }
    return SS_JWT_OK;
}
