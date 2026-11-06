package com.resumeanalyser.skillvector.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.UUID;

/**
 * Public-facing view of a {@link com.resumeanalyser.skillvector.SkillVector}.
 *
 * @param id               the skill-vector row's database identifier
 * @param roleId           the id of the role this weighted skill belongs to
 * @param skill            the skill's canonical name
 * @param weight           the skill's current importance to the role
 * @param versionTimestamp when this specific weight value was written
 * @param current          whether this is the active version {@code /match} reads
 */
public record SkillVectorDto(
        UUID id,

        @NotNull
        UUID roleId,

        @NotBlank
        String skill,

        double weight,

        Instant versionTimestamp,

        boolean current
) {}
