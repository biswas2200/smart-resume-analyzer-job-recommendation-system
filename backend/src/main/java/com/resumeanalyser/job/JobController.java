package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.job.dto.InDemandDto;
import com.resumeanalyser.job.dto.JobPostingDto;
import com.resumeanalyser.job.dto.RecommendedJobsResponse;
import com.resumeanalyser.job.dto.SaveJobRequest;
import com.resumeanalyser.job.dto.SavedJobDto;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;
import java.util.UUID;

/**
 * Jobs for the signed-in user: open jobs in our city (plain or ranked for
 * their latest resume) and the jobs they saved.
 */
@RestController
@RequestMapping("/jobs")
public class JobController {

    static final int MAX_PAGE_SIZE = 100;

    private final JobPostingRepository postings;
    private final JobRecommendationService recommendationService;
    private final SavedJobService savedJobService;
    private final MarketDemandService marketDemandService;
    private final UserRepository userRepository;

    public JobController(JobPostingRepository postings, JobRecommendationService recommendationService,
                         SavedJobService savedJobService, MarketDemandService marketDemandService,
                         UserRepository userRepository) {
        this.marketDemandService = marketDemandService;
        this.postings = postings;
        this.recommendationService = recommendationService;
        this.savedJobService = savedJobService;
        this.userRepository = userRepository;
    }

    /** Open jobs, newest first, unranked. */
    @GetMapping
    public Page<JobPostingDto> list(@RequestParam(defaultValue = "0") int page,
                                    @RequestParam(defaultValue = "20") int size) {
        PageRequest request = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE));
        return postings.findByActiveTrueOrderByFirstSeenAtDesc(request).map(JobPostingDto::of);
    }

    /**
     * Open jobs ranked for the user's latest resume, best first, each with why
     * it matches. Filters apply before ranking.
     *
     * @param q         words to find in the title or company name
     * @param workplace "onsite", "hybrid" or "remote"
     */
    @GetMapping("/recommended")
    public RecommendedJobsResponse recommended(@RequestParam(required = false) String q,
                                               @RequestParam(required = false) String workplace,
                                               @RequestParam(defaultValue = "50") int limit,
                                               Authentication authentication) {
        return recommendationService.recommend(currentUser(authentication), q, workplace, limit);
    }

    /** What Bengaluru's open jobs ask for in the user's top role matches, marking the skills they have. */
    @GetMapping("/in-demand")
    public InDemandDto inDemand(Authentication authentication) {
        return marketDemandService.forUser(currentUser(authentication));
    }

    @GetMapping("/saved")
    public List<SavedJobDto> saved(Authentication authentication) {
        return savedJobService.list(currentUser(authentication));
    }

    /** Saves a job, or sets where its application stands (body optional). */
    @PutMapping("/{id}/saved")
    public SavedJobDto save(@PathVariable UUID id, @RequestBody(required = false) SaveJobRequest request,
                            Authentication authentication) {
        return savedJobService.save(currentUser(authentication), id, request == null ? null : request.status());
    }

    @DeleteMapping("/{id}/saved")
    public ResponseEntity<Void> unsave(@PathVariable UUID id, Authentication authentication) {
        savedJobService.remove(currentUser(authentication), id);
        return ResponseEntity.noContent().build();
    }

    private User currentUser(Authentication authentication) {
        return userRepository.findByEmail(authentication.getName())
                .orElseThrow(() -> new ResourceNotFoundException("No user with email " + authentication.getName()));
    }
}
