package com.resumeanalyser.recommendation.dto;

import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.UUID;

/**
 * Public-facing view of a {@link com.resumeanalyser.recommendation.Recommendation}.
 *
 * @param id         the recommendation's database identifier
 * @param userId     the id of the account it was generated for
 * @param roleId     the id of the recommended role
 * @param matchScore cosine similarity between the candidate and the role, in [0.0, 1.0]
 * @param createdAt  when this recommendation was generated
 */
public record RecommendationDto(
        UUID id,

        @NotNull
        UUID userId,

        @NotNull
        UUID roleId,

        double matchScore,

        Instant createdAt
) {}
