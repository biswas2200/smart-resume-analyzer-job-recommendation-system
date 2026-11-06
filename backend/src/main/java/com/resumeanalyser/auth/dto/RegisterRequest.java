package com.resumeanalyser.auth.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * Request body for {@code POST /auth/register}: the details a new user submits to create an account.
 *
 * @param email    the email to register with; must look like a real email and be unique
 * @param password the plaintext password chosen by the user; hashed with bcrypt before storage,
 *                  capped at 72 characters because bcrypt silently truncates/ignores anything beyond
 *                  its 72-byte input limit
 */
public record RegisterRequest(

        @NotBlank
        @Email
        @Size(max = 320)
        String email,

        @NotBlank
        @Size(min = 8, max = 72)
        String password
) {}
