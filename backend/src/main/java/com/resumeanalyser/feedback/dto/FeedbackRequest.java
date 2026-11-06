package com.resumeanalyser.feedback.dto;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

/**
 * Request body for {@code POST /feedback} (FR-10.1): which recommendation the
 * candidate is rating, and whether they found it helpful.
 *
 * @param recommendationId the recommendation being rated
 * @param helpful           whether the candidate found it helpful
 */
public record FeedbackRequest(

        @NotNull
        UUID recommendationId,

        boolean helpful
) {}
