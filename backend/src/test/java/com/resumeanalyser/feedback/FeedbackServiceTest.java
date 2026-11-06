package com.resumeanalyser.feedback;

import com.resumeanalyser.account.User;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.recommendation.RecommendationRepository;
import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.skillvector.SkillVector;
import com.resumeanalyser.skillvector.SkillVectorService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link FeedbackService}: recording feedback, linking it to a
 * skill-vector version (FR-10.2), and triggering the EMA recompute once a
 * role's feedback count crosses the threshold, per docs/process-flow.md §4.
 */
@ExtendWith(MockitoExtension.class)
class FeedbackServiceTest {

    private static final int THRESHOLD = 5;

    @Mock
    private FeedbackRepository feedbackRepository;

    @Mock
    private RecommendationRepository recommendationRepository;

    @Mock
    private SkillVectorService skillVectorService;

    private FeedbackService feedbackService;
    private User user;
    private Role role;
    private Recommendation recommendation;

    @BeforeEach
    void setUp() {
        feedbackService = new FeedbackService(feedbackRepository, recommendationRepository, skillVectorService, THRESHOLD);

        user = new User();
        user.setId(UUID.randomUUID());

        role = new Role();
        role.setId(UUID.randomUUID());
        role.setTitle("Backend Software Engineer");

        recommendation = new Recommendation();
        recommendation.setId(UUID.randomUUID());
        recommendation.setUser(user);
        recommendation.setRole(role);
        recommendation.setMatchedSkills(List.of("java", "sql"));
        recommendation.setMissingSkills(List.of("kafka"));
    }

    /** Only tests that look up {@link #recommendation} by id need this. */
    private void stubRecommendationFindable() {
        when(recommendationRepository.findById(recommendation.getId())).thenReturn(Optional.of(recommendation));
    }

