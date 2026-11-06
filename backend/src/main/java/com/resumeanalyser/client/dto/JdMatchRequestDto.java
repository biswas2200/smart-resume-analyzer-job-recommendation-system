package com.resumeanalyser.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * Body of the ML service's {@code POST /match-jd}: the candidate's
 * already-extracted skills, the pasted job description, and the domain whose
 * catalogue supplies the closest-role hint.
 */
public record JdMatchRequestDto(
        List<String> skills,

        @JsonProperty("jd_text")
        String jdText,

        String domain
) {}
