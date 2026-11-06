package com.resumeanalyser.skillvector;

import com.resumeanalyser.recommendation.Role;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for the core EMA math and versioning in {@link SkillVectorService},
 * matching the formula in docs/lld.md §7 ({@code new_weight = alpha*new_signal + (1-alpha)*old_weight})
 * and the "never mutate in place, always insert a new version" rule (FR-7.4).
 */
@ExtendWith(MockitoExtension.class)
class SkillVectorServiceTest {

    private static final double ALPHA = 0.3;

    @Mock
    private SkillVectorRepository skillVectorRepository;

    private SkillVectorService skillVectorService;
    private Role role;

    @BeforeEach
    void setUp() {
        skillVectorService = new SkillVectorService(skillVectorRepository, ALPHA);

        role = new Role();
        role.setId(UUID.randomUUID());
        role.setTitle("Backend Software Engineer");
    }

    @Test
    void getCurrent_returnsTheExistingCurrentVector_whenOneAlreadyExists() {
        SkillVector existing = vectorFor("java", 0.7);
        when(skillVectorRepository.findByRoleAndSkillAndCurrentTrue(role, "java")).thenReturn(Optional.of(existing));

        SkillVector result = skillVectorService.getCurrent(role, "java");

        assertThat(result).isSameAs(existing);
        verify(skillVectorRepository, never()).save(any());
    }

    @Test
    void getCurrent_initializesAVectorAtTheDefaultWeight_whenNoneExistsYet() {
        when(skillVectorRepository.findByRoleAndSkillAndCurrentTrue(role, "kotlin")).thenReturn(Optional.empty());
        when(skillVectorRepository.save(any(SkillVector.class))).thenAnswer(inv -> inv.getArgument(0));

        SkillVector result = skillVectorService.getCurrent(role, "kotlin");

        assertThat(result.getRole()).isSameAs(role);
        assertThat(result.getSkill()).isEqualTo("kotlin");
        assertThat(result.getWeight()).isEqualTo(SkillVectorService.DEFAULT_WEIGHT);
        assertThat(result.isCurrent()).isTrue();
        verify(skillVectorRepository).save(result);
    }

    @Test
    void ensureInitialized_createsExactlyOneVectorPerDistinctSkill_ignoringDuplicatesInTheInput() {
        when(skillVectorRepository.findByRoleAndSkillAndCurrentTrue(eq(role), any())).thenReturn(Optional.empty());
        when(skillVectorRepository.save(any(SkillVector.class))).thenAnswer(inv -> inv.getArgument(0));

        skillVectorService.ensureInitialized(role, List.of("java", "sql", "java"));

        verify(skillVectorRepository, times(1)).save(argThat(sv -> sv.getSkill().equals("java")));
        verify(skillVectorRepository, times(1)).save(argThat(sv -> sv.getSkill().equals("sql")));
        verify(skillVectorRepository, times(2)).save(any(SkillVector.class));
    }

    @Test
    void recompute_computesEmaAgainstTheDefaultWeight_whenThisSkillHasNeverBeenScoredBefore() {
        when(skillVectorRepository.findByRoleAndSkillAndCurrentTrue(role, "python")).thenReturn(Optional.empty());
        when(skillVectorRepository.save(any(SkillVector.class))).thenAnswer(inv -> inv.getArgument(0));

        SkillVector result = skillVectorService.recompute(role, "python", 1.0);

        double expected = ALPHA * 1.0 + (1 - ALPHA) * SkillVectorService.DEFAULT_WEIGHT;
        assertThat(result.getWeight()).isEqualTo(expected);
        assertThat(result.isCurrent()).isTrue();
        verify(skillVectorRepository, times(1)).save(any(SkillVector.class));
    }

    @Test
    void recompute_computesEmaAgainstThePriorWeight_andRetiresThatVersionWithoutMutatingIt() {
        SkillVector priorVersion = vectorFor("sql", 0.6);
        when(skillVectorRepository.findByRoleAndSkillAndCurrentTrue(role, "sql")).thenReturn(Optional.of(priorVersion));
        when(skillVectorRepository.save(any(SkillVector.class))).thenAnswer(inv -> inv.getArgument(0));

        SkillVector result = skillVectorService.recompute(role, "sql", 0.9);

        double expected = ALPHA * 0.9 + (1 - ALPHA) * 0.6;
        assertThat(result.getWeight()).isEqualTo(expected);
        assertThat(result.isCurrent()).isTrue();
        assertThat(result).isNotSameAs(priorVersion);
        assertThat(priorVersion.isCurrent())
                .as("the prior version is retired (current=false), never deleted or overwritten -- FR-7.4")
                .isFalse();

        ArgumentCaptor<SkillVector> captor = ArgumentCaptor.forClass(SkillVector.class);
        verify(skillVectorRepository, times(2)).save(captor.capture());
        assertThat(captor.getAllValues()).containsExactlyInAnyOrder(priorVersion, result);
    }

    @Test
    void recomputeAll_recomputesEveryEntryInTheSignalMap() {
        when(skillVectorRepository.findByRoleAndSkillAndCurrentTrue(eq(role), any())).thenReturn(Optional.empty());
        when(skillVectorRepository.save(any(SkillVector.class))).thenAnswer(inv -> inv.getArgument(0));

        List<SkillVector> results = skillVectorService.recomputeAll(role, Map.of("java", 1.0, "cobol", 0.0));

        assertThat(results).hasSize(2);
        assertThat(results).extracting(SkillVector::getSkill).containsExactlyInAnyOrder("java", "cobol");
    }

    private SkillVector vectorFor(String skill, double weight) {
        SkillVector sv = new SkillVector();
        sv.setId(UUID.randomUUID());
        sv.setRole(role);
        sv.setSkill(skill);
        sv.setWeight(weight);
        sv.setCurrent(true);
        return sv;
    }
}
