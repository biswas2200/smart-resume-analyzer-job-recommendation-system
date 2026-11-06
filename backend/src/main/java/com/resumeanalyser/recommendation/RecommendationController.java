package com.resumeanalyser.recommendation;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.recommendation.dto.DashboardResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Read endpoints for the candidate's role recommendations. */
@RestController
@RequestMapping("/recommendations")
public class RecommendationController {

    private final RecommendationService recommendationService;
    private final UserRepository userRepository;

    public RecommendationController(RecommendationService recommendationService, UserRepository userRepository) {
        this.recommendationService = recommendationService;
        this.userRepository = userRepository;
    }

    /**
     * The dashboard view for the signed-in user's most recently uploaded resume.
     *
     * @param authentication the signed-in user, injected by Spring Security
     * @return 200 with the dashboard data, or 204 No Content if no resume has been uploaded yet
     */
    @GetMapping("/dashboard")
    public ResponseEntity<DashboardResponse> getDashboard(Authentication authentication) {
        User user = currentUser(authentication);
        return recommendationService.getDashboard(user)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.noContent().build());
    }

    private User currentUser(Authentication authentication) {
        return userRepository.findByEmail(authentication.getName())
                .orElseThrow(() -> new ResourceNotFoundException("No user with email " + authentication.getName()));
    }
}
