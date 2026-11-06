package com.resumeanalyser.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * Mirrors the ML service's {@code AtsScoreResponse} Pydantic model field-for-field,
 * including its snake_case {@code max_score} field.
 */
public record AtsScoreResponseDto(
        double score,

        @JsonProperty("max_score")
        double maxScore,

        List<AtsCheckDto> checks
) {

    /** Mirrors the ML service's {@code AtsCheck}. */
    public record AtsCheckDto(String name, boolean passed, String detail) {}
}
