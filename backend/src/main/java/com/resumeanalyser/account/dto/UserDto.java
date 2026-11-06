package com.resumeanalyser.account.dto;

import com.resumeanalyser.account.UserRole;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.UUID;

/**
 * Public-facing view of a {@link com.resumeanalyser.account.User}, used in API
 * responses (e.g. as part of {@link com.resumeanalyser.auth.dto.AuthResponse}).
 * Deliberately excludes the password hash — that field must never leave the server.
 *
 * @param id          the account's database identifier
 * @param email       the account's login email
 * @param role        the account's access level (USER / ADMIN)
 * @param createdAt   when the account was created
 */
public record UserDto(
        UUID id,

        @NotBlank
        @Email
        @Size(max = 320)
        String email,

        UserRole role,

        Instant createdAt
) {}
