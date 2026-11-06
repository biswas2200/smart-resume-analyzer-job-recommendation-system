package com.resumeanalyser.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * Mirrors the ML service's {@code JdMatchResponse} (services/jd_match.py):
 * a deterministic score for one resume against one pasted job description,
 * with the JD's recognised skills split into matched and missing.
 */
public record JdMatchResponseDto(
        double score,
        double coverage,
        double similarity,

        @JsonProperty("jd_skills")
        List<String> jdSkills,

        @JsonProperty("matched_skills")
        List<String> matchedSkills,

        @JsonProperty("missing_skills")
        List<String> missingSkills,

        /** The catalogue role the JD most resembles; null when nothing was recognised. */
        @JsonProperty("closest_role")
        RoleMatchDto closestRole,

        String explanation
) {}
