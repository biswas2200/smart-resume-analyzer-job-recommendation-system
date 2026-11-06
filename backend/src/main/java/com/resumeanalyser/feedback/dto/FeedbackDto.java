package com.resumeanalyser.feedback.dto;

import jakarta.validation.constraints.NotNull;
import java.time.Instant;
import java.util.UUID;

/**
 * Public-facing view of a {@link com.resumeanalyser.feedback.Feedback} entry.
 *
 * @param id                   the feedback row's database identifier
 * @param recommendationId     the id of the recommendation this feedback is about
 * @param skillVectorVersionId the id of the skill-vector version active when the feedback was given, if any
 * @param helpful              whether the user found the recommendation helpful
 * @param createdAt            when the feedback was submitted
 */
public record FeedbackDto(
        UUID id,

        @NotNull
        UUID recommendationId,

        UUID skillVectorVersionId,

        boolean helpful,

        Instant createdAt
) {}
