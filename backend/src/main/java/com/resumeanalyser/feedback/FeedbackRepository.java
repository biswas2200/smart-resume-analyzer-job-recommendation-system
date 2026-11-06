package com.resumeanalyser.feedback;

import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.recommendation.Role;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Persistence for {@link Feedback}. */
public interface FeedbackRepository extends JpaRepository<Feedback, UUID> {

    /** The most recent feedback given for a recommendation, if any (latest answer wins). */
    Optional<Feedback> findTopByRecommendationOrderByCreatedAtDesc(Recommendation recommendation);

    /** How much feedback has ever been given across all of a role's recommendations. */
    long countByRecommendation_Role(Role role);

    /** Every feedback event given across all of a role's recommendations. */
    List<Feedback> findByRecommendation_Role(Role role);
}
