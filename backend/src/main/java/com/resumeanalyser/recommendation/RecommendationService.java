package com.resumeanalyser.recommendation;

import com.resumeanalyser.account.User;
import com.resumeanalyser.client.dto.RoleMatchDto;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.recommendation.dto.DashboardResponse;
import com.resumeanalyser.resume.ParsedProfile;
import com.resumeanalyser.resume.ParsedProfileRepository;
import com.resumeanalyser.resume.Resume;
import com.resumeanalyser.resume.ResumeRepository;
import com.resumeanalyser.skillvector.SkillVectorService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * Owns everything role-recommendation related: turning one resume analysis
 * run's ML role matches into persisted {@link Recommendation} rows (per
 * docs/lld.md §7: "persists Recommendation rows"), and assembling the
 * dashboard's composite read view from what's already been persisted.
 */
@Service
public class RecommendationService {

    private final RoleRepository roleRepository;
    private final RecommendationRepository recommendationRepository;
    private final ResumeRepository resumeRepository;
    private final ParsedProfileRepository parsedProfileRepository;
    private final SkillVectorService skillVectorService;

    public RecommendationService(
            RoleRepository roleRepository,
            RecommendationRepository recommendationRepository,
            ResumeRepository resumeRepository,
            ParsedProfileRepository parsedProfileRepository,
            SkillVectorService skillVectorService
    ) {
        this.roleRepository = roleRepository;
        this.recommendationRepository = recommendationRepository;
        this.resumeRepository = resumeRepository;
        this.parsedProfileRepository = parsedProfileRepository;
        this.skillVectorService = skillVectorService;
    }

    /**
     * Persists one {@link Recommendation} row per role match from a resume's
     * analysis run (called by {@code ResumeService} right after it persists the
     * resume itself, reusing the same ML response rather than calling the ML
     * service a second time). Roles are upserted by title -- the first time a
     * given role is matched anywhere, a new {@link Role} row is created for it;
     * every match after that reuses the existing row. Every matched/missing
     * skill also gets a {@code SkillVector} row initialized (FR-7.1) if it
     * doesn't have one yet, so the role's skills are visible at the default
     * weight even before any feedback exists for them.
     *
     * @param user    the account this analysis was run for
     * @param resume  the resume version that was analyzed
     * @param matches the ML service's ranked role matches for this analysis run
     */
    public void persistFromAnalysis(User user, Resume resume, List<RoleMatchDto> matches) {
        for (RoleMatchDto match : matches) {
            Role role = roleRepository.findByTitle(match.role())
                    .orElseGet(() -> {
                        Role newRole = new Role();
                        newRole.setTitle(match.role());
                        newRole.setDomain(domainOf(match));
                        newRole.setDescription(match.description() == null ? "" : match.description());
                        return roleRepository.save(newRole);
                    });
            if (role.getDescription().isBlank() && match.description() != null && !match.description().isBlank()) {
                // Roles created before the catalogue carried descriptions get
                // one the next time they are matched.
                role.setDescription(match.description());
                roleRepository.save(role);
            }

            Recommendation recommendation = new Recommendation();
            recommendation.setUser(user);
            recommendation.setRole(role);
            recommendation.setResume(resume);
            recommendation.setMatchScore(match.score());
            recommendation.setMatchedSkills(match.matchedSkills());
            recommendation.setMissingSkills(match.missingSkills());
            recommendationRepository.save(recommendation);

            Set<String> allSkills = new LinkedHashSet<>(match.matchedSkills());
            allSkills.addAll(match.missingSkills());
            skillVectorService.ensureInitialized(role, allSkills);
        }
    }

    /**
     * Replaces one resume version's recommendations with a fresh analysis run's
     * (see {@code ResumeService#reanalyze}): the old rows -- and, through the
     * schema's cascade, any feedback on them -- are removed first, so the
     * dashboard never shows two generations of matches for the same resume.
     */
    @Transactional
    public void replaceForResume(User user, Resume resume, List<RoleMatchDto> matches) {
        recommendationRepository.deleteByResume(resume);
        persistFromAnalysis(user, resume, matches);
    }

    private static String domainOf(RoleMatchDto match) {
        return match.domain() == null || match.domain().isBlank() ? "engineering" : match.domain();
    }

    /**
     * Assembles the dashboard view for a user's most recently uploaded resume.
     *
     * @param user the signed-in account
     * @return the dashboard data, or empty if the user hasn't uploaded a resume yet
     */
    // Read-only transaction so the lazy Recommendation -> Role association can
    // be walked while assembling the view; open-in-view is off, so without it
    // r.getRole().getTitle() throws LazyInitializationException.
    @Transactional(readOnly = true)
    public Optional<DashboardResponse> getDashboard(User user) {
        Optional<Resume> latestResume = resumeRepository.findTopByUserOrderByVersionDesc(user);
        if (latestResume.isEmpty()) {
            return Optional.empty();
        }

        Resume resume = latestResume.get();
        ParsedProfile profile = parsedProfileRepository.findByResume(resume)
                .orElseThrow(() -> new ResourceNotFoundException("No parsed profile for resume: " + resume.getId()));

        List<Recommendation> recommendations = recommendationRepository.findByResumeOrderByMatchScoreDesc(resume);

        DashboardResponse.AtsScore atsScore = new DashboardResponse.AtsScore(
                profile.getAtsScore(),
                profile.getAtsMaxScore(),
                profile.getAtsChecks().stream()
                        .map(c -> new DashboardResponse.AtsCheck(c.name(), c.passed(), c.detail()))
                        .toList());

        List<DashboardResponse.RoleRecommendation> roleRecommendations = recommendations.stream()
                .map(r -> new DashboardResponse.RoleRecommendation(
                        r.getId(),
                        new DashboardResponse.RoleSummary(
                                r.getRole().getId(), r.getRole().getTitle(), r.getRole().getDescription(),
                                r.getRole().getDomain()),
                        r.getMatchScore(),
                        r.getCreatedAt(),
                        r.getMatchedSkills(),
                        r.getMissingSkills()))
                .toList();

        DashboardResponse.DomainInfo domain = new DashboardResponse.DomainInfo(
                profile.getDomain(),
                profile.getDomainName(),
                profile.getDomainConfidence(),
                profile.getDomainEngine());

        return Optional.of(new DashboardResponse(
                resume.getId(),
                domain,
                atsScore,
                roleRecommendations,
                profile.isRecommendationsLocked(),
                profile.getLockReason(),
                profile.getExplanation(),
                profile.getExplanationSource()));
    }
}
