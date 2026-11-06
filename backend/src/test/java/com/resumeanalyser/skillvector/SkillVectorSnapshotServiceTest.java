package com.resumeanalyser.skillvector;

import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.skillvector.dto.WeightsSnapshotDto;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link SkillVectorSnapshotService}, matching the exported
 * shape docs/lld.md §7.4 defines: {@code {snapshot_id, created_at, sha256,
 * weights{role -> skill -> weight}}} (FR-7.5).
 */
@ExtendWith(MockitoExtension.class)
class SkillVectorSnapshotServiceTest {

    @Mock
    private SkillVectorRepository skillVectorRepository;

    private SkillVectorSnapshotService snapshotService;

    @BeforeEach
    void setUp() {
        snapshotService = new SkillVectorSnapshotService(skillVectorRepository);
    }

    @Test
    void exportSnapshot_groupsWeightsByRoleTitleThenSkill() {
        Role backend = roleOf("Backend Software Engineer");
        Role frontend = roleOf("Frontend Software Engineer");
        when(skillVectorRepository.findByCurrentTrue()).thenReturn(List.of(
                vectorOf(backend, "Java", 0.8),
                vectorOf(backend, "SQL", 0.6),
                vectorOf(frontend, "React", 0.9)
        ));

        WeightsSnapshotDto snapshot = snapshotService.exportSnapshot();

        assertThat(snapshot.weights())
                .containsEntry("Backend Software Engineer", java.util.Map.of("Java", 0.8, "SQL", 0.6))
                .containsEntry("Frontend Software Engineer", java.util.Map.of("React", 0.9));
    }

    @Test
    void exportSnapshot_returnsAnEmptyWeightsMap_whenNoSkillVectorsExistYet() {
        when(skillVectorRepository.findByCurrentTrue()).thenReturn(List.of());

        WeightsSnapshotDto snapshot = snapshotService.exportSnapshot();

        assertThat(snapshot.weights()).isEmpty();
    }

    @Test
    void exportSnapshot_setsSnapshotIdToTheCreatedAtInstantAsAString() {
        when(skillVectorRepository.findByCurrentTrue()).thenReturn(List.of());

        WeightsSnapshotDto snapshot = snapshotService.exportSnapshot();

        assertThat(snapshot.snapshotId()).isEqualTo(snapshot.createdAt().toString());
        assertThat(Instant.parse(snapshot.snapshotId())).isEqualTo(snapshot.createdAt());
    }

    @Test
    void exportSnapshot_producesTheSameHash_forTheSameWeightsRegardlessOfInputOrder() {
        Role backend = roleOf("Backend Software Engineer");
        when(skillVectorRepository.findByCurrentTrue())
                .thenReturn(List.of(vectorOf(backend, "Java", 0.8), vectorOf(backend, "SQL", 0.6)))
                .thenReturn(List.of(vectorOf(backend, "SQL", 0.6), vectorOf(backend, "Java", 0.8)));

        String firstHash = snapshotService.exportSnapshot().sha256();
        String secondHash = snapshotService.exportSnapshot().sha256();

        assertThat(firstHash).isEqualTo(secondHash);
        assertThat(firstHash).hasSize(64);
    }

    @Test
    void exportSnapshot_producesADifferentHash_whenTheWeightsDiffer() {
        Role backend = roleOf("Backend Software Engineer");
        when(skillVectorRepository.findByCurrentTrue())
                .thenReturn(List.of(vectorOf(backend, "Java", 0.8)))
                .thenReturn(List.of(vectorOf(backend, "Java", 0.5)));

        String firstHash = snapshotService.exportSnapshot().sha256();
        String secondHash = snapshotService.exportSnapshot().sha256();

        assertThat(firstHash).isNotEqualTo(secondHash);
    }

    private Role roleOf(String title) {
        Role role = new Role();
        role.setId(UUID.randomUUID());
        role.setTitle(title);
        return role;
    }

    private SkillVector vectorOf(Role role, String skill, double weight) {
        SkillVector vector = new SkillVector();
        vector.setId(UUID.randomUUID());
        vector.setRole(role);
        vector.setSkill(skill);
        vector.setWeight(weight);
        vector.setCurrent(true);
        return vector;
    }
}
