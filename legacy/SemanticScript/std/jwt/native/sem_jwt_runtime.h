#ifndef SEM_JWT_RUNTIME_H
#define SEM_JWT_RUNTIME_H

/*
 * SemanticScript-owned C ABI for the current HS256 JWT surface.
 *
 * The runtime deliberately exposes only generic primitives the language can
 * represent cleanly today: issue an HS256 token from caller-owned claim text,
 * verify a token signature, read flat top-level JWT claims after signature
 * verification, and format token envelopes from caller-supplied fields.
 * Applications own session state, claim policy, and user data.
 */

#ifdef __cplusplus
extern "C" {
#endif

enum {
    SS_JWT_OK = 0,
    SS_JWT_MISMATCH = 0,
    SS_JWT_MATCH = 1,
    SS_JWT_ERR_CONFIG = -1,
    SS_JWT_ERR_RANDOM = -2,
    SS_JWT_ERR_MALFORMED = -3,
    SS_JWT_ERR_OUTPUT_TOO_SMALL = -4
};

int ss_jwt_hs256_sign_json_payload_with_random_jti(
    const char *secret,
    const char *payload_template,
    char *out_token_buffer,
    int out_token_capacity
);

int ss_jwt_hs256_verify_token(
    const char *token,
    const char *secret
);

const char *ss_jwt_read_string_claim(
    const char *token,
    const char *claim_name,
    char *out_claim_buffer,
    int out_claim_capacity
);

long long ss_jwt_read_int64_claim(
    const char *token,
    const char *claim_name,
    long long missing_default
);

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
);

int ss_jwt_format_bearer_refresh_envelope(
    const char *access_token,
    const char *refresh_token,
    char *out_body_buffer,
    int out_body_capacity
);

#ifdef __cplusplus
}
#endif

#endif
