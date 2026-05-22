#ifndef SEM_JWT_RUNTIME_H
#define SEM_JWT_RUNTIME_H

/*
 * SemanticScript-owned C ABI for the current HS256 JWT surface.
 *
 * The runtime deliberately exposes only the primitives the language can
 * represent cleanly today: issue a demo access token, verify an access
 * token signature, and format the auth envelopes that contain generated
 * tokens. The server still owns the session state and refresh-token hash.
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

int ss_jwt_hs256_sign_demo_access_token(
    const char *secret,
    char *out_token_buffer,
    int out_token_capacity
);

int ss_jwt_hs256_verify_token(
    const char *token,
    const char *secret
);

int ss_auth_format_login_envelope(
    const char *access_token,
    const char *refresh_token,
    char *out_body_buffer,
    int out_body_capacity
);

int ss_auth_format_refresh_envelope(
    const char *access_token,
    const char *refresh_token,
    char *out_body_buffer,
    int out_body_capacity
);

#ifdef __cplusplus
}
#endif

#endif
