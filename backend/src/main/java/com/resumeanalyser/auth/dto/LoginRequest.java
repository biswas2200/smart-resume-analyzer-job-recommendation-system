package com.resumeanalyser.auth.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * Request body for {@code POST /auth/login}.
 * The email field has no format validation on purpose: telling an attacker
 * "that's not even a valid email" before checking the password would leak
 * information about which accounts exist.
 *
 * @param email    the account's login email
 * @param password the account's plaintext password, checked against the stored bcrypt hash
 */
public record LoginRequest(

        @NotBlank
        String email,

        @NotBlank
        String password
) {}
