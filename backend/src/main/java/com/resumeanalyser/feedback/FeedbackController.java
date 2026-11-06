package com.resumeanalyser.feedback;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.feedback.dto.FeedbackDto;
import com.resumeanalyser.feedback.dto.FeedbackRequest;
import com.resumeanalyser.feedback.mapper.FeedbackMapper;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

/** Records and looks up helpful/not-helpful feedback on a recommendation (FR-10.1). */
@RestController
@RequestMapping("/feedback")
public class FeedbackController {

    private final FeedbackService feedbackService;
    private final UserRepository userRepository;
    private final FeedbackMapper feedbackMapper;

    public FeedbackController(FeedbackService feedbackService, UserRepository userRepository, FeedbackMapper feedbackMapper) {
        this.feedbackService = feedbackService;
        this.userRepository = userRepository;
        this.feedbackMapper = feedbackMapper;
    }

    /** Records the signed-in user's verdict on one of their own recommendations. */
    @PostMapping
    public ResponseEntity<FeedbackDto> submit(@Valid @RequestBody FeedbackRequest request, Authentication authentication) {
        Feedback feedback = feedbackService.submit(currentUser(authentication), request.recommendationId(), request.helpful());
        return ResponseEntity.status(HttpStatus.CREATED).body(feedbackMapper.toDto(feedback));
    }

    /** The most recent feedback given for a recommendation, or 204 No Content if none yet. */
    @GetMapping("/{recommendationId}")
    public ResponseEntity<FeedbackDto> getFeedbackFor(@PathVariable UUID recommendationId, Authentication authentication) {
        return feedbackService.getLatestFeedback(currentUser(authentication), recommendationId)
                .map(feedback -> ResponseEntity.ok(feedbackMapper.toDto(feedback)))
                .orElseGet(() -> ResponseEntity.noContent().build());
    }

    private User currentUser(Authentication authentication) {
        return userRepository.findByEmail(authentication.getName())
                .orElseThrow(() -> new ResourceNotFoundException("No user with email " + authentication.getName()));
    }
}
