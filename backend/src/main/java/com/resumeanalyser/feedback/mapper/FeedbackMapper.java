package com.resumeanalyser.feedback.mapper;

import com.resumeanalyser.feedback.Feedback;
import com.resumeanalyser.feedback.dto.FeedbackDto;
import org.springframework.stereotype.Component;

/** Maps {@link Feedback} entities to their public-facing {@link FeedbackDto}. */
@Component
public class FeedbackMapper {

    public FeedbackDto toDto(Feedback feedback) {
        return new FeedbackDto(
                feedback.getId(),
                feedback.getRecommendation().getId(),
                feedback.getSkillVectorVersion() == null ? null : feedback.getSkillVectorVersion().getId(),
                feedback.isHelpful(),
                feedback.getCreatedAt());
    }
}
