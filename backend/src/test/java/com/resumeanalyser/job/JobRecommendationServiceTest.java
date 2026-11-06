package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.client.MlServiceClient;
import com.resumeanalyser.client.dto.RankJobsDto;
import com.resumeanalyser.job.dto.RecommendedJobsResponse;
import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.recommendation.RecommendationRepository;
import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.resume.ParsedProfile;
import com.resumeanalyser.resume.ParsedProfileRepository;
import com.resumeanalyser.resume.Resume;
import com.resumeanalyser.resume.ResumeRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class JobRecommendationServiceTest {

    @Mock private JobPostingRepository postings;
    @Mock private SavedJobRepository saved;
    @Mock private ResumeRepository resumes;
    @Mock private ParsedProfileRepository profiles;
    @Mock private RecommendationRepository recommendations;
    @Mock private MlServiceClient ml;

    private JobRecommendationService service;
    private final User user = new User();
    private JobPosting backend;
    private JobPosting sales;

    @BeforeEach
    void setUp() {
        service = new JobRecommendationService(postings, saved, resumes, profiles, recommendations, ml);
        backend = job("Backend Engineer", "Groww", "hybrid", List.of("Java", "Kafka"));
        sales = job("Account Executive", "CRED", "onsite", null);
        lenient().when(postings.findAllByActiveTrueOrderByFirstSeenAtDesc(any())).thenReturn(List.of(sales, backend));
        lenient().when(saved.findByUserOrderBySavedAtDesc(user)).thenReturn(List.of());
    }

    private static JobPosting job(String title, String company, String workplace, List<String> skills) {
        Company c = new Company();
        c.setName(company);
        c.setDomain(company.toLowerCase() + ".com");
        JobPosting posting = new JobPosting();
        posting.setId(UUID.randomUUID());
        posting.setCompany(c);
        posting.setTitle(title);
        posting.setWorkplaceType(workplace);
        posting.setUrl("https://example.com/" + title);
        posting.setSkills(skills);
        posting.setFirstSeenAt(Instant.parse("2026-10-21T00:00:00Z"));
        return posting;
    }

    @Test
    void ranksForTheLatestResume_withItsSkillsAndTopRoles_andKeepsTheMlOrder() {
        Resume resume = new Resume();
        resume.setId(UUID.randomUUID());
        resume.setVersion(2);
        ParsedProfile profile = new ParsedProfile();
        profile.setSkills(List.of("Java", "SQL"));
        Role role = new Role();
        role.setTitle("Backend Software Engineer");
        Recommendation match = new Recommendation();
        match.setRole(role);
        when(resumes.findTopByUserOrderByVersionDesc(user)).thenReturn(Optional.of(resume));
        when(profiles.findByResume(resume)).thenReturn(Optional.of(profile));
        when(recommendations.findByResumeOrderByMatchScoreDesc(resume)).thenReturn(List.of(match));
        when(ml.rankJobs(any())).thenReturn(new RankJobsDto.Response(List.of(
                new RankJobsDto.RankedJob(backend.getId().toString(), 0.71, 0.5, 0.8, 0.9, List.of("Java"), List.of("Kafka"),
                        "Backend Software Engineer", "You have 1 of the 2 skills this job asks for (50%): Java."),
                new RankJobsDto.RankedJob(sales.getId().toString(), 0.05, 0, 0, 0.1, List.of(), List.of(), null, "…"))));

        RecommendedJobsResponse response = service.recommend(user, null, null, 10);

        ArgumentCaptor<RankJobsDto.Request> sent = ArgumentCaptor.forClass(RankJobsDto.Request.class);
        verify(ml).rankJobs(sent.capture());
        assertThat(sent.getValue().skills()).containsExactly("Java", "SQL");
        assertThat(sent.getValue().roles()).containsExactly("Backend Software Engineer");
        assertThat(sent.getValue().jobs()).extracting(RankJobsDto.Job::skills)
                .containsExactly(List.of(), List.of("Java", "Kafka")); // unread skills go as an empty list
        assertThat(response.resumeVersion()).isEqualTo(2);
        assertThat(response.jobs()).extracting(j -> j.job().title()).containsExactly("Backend Engineer", "Account Executive");
        assertThat(response.jobs().get(0).missingSkills()).containsExactly("Kafka");
    }

    @Test
    void withoutAResume_listsNewestJobsAndAsksForOne_withoutCallingTheMlService() {
        when(resumes.findTopByUserOrderByVersionDesc(user)).thenReturn(Optional.empty());

        RecommendedJobsResponse response = service.recommend(user, null, null, 10);

        assertThat(response.resumeId()).isNull();
        assertThat(response.jobs()).hasSize(2);
        assertThat(response.jobs().get(0).why()).startsWith("Upload a resume");
        verify(ml, never()).rankJobs(any());
    }

    @Test
    void filters_matchEveryWordAndTheWorkplace() {
        assertThat(JobRecommendationService.matchesFilters(backend, "backend groww", null)).isTrue();
        assertThat(JobRecommendationService.matchesFilters(backend, "backend cred", null)).isFalse();
        assertThat(JobRecommendationService.matchesFilters(backend, null, "HYBRID")).isTrue();
        assertThat(JobRecommendationService.matchesFilters(backend, "", "remote")).isFalse();
        assertThat(JobRecommendationService.matchesFilters(backend, "eng", null)).isTrue();
    }

    @Test
    void search_matchesWholeWords_notPartsOfACompanyName() {
        JobPosting acceldata = job("Staff Engineer (Full Stack)", "Acceldata", "", List.of());
        assertThat(JobRecommendationService.matchesFilters(acceldata, "data engineer", null)).isFalse();
        assertThat(JobRecommendationService.matchesFilters(acceldata, "acceldata", null)).isTrue();
        JobPosting cpp = job("C++ Developer", "Zoho", "", List.of());
        assertThat(JobRecommendationService.matchesFilters(cpp, "c++", null)).isTrue();
    }
}