    /** Only tests that actually reach a successful save need this. */
    private void stubFeedbackSavePassthrough() {
        when(feedbackRepository.save(any(Feedback.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    @Test
    void submit_persistsFeedback_linkedToTheOwnedRecommendation() {
        stubRecommendationFindable();
        stubFeedbackSavePassthrough();
        when(feedbackRepository.countByRecommendation_Role(role)).thenReturn(1L);
        when(skillVectorService.getCurrent(role, "java")).thenReturn(vectorFor("java"));

        Feedback feedback = feedbackService.submit(user, recommendation.getId(), true);

        assertThat(feedback.getRecommendation()).isSameAs(recommendation);
        assertThat(feedback.isHelpful()).isTrue();
    }

    @Test
    void submit_throwsResourceNotFound_whenTheRecommendationDoesNotBelongToThisUser() {
        stubRecommendationFindable();
        User someoneElse = new User();
        someoneElse.setId(UUID.randomUUID());
        UUID recommendationId = recommendation.getId();

        assertThatThrownBy(() -> feedbackService.submit(someoneElse, recommendationId, true))
                .isInstanceOf(ResourceNotFoundException.class);

        verifyNoInteractions(feedbackRepository, skillVectorService);
    }

    @Test
    void submit_throwsResourceNotFound_whenTheRecommendationDoesNotExist() {
        UUID missingId = UUID.randomUUID();
        when(recommendationRepository.findById(missingId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> feedbackService.submit(user, missingId, true))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void submit_linksFeedbackToTheCurrentVectorOfTheFirstMatchedSkill() {
        stubRecommendationFindable();
        stubFeedbackSavePassthrough();
        when(feedbackRepository.countByRecommendation_Role(role)).thenReturn(1L);
        SkillVector javaVector = vectorFor("java");
        when(skillVectorService.getCurrent(role, "java")).thenReturn(javaVector);

        Feedback feedback = feedbackService.submit(user, recommendation.getId(), true);

        assertThat(feedback.getSkillVectorVersion()).isSameAs(javaVector);
    }

    @Test
    void submit_fallsBackToAMissingSkill_whenThereAreNoMatchedSkills() {
        stubRecommendationFindable();
        stubFeedbackSavePassthrough();
        recommendation.setMatchedSkills(List.of());
        when(feedbackRepository.countByRecommendation_Role(role)).thenReturn(1L);
        SkillVector kafkaVector = vectorFor("kafka");
        when(skillVectorService.getCurrent(role, "kafka")).thenReturn(kafkaVector);

        Feedback feedback = feedbackService.submit(user, recommendation.getId(), false);

        assertThat(feedback.getSkillVectorVersion()).isSameAs(kafkaVector);
    }

    @Test
    void submit_leavesSkillVectorVersionNull_whenTheRecommendationHasNoSkillsRecordedAtAll() {
        stubRecommendationFindable();
        stubFeedbackSavePassthrough();
        recommendation.setMatchedSkills(List.of());
        recommendation.setMissingSkills(List.of());
        when(feedbackRepository.countByRecommendation_Role(role)).thenReturn(1L);

        Feedback feedback = feedbackService.submit(user, recommendation.getId(), true);

        assertThat(feedback.getSkillVectorVersion()).isNull();
        verifyNoInteractions(skillVectorService);
    }

    @Test
    void submit_doesNotTriggerARecompute_beforeTheFeedbackThresholdIsReached() {
        stubRecommendationFindable();
        stubFeedbackSavePassthrough();
        when(feedbackRepository.countByRecommendation_Role(role)).thenReturn(3L);
        when(skillVectorService.getCurrent(role, "java")).thenReturn(vectorFor("java"));

        feedbackService.submit(user, recommendation.getId(), true);

        verify(feedbackRepository, never()).findByRecommendation_Role(any());
        verify(skillVectorService, never()).recomputeAll(any(), any());
    }

    @Test
    void submit_triggersARecompute_onceTheRolesFeedbackCountReachesTheThreshold() {
        stubRecommendationFindable();
        stubFeedbackSavePassthrough();
        when(feedbackRepository.countByRecommendation_Role(role)).thenReturn((long) THRESHOLD);
        when(skillVectorService.getCurrent(role, "java")).thenReturn(vectorFor("java"));
        when(feedbackRepository.findByRecommendation_Role(role))
                .thenReturn(List.of(feedbackTouching(List.of("java"), true), feedbackTouching(List.of("java"), false)));

        feedbackService.submit(user, recommendation.getId(), true);

        verify(skillVectorService).recomputeAll(role, Map.of("java", 0.5));
    }

    @Test
    void recomputeSkillVectors_turnsHelpfulRatioPerSkillIntoTheSignalMap() {
        Feedback helpfulJavaAndSql = feedbackTouching(List.of("java", "sql"), true);
        Feedback unhelpfulJavaOnly = feedbackTouching(List.of("java"), false);
        when(feedbackRepository.findByRecommendation_Role(role)).thenReturn(List.of(helpfulJavaAndSql, unhelpfulJavaOnly));
        when(skillVectorService.recomputeAll(any(), any())).thenReturn(List.of());

        feedbackService.recomputeSkillVectors(role);

        verify(skillVectorService).recomputeAll(role, Map.of("java", 0.5, "sql", 1.0));
    }

    private SkillVector vectorFor(String skill) {
        SkillVector sv = new SkillVector();
        sv.setId(UUID.randomUUID());
        sv.setRole(role);
        sv.setSkill(skill);
        sv.setWeight(1.0);
        sv.setCurrent(true);
        return sv;
    }

    private Feedback feedbackTouching(List<String> matchedSkills, boolean helpful) {
        Recommendation r = new Recommendation();
        r.setRole(role);
        r.setMatchedSkills(matchedSkills);
        r.setMissingSkills(List.of());

        Feedback feedback = new Feedback();
        feedback.setRecommendation(r);
        feedback.setHelpful(helpful);
        return feedback;
    }
}
