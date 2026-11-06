package com.resumeanalyser.feedback;

import com.resumeanalyser.account.User;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.recommendation.RecommendationRepository;
import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.skillvector.SkillVector;
import com.resumeanalyser.skillvector.SkillVectorService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Stream;

/**
 * Records and looks up a candidate's helpful/not-helpful verdict on a
 * recommendation (FR-10.1), and drives the temporal EMA skill-vector update
 * from it (FR-7.1-FR-7.4): once a role's feedback count crosses
 * {@code app.skill-vector.feedback-threshold}, every skill that role's
 * feedback has touched gets its weight recomputed. See docs/process-flow.md
 * §4 for the end-to-end flow this class implements.
 */
@Service
public class FeedbackService {

    private final FeedbackRepository feedbackRepository;
    private final RecommendationRepository recommendationRepository;
    private final SkillVectorService skillVectorService;
    private final int feedbackThreshold;

    /**
     * @param feedbackRepository       persistence for {@link Feedback}
     * @param recommendationRepository persistence for {@link Recommendation}, used to verify ownership
     * @param skillVectorService       the EMA update engine this class feeds signals into
     * @param feedbackThreshold        how much feedback on a role triggers an automatic recompute
     *                                 ({@code app.skill-vector.feedback-threshold}) -- the "enough
     *                                 feedback accumulated" branch in docs/process-flow.md §4
     */
    public FeedbackService(
            FeedbackRepository feedbackRepository,
            RecommendationRepository recommendationRepository,
            SkillVectorService skillVectorService,
            @Value("${app.skill-vector.feedback-threshold}") int feedbackThreshold
    ) {
        this.feedbackRepository = feedbackRepository;
        this.recommendationRepository = recommendationRepository;
        this.skillVectorService = skillVectorService;
        this.feedbackThreshold = feedbackThreshold;
    }

    /**
     * Records the candidate's verdict on one of their own recommendations,
     * links it to the skill-vector version active right now (FR-10.2), and --
     * once enough feedback has accumulated for this role -- recomputes that
     * role's skill weights from it.
     *
     * @throws ResourceNotFoundException if the recommendation doesn't exist or
     *         doesn't belong to {@code user}
     */
    @Transactional
    public Feedback submit(User user, UUID recommendationId, boolean helpful) {
        Recommendation recommendation = ownedRecommendation(user, recommendationId);

        Feedback feedback = new Feedback();
        feedback.setRecommendation(recommendation);
        feedback.setHelpful(helpful);
        feedback.setSkillVectorVersion(representativeSkillVector(recommendation));
        feedback = feedbackRepository.save(feedback);

        Role role = recommendation.getRole();
        if (feedbackRepository.countByRecommendation_Role(role) % feedbackThreshold == 0) {
            recomputeSkillVectors(role);
        }

        return feedback;
    }

    /**
     * The most recent feedback given for one of the user's own recommendations.
     *
     * @throws ResourceNotFoundException if the recommendation doesn't exist or
     *         doesn't belong to {@code user}
     */
    public Optional<Feedback> getLatestFeedback(User user, UUID recommendationId) {
        Recommendation recommendation = ownedRecommendation(user, recommendationId);
        return feedbackRepository.findTopByRecommendationOrderByCreatedAtDesc(recommendation);
    }

    /**
     * Recomputes every skill weight {@code role}'s accumulated feedback has
     * touched -- the actual EMA update (FR-7.2). Called automatically by
     * {@link #submit} once enough feedback exists, or manually via the
     * admin-only recompute endpoint ({@code SkillVectorController}).
     *
     * @param role the role whose skill vectors should be recomputed
     * @return the newly written, now-current skill-vector rows
     */
    public List<SkillVector> recomputeSkillVectors(Role role) {
        return skillVectorService.recomputeAll(role, computeSignals(role));
    }

    /**
     * Turns all of a role's accumulated feedback into one helpful-ratio signal
     * per skill: for each skill any of the role's recommendations matched on,
     * the fraction of feedback events that were "helpful" among all feedback
     * whose recommendation matched that skill. This is the {@code new_signal}
     * FR-7.2's formula is computed from -- job-market data is a separate,
     * post-MVP signal source (see docs/database-schema.md §3) not implemented here.
     */
    private Map<String, Double> computeSignals(Role role) {
        Map<String, long[]> tally = new HashMap<>(); // skill -> [helpfulCount, totalCount]

        for (Feedback feedback : feedbackRepository.findByRecommendation_Role(role)) {
            for (String skill : feedback.getRecommendation().getMatchedSkills()) {
                long[] counts = tally.computeIfAbsent(skill, unused -> new long[2]);
                counts[1]++;
                if (feedback.isHelpful()) {
                    counts[0]++;
                }
            }
        }

        Map<String, Double> signals = new HashMap<>();
        tally.forEach((skill, counts) -> signals.put(skill, (double) counts[0] / counts[1]));
        return signals;
    }

    /**
     * The single {@link SkillVector} this feedback event is linked to for audit
     * purposes (FR-10.2). A recommendation touches several skills but
     * {@code Feedback} can only reference one vector row, so this picks a
     * representative: the first matched skill, or the first missing skill if
     * there were no matches, or {@code null} if the recommendation has no
     * skills recorded at all.
     */
    private SkillVector representativeSkillVector(Recommendation recommendation) {
        return Stream.concat(recommendation.getMatchedSkills().stream(), recommendation.getMissingSkills().stream())
                .findFirst()
                .map(skill -> skillVectorService.getCurrent(recommendation.getRole(), skill))
                .orElse(null);
    }

    private Recommendation ownedRecommendation(User user, UUID recommendationId) {
        return recommendationRepository.findById(recommendationId)
                .filter(r -> r.getUser().getId().equals(user.getId()))
                .orElseThrow(() -> new ResourceNotFoundException("Recommendation not found: " + recommendationId));
    }
}
