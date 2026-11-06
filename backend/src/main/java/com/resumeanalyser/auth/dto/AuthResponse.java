package com.resumeanalyser.auth.dto;

import com.resumeanalyser.account.dto.UserDto;
import java.time.Instant;

/**
 * Response body returned by both {@code POST /auth/register} and {@code POST /auth/login}:
 * a freshly issued access token plus who it belongs to.
 *
 * @param token     the signed JWT the client must send back as {@code Authorization: Bearer <token>}
 * @param tokenType always "Bearer" -- included so clients don't have to hardcode the auth scheme
 * @param expiresAt when this token stops being valid
 * @param user      the account the token was issued for
 */
public record AuthResponse(
        String token,
        String tokenType,
        Instant expiresAt,
        UserDto user
) {

    /**
     * Builds an {@link AuthResponse} for a Bearer token, filling in the fixed {@code tokenType}
     * so callers don't have to repeat the literal "Bearer" string everywhere a token is issued.
     *
     * @param token     the signed JWT
     * @param expiresAt when the token expires
     * @param user      the account the token belongs to
     * @return a ready-to-return AuthResponse
     */
    public static AuthResponse bearer(String token, Instant expiresAt, UserDto user) {
        return new AuthResponse(token, "Bearer", expiresAt, user);
    }
}
