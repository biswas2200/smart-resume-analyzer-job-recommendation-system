package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.job.dto.AddCompanyRequest;
import com.resumeanalyser.job.dto.CompanyOptionDto;
import com.resumeanalyser.job.dto.WatchedCompanyDto;
import com.resumeanalyser.job.dto.WatchlistLimitsDto;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;
import java.util.UUID;

/** The signed-in user's company watchlist. */
@RestController
@RequestMapping("/watchlist")
public class WatchlistController {

    private final WatchlistService watchlistService;
    private final UserRepository userRepository;

    public WatchlistController(WatchlistService watchlistService, UserRepository userRepository) {
        this.watchlistService = watchlistService;
        this.userRepository = userRepository;
    }

    @GetMapping
    public List<WatchedCompanyDto> list(Authentication authentication) {
        return watchlistService.list(currentUser(authentication));
    }

    /** The cap and change rate every user has, and how many companies this user watches. */
    @GetMapping("/limits")
    public WatchlistLimitsDto limits(Authentication authentication) {
        return watchlistService.limits(currentUser(authentication));
    }

    /** Companies to add, by name; empty for a blank query. */
    @GetMapping("/companies")
    public List<CompanyOptionDto> search(@RequestParam(defaultValue = "") String q, Authentication authentication) {
        return watchlistService.search(currentUser(authentication), q);
    }

    /**
     * Watches a company that isn't in our list yet, by its website; we look for
     * its job tool straight away (a few seconds). An existing company with the
     * same website is reused.
     */
    @PostMapping("/companies")
    public ResponseEntity<WatchedCompanyDto> watchNew(@Valid @RequestBody AddCompanyRequest request,
                                                      Authentication authentication) {
        WatchedCompanyDto added = watchlistService.watchNew(currentUser(authentication),
                request.name(), request.website(), request.careersUrl());
        return ResponseEntity.status(HttpStatus.CREATED).body(added);
    }

    @PutMapping("/{companyId}")
    public WatchedCompanyDto watch(@PathVariable UUID companyId, Authentication authentication) {
        return watchlistService.watch(currentUser(authentication), companyId);
    }

    @DeleteMapping("/{companyId}")
    public ResponseEntity<Void> unwatch(@PathVariable UUID companyId, Authentication authentication) {
        watchlistService.unwatch(currentUser(authentication), companyId);
        return ResponseEntity.noContent().build();
    }

    private User currentUser(Authentication authentication) {
        return userRepository.findByEmail(authentication.getName())
                .orElseThrow(() -> new ResourceNotFoundException("No user with email " + authentication.getName()));
    }
}
