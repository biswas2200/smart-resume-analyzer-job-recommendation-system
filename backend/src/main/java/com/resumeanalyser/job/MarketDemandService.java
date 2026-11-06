package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.client.MlServiceClient;
import com.resumeanalyser.client.MlServiceException;
import com.resumeanalyser.client.dto.MarketDemandDto;
import com.resumeanalyser.client.dto.RankJobsDto;
import com.resumeanalyser.job.dto.InDemandDto;
import com.resumeanalyser.recommendation.Recommendation;
import com.resumeanalyser.recommendation.RecommendationRepository;
import com.resumeanalyser.resume.ParsedProfile;
import com.resumeanalyser.resume.ParsedProfileRepository;
import com.resumeanalyser.resume.Resume;
import com.resumeanalyser.resume.ResumeRepository;
import com.resumeanalyser.skillvector.SkillVectorSnapshotService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;

/**
 * The job-market signal for the EMA skill weights (SRS FR-7, "job-market
 * data", planned since v2.0): once a day, after the jobs refresh, the ML
 * service groups open jobs by catalogue role and measures how often each
 * skill is asked for; that becomes each role's EMA signal, and the updated
 * weights are pushed to the ML service, so role matches lean towards what
 * Bengaluru employers ask for. Users see the same numbers as "in demand".
 */
@Service
public class MarketDemandService {

    private static final Logger log = LoggerFactory.getLogger(MarketDemandService.class);
    static final int MAX_JOBS = 20_000;
    static final int ROLES_SHOWN = 3;
    static final int SKILLS_SHOWN = 10;

    private final JobPostingRepository postings;
    private final MarketDemandStore store;
    private final MarketSkillDemandRepository demand;
    private final SkillVectorSnapshotService snapshots;
    private final MlServiceClient mlServiceClient;
    private final ResumeRepository resumes;
    private final ParsedProfileRepository profiles;
    private final RecommendationRepository recommendations;
    private final Clock clock;

    public MarketDemandService(JobPostingRepository postings, MarketDemandStore store,
                               MarketSkillDemandRepository demand, SkillVectorSnapshotService snapshots,
                               MlServiceClient mlServiceClient, ResumeRepository resumes,
                               ParsedProfileRepository profiles, RecommendationRepository recommendations, Clock clock) {
        this.postings = postings;
        this.store = store;
        this.demand = demand;
        this.snapshots = snapshots;
        this.mlServiceClient = mlServiceClient;
        this.resumes = resumes;
        this.profiles = profiles;
        this.recommendations = recommendations;
        this.clock = clock;
    }

    /** Measures demand, updates the EMA weights and installs them in the ML service. */
    public String update() {
        List<RankJobsDto.Job> jobs = postings.findAllByActiveTrueOrderByFirstSeenAtDesc(PageRequest.of(0, MAX_JOBS))
                .stream()
                .filter(job -> job.getSkills() != null)
                .map(job -> new RankJobsDto.Job(job.getId().toString(), job.getTitle(), job.getSkills()))
                .toList();
        try {
            MarketDemandDto.Response result = mlServiceClient.marketDemand(jobs);
            if (result == null || result.roles() == null) {
                return "market demand: no answer from the ML service";
            }
            int updated = store.store(result, clock.instant());
            mlServiceClient.pushWeights(snapshots.exportSnapshot());
            String summary = "market demand from %d jobs: %d roles measured (%d jobs matched no role), %d skill weights updated and installed"
                    .formatted(jobs.size(), result.roles().size(), result.unassignedJobs(), updated);
            log.info("Market demand: {}", summary);
            return summary;
        } catch (MlServiceException e) {
            log.warn("Market demand update failed: {}", e.getMessage());
            return "market demand not updated: " + e.getMessage();
        }
    }

    /** What open jobs ask for in the user's top role matches, marking the skills they have. */
    @Transactional(readOnly = true)
    public InDemandDto forUser(User user) {
        Optional<Resume> latest = resumes.findTopByUserOrderByVersionDesc(user);
        if (latest.isEmpty()) {
            return new InDemandDto(List.of());
        }
        Set<String> have = new HashSet<>();
        profiles.findByResume(latest.get()).map(ParsedProfile::getSkills)
                .ifPresent(skills -> skills.forEach(skill -> have.add(key(skill))));
        List<Recommendation> top = recommendations.findByResumeOrderByMatchScoreDesc(latest.get()).stream()
                .limit(ROLES_SHOWN).toList();
        top.forEach(match -> match.getMatchedSkills().forEach(skill -> have.add(key(skill))));

        List<InDemandDto.RoleDemand> roles = top.stream().map(match -> {
            String title = match.getRole().getTitle();
            List<MarketSkillDemand> rows = demand.findByRoleTitleOrderByShareDescSkillAsc(title);
            if (rows.isEmpty()) {
                return new InDemandDto.RoleDemand(title, 0, null, List.of());
            }
            List<InDemandDto.SkillDemand> skills = rows.stream().limit(SKILLS_SHOWN)
                    .map(row -> new InDemandDto.SkillDemand(row.getSkill(), row.getShare(), have.contains(key(row.getSkill()))))
                    .toList();
            return new InDemandDto.RoleDemand(title, rows.get(0).getJobCount(), rows.get(0).getComputedAt(), skills);
        }).toList();
        return new InDemandDto(roles);
    }

    private static String key(String skill) {
        return skill.trim().toLowerCase(Locale.ROOT);
    }
}
