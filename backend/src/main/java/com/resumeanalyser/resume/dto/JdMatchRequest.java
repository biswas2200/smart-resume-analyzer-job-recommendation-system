package com.resumeanalyser.resume.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * Body of {@code POST /resumes/{id}/jd-match}: a job description pasted as
 * free text (FR-8.1). The size cap matches the ML service's own limit.
 *
 * @param jdText the job description to match the resume against
 */
public record JdMatchRequest(
        @NotBlank
        @Size(max = 20_000)
        String jdText
) {}
