package com.resumeanalyser.resume.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.time.Instant;
import java.util.UUID;

/**
 * Public-facing view of a {@link com.resumeanalyser.resume.Resume}.
 *
 * @param id         the resume's database identifier
 * @param userId     the id of the account that uploaded it
 * @param fileRef    object-storage pointer to the actual resume file
 * @param version    this upload's position in the user's upload history
 * @param uploadedAt when this version was uploaded
 */
public record ResumeDto(
        UUID id,

        @NotNull
        UUID userId,

        @NotBlank
        String fileRef,

        @PositiveOrZero
        int version,

        Instant uploadedAt
) {}
