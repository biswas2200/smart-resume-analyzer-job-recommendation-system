package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.client.MlServiceClient;
import com.resumeanalyser.client.MlServiceException;
import com.resumeanalyser.client.dto.MarketDemandDto;
import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.recommendation.RecommendationRepository;
import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.recommendation.RoleRepository;
import com.resumeanalyser.resume.ParsedProfile;
import com.resumeanalyser.resume.ParsedProfileRepository;
import com.resumeanalyser.resume.Resume;
import com.resumeanalyser.resume.ResumeRepository;
import com.resumeanalyser.skillvector.SkillVector;
import com.resumeanalyser.skillvector.SkillVectorService;
import com.resumeanalyser.skillvector.SkillVectorSnapshotService;
import com.resumeanalyser.skillvector.dto.WeightsSnapshotDto;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** The job-market signal: storing demand, feeding the EMA weights, installing them, and the user's view. */
@ExtendWith(MockitoExtension.class)
class MarketDemandTest {

    private static final Instant NOW = Instant.parse("2026-10-22T06:30:00Z");

    @Mock private MarketSkillDemandRepository demand;
    @Mock private RoleRepository roles;
    @Mock private SkillVectorService skillVectors;
    @Mock private JobPostingRepository postings;
    @Mock private SkillVectorSnapshotService snapshots;
    @Mock private MlServiceClient ml;
    @Mock private ResumeRepository resumes;
    @Mock private ParsedProfileRepository profiles;
    @Mock private RecommendationRepository recommendations;

    private static final MarketDemandDto.RoleDemand BACKEND = new MarketDemandDto.RoleDemand(
            "Backend Software Engineer", "engineering", 12,
            List.of(new MarketDemandDto.SkillDemand("Java", 0.75), new MarketDemandDto.SkillDemand("Kafka", 0.42)),
            Map.of("Java", 1.0, "Kafka", 0.78, "Docker", 0.5));

    @Test
    void store_replacesTheDemandTable_andFeedsEachRolesSignalsIntoItsEmaWeights() {
        MarketDemandStore store = new MarketDemandStore(demand, roles, skillVectors);
        when(roles.findByTitle("Backend Software Engineer")).thenReturn(Optional.empty());
        when(roles.save(any(Role.class))).thenAnswer(inv -> inv.getArgument(0));
        when(skillVectors.recomputeAll(any(), any())).thenReturn(List.of(new SkillVector(), new SkillVector(), new SkillVector()));

        int updated = store.store(new MarketDemandDto.Response(List.of(BACKEND), 40), NOW);

        assertThat(updated).isEqualTo(3);
        verify(demand).deleteAllRows();
        ArgumentCaptor<MarketSkillDemand> rows = ArgumentCaptor.forClass(MarketSkillDemand.class);
        verify(demand, org.mockito.Mockito.times(2)).save(rows.capture());
        assertThat(rows.getAllValues()).extracting(MarketSkillDemand::getSkill).containsExactly("Java", "Kafka");
        assertThat(rows.getAllValues().get(0).getJobCount()).isEqualTo(12);
        ArgumentCaptor<Role> role = ArgumentCaptor.forClass(Role.class);
        verify(skillVectors).recomputeAll(role.capture(), eq(BACKEND.signals()));
        assertThat(role.getValue().getTitle()).isEqualTo("Backend Software Engineer");
        assertThat(role.getValue().getDomain()).isEqualTo("engineering");
    }

