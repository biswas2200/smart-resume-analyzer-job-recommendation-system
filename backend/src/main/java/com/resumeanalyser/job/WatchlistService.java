package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.common.BadRequestException;
import com.resumeanalyser.common.LimitReachedException;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.common.TooManyRequestsException;
import com.resumeanalyser.job.dto.CompanyOptionDto;
import com.resumeanalyser.job.dto.WatchedCompanyDto;
import com.resumeanalyser.job.dto.WatchlistLimitsDto;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

/** The companies a user watches for new jobs, and finding companies to add. */
@Service
public class WatchlistService {

    /** A job counts as new for this long after we first see it. */
    static final Duration NEW_FOR = Duration.ofDays(7);

    private final WatchedCompanyRepository watched;
    private final CompanyRepository companies;
    private final JobPostingRepository postings;
    private final WatchlistProperties limits;
    private final WatchlistRateLimiter rateLimiter;
    private final CompanyService companyService;
    private final Clock clock;

    public WatchlistService(WatchedCompanyRepository watched, CompanyRepository companies,
                            JobPostingRepository postings, WatchlistProperties limits,
                            WatchlistRateLimiter rateLimiter, CompanyService companyService, Clock clock) {
        this.watched = watched;
        this.companies = companies;
        this.postings = postings;
        this.limits = limits;
        this.rateLimiter = rateLimiter;
        this.companyService = companyService;
        this.clock = clock;
    }

    /** The limits every user has, and how many companies this user watches now. */
    @Transactional(readOnly = true)
    public WatchlistLimitsDto limits(User user) {
        return new WatchlistLimitsDto(limits.maxCompanies(), watched.countByUser(user),
                limits.changesPerMinute(), limits.changesPerHour());
    }

    @Transactional(readOnly = true)
    public List<WatchedCompanyDto> list(User user) {
        Instant newSince = clock.instant().minus(NEW_FOR);
        return watched.findByUserOrderByAddedAtDesc(user).stream()
                .map(entry -> toDto(entry, newSince))
                .toList();
    }

    /**
     * Adds a company to the watchlist; adding it again changes nothing. Every
     * call counts towards the change rate limit, even a repeat.
     *
     * @throws TooManyRequestsException  if the user is changing the watchlist too quickly
     * @throws ResourceNotFoundException if there is no such company
     * @throws LimitReachedException     if the user already watches the most companies allowed
     */
    @Transactional
    public WatchedCompanyDto watch(User user, UUID companyId) {
        rateLimiter.recordChange(user.getId());
        Company company = companies.findById(companyId)
                .orElseThrow(() -> new ResourceNotFoundException("No company with id " + companyId));
        return toDto(entryFor(user, company), clock.instant().minus(NEW_FOR));
    }

    /**
     * Watches a company that may not be in our list yet, found by its website:
     * an existing company with that domain is reused, otherwise it is added
     * (source USER) and its job tool looked for straight away -- Lever,
     * Greenhouse or Ashby, from {@code careersUrl} if given, else from the
     * domain and name. Counts as one watchlist change, and the cap is checked
     * before any job-board call, so a full or too-busy watchlist costs no
     * outside requests. Not transactional: detection makes network calls
     * that can take a few seconds.
     *
     * @throws TooManyRequestsException if the user is changing the watchlist too quickly
     * @throws BadRequestException      if {@code website} isn't a web address
     * @throws LimitReachedException    if the user already watches the most companies allowed
     */
    public WatchedCompanyDto watchNew(User user, String name, String website, String careersUrl) {
        rateLimiter.recordChange(user.getId());
        String domain = Domains.normalize(website);
        if (domain == null) {
            throw new BadRequestException("That doesn't look like a website address, e.g. acme.com");
        }
        boolean alreadyWatched = companies.findByDomain(domain)
                .flatMap(company -> watched.findByUserAndCompany(user, company))
                .isPresent();
        if (!alreadyWatched) {
            requireRoom(user);
        }
        Company company = companyService.add(name, website, careersUrl, CompanySource.USER);
        return toDto(entryFor(user, company), clock.instant().minus(NEW_FOR));
    }

    /** The user's entry for this company, added if missing (the one place entries are created). */
    private WatchedCompany entryFor(User user, Company company) {
        return watched.findByUserAndCompany(user, company).orElseGet(() -> {
            requireRoom(user);
            WatchedCompany created = new WatchedCompany();
            created.setUser(user);
            created.setCompany(company);
            created.setAddedAt(clock.instant());
            return watched.save(created);
        });
    }

    private void requireRoom(User user) {
        if (watched.countByUser(user) >= limits.maxCompanies()) {
            throw new LimitReachedException("You can watch up to " + limits.maxCompanies()
                    + " companies. Stop watching one to add another.");
        }
    }

    /**
     * Removes a company from the watchlist; nothing happens if it wasn't there.
     * Counts towards the change rate limit like {@link #watch}.
     *
     * @throws TooManyRequestsException if the user is changing the watchlist too quickly
     */
    @Transactional
    public void unwatch(User user, UUID companyId) {
        rateLimiter.recordChange(user.getId());
        companies.findById(companyId).flatMap(company -> watched.findByUserAndCompany(user, company))
                .ifPresent(watched::delete);
    }

    /** Up to 20 companies whose name contains {@code query}, by name, each marked if the user already watches it. */
    @Transactional(readOnly = true)
    public List<CompanyOptionDto> search(User user, String query) {
        String q = query == null ? "" : query.trim();
        if (q.isEmpty()) {
            return List.of();
        }
        Set<UUID> mine = watched.findByUserOrderByAddedAtDesc(user).stream()
                .map(entry -> entry.getCompany().getId())
                .collect(Collectors.toSet());
        return companies.findTop20ByNameContainingIgnoreCaseOrderByNameAsc(q).stream()
                .map(company -> CompanyOptionDto.of(company, mine.contains(company.getId())))
                .toList();
    }

    private WatchedCompanyDto toDto(WatchedCompany entry, Instant newSince) {
        Company company = entry.getCompany();
        return WatchedCompanyDto.of(company, postings.countByCompanyAndActiveTrue(company),
                postings.countByCompanyAndActiveTrueAndFirstSeenAtAfter(company, newSince), entry.getAddedAt());
    }
}
