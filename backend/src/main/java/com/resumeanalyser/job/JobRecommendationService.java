package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.client.MlServiceClient;
import com.resumeanalyser.client.dto.RankJobsDto;
import com.resumeanalyser.job.dto.JobPostingDto;
import com.resumeanalyser.job.dto.RecommendedJobDto;
import com.resumeanalyser.job.dto.RecommendedJobsResponse;
import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.recommendation.RecommendationRepository;
import com.resumeanalyser.resume.ParsedProfile;
import com.resumeanalyser.resume.ParsedProfileRepository;
import com.resumeanalyser.resume.Resume;
import com.resumeanalyser.resume.ResumeRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Open jobs ranked for a user's latest resume: its extracted skills and its
 * best-matched catalogue roles go to the ML service's {@code /rank-jobs}
 * together with every open job's stored skills, and come back best first,
 * each with its reasons. Without a resume, jobs are listed newest first.
 */
@Service
public class JobRecommendationService {

    /** Ranking candidates, newest first; far above today's few hundred open jobs. */
    static final int MAX_CANDIDATES = 5_000;
    /** How many of the user's top role matches steer the ranking. */
    static final int ROLES_USED = 3;
    static final int MAX_RESULTS = 100;
    private static final Pattern WORD_BREAK = Pattern.compile("[^\\p{L}\\p{N}+#]+");

    private final JobPostingRepository postings;
    private final SavedJobRepository saved;
    private final ResumeRepository resumes;
    private final ParsedProfileRepository profiles;
    private final RecommendationRepository recommendations;
    private final MlServiceClient mlServiceClient;

    public JobRecommendationService(JobPostingRepository postings, SavedJobRepository saved, ResumeRepository resumes,
                                    ParsedProfileRepository profiles, RecommendationRepository recommendations,
                                    MlServiceClient mlServiceClient) {
        this.postings = postings;
        this.saved = saved;
        this.resumes = resumes;
        this.profiles = profiles;
        this.recommendations = recommendations;
        this.mlServiceClient = mlServiceClient;
    }

    /**
     * @param query     optional words; each must start a word of the title or company name
     * @param workplace optional "onsite", "hybrid" or "remote"
     * @param limit     at most this many jobs (capped at {@value #MAX_RESULTS})
     * @throws com.resumeanalyser.client.MlServiceException if the ML service can't rank right now
     */
    @Transactional(readOnly = true)
    public RecommendedJobsResponse recommend(User user, String query, String workplace, int limit) {
        List<JobPosting> open = postings.findAllByActiveTrueOrderByFirstSeenAtDesc(PageRequest.of(0, MAX_CANDIDATES));
        List<JobPosting> candidates = open.stream().filter(job -> matchesFilters(job, query, workplace)).toList();
        int size = Math.min(Math.max(limit, 1), MAX_RESULTS);

        Map<UUID, SavedJobStatus> savedStatus = new HashMap<>();
        saved.findByUserOrderBySavedAtDesc(user)
                .forEach(entry -> savedStatus.put(entry.getJobPosting().getId(), entry.getStatus()));

        Optional<Resume> latest = resumes.findTopByUserOrderByVersionDesc(user);
        Optional<ParsedProfile> profile = latest.flatMap(profiles::findByResume);
        if (latest.isEmpty() || profile.isEmpty()) {
            List<RecommendedJobDto> newest = candidates.stream().limit(size)
                    .map(job -> new RecommendedJobDto(JobPostingDto.of(job), 0, 0, List.of(), List.of(), null,
                            "Upload a resume to see how well this job fits you.", savedStatus.get(job.getId())))
                    .toList();
            return new RecommendedJobsResponse(null, null, List.of(), open.size(), newest);
        }

        Resume resume = latest.get();
        List<String> roles = recommendations.findByResumeOrderByMatchScoreDesc(resume).stream()
                .limit(ROLES_USED)
                .map(Recommendation::getRole)
                .map(com.resumeanalyser.recommendation.Role::getTitle)
                .toList();
        if (candidates.isEmpty()) {
            return new RecommendedJobsResponse(resume.getId(), resume.getVersion(), roles, open.size(), List.of());
        }

        Map<String, JobPosting> byId = new HashMap<>();
        List<RankJobsDto.Job> jobs = candidates.stream().map(job -> {
            byId.put(job.getId().toString(), job);
            return new RankJobsDto.Job(job.getId().toString(), job.getTitle(),
                    job.getSkills() == null ? List.of() : job.getSkills());
        }).toList();
        RankJobsDto.Response ranked = mlServiceClient.rankJobs(
                new RankJobsDto.Request(profile.get().getSkills(), roles, jobs, size));

        List<RecommendedJobDto> results = ranked == null || ranked.jobs() == null ? List.of()
                : ranked.jobs().stream()
                        .filter(match -> byId.containsKey(match.id()))
                        .map(match -> {
                            JobPosting job = byId.get(match.id());
                            return new RecommendedJobDto(JobPostingDto.of(job), match.score(), match.coverage(),
                                    match.matchedSkills(), match.missingSkills(), match.closestRole(),
                                    match.explanation(), savedStatus.get(job.getId()));
                        })
                        .toList();
        return new RecommendedJobsResponse(resume.getId(), resume.getVersion(), roles, open.size(), results);
    }

    static boolean matchesFilters(JobPosting job, String query, String workplace) {
        if (workplace != null && !workplace.isBlank() && !workplace.equalsIgnoreCase(job.getWorkplaceType())) {
            return false;
        }
        if (query == null || query.isBlank()) {
            return true;
        }
        // Whole words (or their start, so "eng" finds "Engineer"): "data" must not
        // match "Acceldata", which made every Acceldata job a "data engineer" hit.
        List<String> words = List.of(WORD_BREAK.split(
                (job.getTitle() + " " + job.getCompany().getName()).toLowerCase(Locale.ROOT)));
        for (String term : WORD_BREAK.split(query.toLowerCase(Locale.ROOT).trim())) {
            if (!term.isEmpty() && words.stream().noneMatch(word -> word.startsWith(term))) {
                return false;
            }
        }
        return true;
    }
}