    private MarketDemandService service(MarketDemandStore store) {
        return new MarketDemandService(postings, store, demand, snapshots, ml, resumes, profiles, recommendations,
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    @Test
    void update_sendsOnlyJobsWithSkills_thenInstallsTheNewWeights() {
        MarketDemandStore store = org.mockito.Mockito.mock(MarketDemandStore.class);
        JobPosting withSkills = posting("Backend Engineer", List.of("Java"));
        JobPosting notYetRead = posting("Designer", null);
        when(postings.findAllByActiveTrueOrderByFirstSeenAtDesc(any())).thenReturn(List.of(withSkills, notYetRead));
        MarketDemandDto.Response result = new MarketDemandDto.Response(List.of(BACKEND), 0);
        when(ml.marketDemand(any())).thenReturn(result);
        when(store.store(result, NOW)).thenReturn(3);
        WeightsSnapshotDto snapshot = new WeightsSnapshotDto("s1", NOW, "x", Map.of());
        when(snapshots.exportSnapshot()).thenReturn(snapshot);

        String summary = service(store).update();

        verify(ml).marketDemand(org.mockito.ArgumentMatchers.argThat(jobs -> jobs.size() == 1));
        verify(ml).pushWeights(snapshot);
        assertThat(summary).contains("1 roles measured", "3 skill weights updated");
    }

    @Test
    void update_keepsTheOldWeights_whenTheMlServiceIsDown() {
        MarketDemandStore store = org.mockito.Mockito.mock(MarketDemandStore.class);
        when(postings.findAllByActiveTrueOrderByFirstSeenAtDesc(any())).thenReturn(List.of());
        MlServiceException down = new MlServiceException("Could not reach the ML service", false, null);
        when(ml.marketDemand(any())).thenThrow(down);

        assertThat(service(store).update()).startsWith("market demand not updated");
        verify(store, never()).store(any(), any());
        verify(ml, never()).pushWeights(any());
    }

    @Test
    void forUser_showsDemandForTheTopRoles_markingSkillsTheResumeHas() {
        User user = new User();
        Resume resume = new Resume();
        ParsedProfile profile = new ParsedProfile();
        profile.setSkills(List.of("java", "Docker"));
        Role role = new Role();
        role.setTitle("Backend Software Engineer");
        Recommendation match = new Recommendation();
        match.setRole(role);
        match.setMatchedSkills(List.of("SQL"));
        Role other = new Role();
        other.setTitle("Data Analyst");
        Recommendation second = new Recommendation();
        second.setRole(other);
        second.setMatchedSkills(List.of());
        when(resumes.findTopByUserOrderByVersionDesc(user)).thenReturn(Optional.of(resume));
        when(profiles.findByResume(resume)).thenReturn(Optional.of(profile));
        when(recommendations.findByResumeOrderByMatchScoreDesc(resume)).thenReturn(List.of(match, second));
        when(demand.findByRoleTitleOrderByShareDescSkillAsc("Backend Software Engineer"))
                .thenReturn(List.of(row("Java", 0.75), row("Kafka", 0.42), row("SQL", 0.3)));
        when(demand.findByRoleTitleOrderByShareDescSkillAsc("Data Analyst")).thenReturn(List.of());

        var view = service(null).forUser(user);

        assertThat(view.roles()).hasSize(2);
        var backend = view.roles().get(0);
        assertThat(backend.jobCount()).isEqualTo(12);
        assertThat(backend.skills()).extracting(s -> s.skill() + "=" + s.have())
                .containsExactly("Java=true", "Kafka=false", "SQL=true");
        assertThat(view.roles().get(1).jobCount()).isZero();
    }

    @Test
    void forUser_withoutAResume_isEmpty() {
        when(resumes.findTopByUserOrderByVersionDesc(any())).thenReturn(Optional.empty());
        assertThat(service(null).forUser(new User()).roles()).isEmpty();
    }

    private static MarketSkillDemand row(String skill, double share) {
        MarketSkillDemand row = new MarketSkillDemand();
        row.setSkill(skill);
        row.setShare(share);
        row.setJobCount(12);
        row.setComputedAt(NOW);
        return row;
    }

    private static JobPosting posting(String title, List<String> skills) {
        JobPosting posting = new JobPosting();
        posting.setId(UUID.randomUUID());
        posting.setTitle(title);
        posting.setSkills(skills);
        return posting;
    }
}
