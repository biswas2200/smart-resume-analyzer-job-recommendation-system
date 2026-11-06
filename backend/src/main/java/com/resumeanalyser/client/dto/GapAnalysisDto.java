package com.resumeanalyser.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * Mirrors the ML service's {@code GapAnalysis} Pydantic model. Redundant with
 * {@link RoleMatchDto#missingSkills()} for the roles already in {@code matches},
 * but part of {@code AnalyzeResponse}'s shape, so it's declared here rather than
 * silently dropped.
 */
public record GapAnalysisDto(
        String role,

        @JsonProperty("missing_skills")
        List<String> missingSkills
) {}
