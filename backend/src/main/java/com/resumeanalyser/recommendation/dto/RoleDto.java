package com.resumeanalyser.recommendation.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.UUID;

/**
 * Public-facing view of a {@link com.resumeanalyser.recommendation.Role}.
 *
 * @param id          the role's database identifier
 * @param title       the role's display name
 * @param description free-text description of the role
 */
public record RoleDto(
        UUID id,

        @NotBlank
        String title,

        String description
) {}
