package com.resumeanalyser.job;

import com.resumeanalyser.job.feed.FeedPosting;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Stores one company's freshly read feed: keeps the postings in our city,
 * adds new ones, updates the rest, and closes those that left the feed.
 * One transaction per company, so one bad feed never undoes another.
 */
@Component
public class JobPostingWriter {

    /** Long descriptions are cut here; the UI links to the original anyway. */
    static final int MAX_DESCRIPTION = 20_000;

    private final JobPostingRepository postings;
    private final CompanyRepository companies;
    private final LocationMatcher locations;
    private final Clock clock;

    public JobPostingWriter(JobPostingRepository postings, CompanyRepository companies,
                            LocationMatcher locations, Clock clock) {
        this.postings = postings;
        this.companies = companies;
        this.locations = locations;
        this.clock = clock;
    }

    /** What one company's refresh changed. {@code inCity} is how many feed postings were in our city. */
    public record Applied(int inFeed, int inCity, int added, int closed) {}

    @Transactional
    public Applied apply(Company company, List<FeedPosting> feed) {
        Instant now = clock.instant();
        List<FeedPosting> inCity = feed.stream()
                .filter(posting -> !posting.externalId().isEmpty() && !posting.url().isEmpty())
                .filter(posting -> locations.matches(posting.locations()))
                .toList();
        Map<String, JobPosting> existing = postings.findByCompany(company).stream()
                .collect(Collectors.toMap(JobPosting::getExternalId, Function.identity(), (a, b) -> a));

        Set<String> seen = new HashSet<>();
        int added = 0;
        for (FeedPosting item : inCity) {
            if (!seen.add(item.externalId())) {
                continue;
            }
            JobPosting posting = existing.get(item.externalId());
            if (posting == null) {
                posting = new JobPosting();
                posting.setCompany(company);
                posting.setExternalId(item.externalId());
                posting.setFirstSeenAt(now);
                added++;
            }
            copy(item, posting);
            posting.setLastSeenAt(now);
            posting.setActive(true);
            postings.save(posting);
        }

        int closed = 0;
        for (JobPosting posting : existing.values()) {
            if (posting.isActive() && !seen.contains(posting.getExternalId())) {
                posting.setActive(false);
                postings.save(posting);
                closed++;
            }
        }

        company.setLastFetchedAt(now);
        company.setLastError(null);
        companies.save(company);
        return new Applied(feed.size(), inCity.size(), added, closed);
    }

    /** Closes every open posting of a company whose feed is gone. */
    @Transactional
    public int closeAll(Company company) {
        int closed = 0;
        for (JobPosting posting : postings.findByCompany(company)) {
            if (posting.isActive()) {
                posting.setActive(false);
                postings.save(posting);
                closed++;
            }
        }
        return closed;
    }

    private static void copy(FeedPosting item, JobPosting posting) {
        String description = cut(item.description(), MAX_DESCRIPTION);
        if (!description.equals(posting.getDescription()) || !cut(item.title(), 512).equals(posting.getTitle())) {
            posting.setSkills(null); // re-extracted by JobSkillService
        }
        posting.setTitle(cut(item.title(), 512));
        posting.setLocation(cut(String.join(" · ", item.locations()), 512));
        posting.setWorkplaceType(cut(item.workplaceType(), 32));
        posting.setEmploymentType(cut(item.employmentType(), 64));
        posting.setDepartment(cut(item.department(), 255));
        posting.setUrl(item.url());
        posting.setApplyUrl(item.applyUrl());
        posting.setDescription(description);
        posting.setPublishedAt(item.publishedAt());
    }

    private static String cut(String value, int max) {
        if (value == null) {
            return "";
        }
        return value.length() <= max ? value : value.substring(0, max);
    }
}
