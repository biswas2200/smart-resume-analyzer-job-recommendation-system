package com.resumeanalyser.job;

import com.resumeanalyser.job.feed.FeedPosting;
import com.resumeanalyser.job.feed.JobFeedException;
import com.resumeanalyser.job.feed.JobFeeds;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import java.time.Clock;
import java.util.List;
import java.util.Optional;

/**
 * Re-reads every ACTIVE company's job feed and stores its jobs in our city
 * ({@link JobPostingWriter}). Run daily by {@link JobsRunner}. A company
 * whose board has disappeared becomes UNSUPPORTED and its jobs are closed;
 * a feed that is merely down keeps its jobs and records the error.
 */
@Service
public class JobRefreshService {

    private static final Logger log = LoggerFactory.getLogger(JobRefreshService.class);

    private final CompanyRepository companies;
    private final JobFeeds feeds;
    private final JobPostingWriter writer;
    private final Throttle throttle;
    private final Clock clock;

    public JobRefreshService(CompanyRepository companies, JobFeeds feeds, JobPostingWriter writer,
                             Throttle throttle, Clock clock) {
        this.companies = companies;
        this.feeds = feeds;
        this.writer = writer;
        this.throttle = throttle;
        this.clock = clock;
    }

    public record Summary(int companies, int failed, int gone, int jobsInCity, int added, int closed) {
        @Override
        public String toString() {
            return "%d companies refreshed (%d failed, %d boards gone): %d open jobs in the city, %d new, %d closed"
                    .formatted(companies, failed, gone, jobsInCity, added, closed);
        }
    }

    public Summary refreshAll() {
        List<Company> active = companies.findByStatusOrderByNameAsc(CompanyStatus.ACTIVE);
        int failed = 0;
        int gone = 0;
        int inCity = 0;
        int added = 0;
        int closed = 0;
        for (Company company : active) {
            throttle.pause();
            try {
                Optional<List<FeedPosting>> feed = feeds.get(company.getAtsProvider()).fetch(company.getAtsSlug());
                if (feed.isEmpty()) {
                    closed += boardGone(company);
                    gone++;
                    continue;
                }
                JobPostingWriter.Applied applied = writer.apply(company, feed.get());
                inCity += applied.inCity();
                added += applied.added();
                closed += applied.closed();
            } catch (JobFeedException e) {
                failed++;
                company.setLastError(e.getMessage());
                companies.save(company);
                log.warn("Job feed for {} ({} {}) failed: {}", company.getName(), company.getAtsProvider(),
                        company.getAtsSlug(), e.getMessage());
            }
        }
        Summary summary = new Summary(active.size(), failed, gone, inCity, added, closed);
        log.info("Job refresh: {}", summary);
        return summary;
    }

    private int boardGone(Company company) {
        log.info("Job board for {} ({} {}) is gone; marking it unsupported", company.getName(),
                company.getAtsProvider(), company.getAtsSlug());
        company.setStatus(CompanyStatus.UNSUPPORTED);
        company.setLastCheckedAt(clock.instant());
        company.setLastError("The board " + company.getAtsSlug() + " no longer exists on " + company.getAtsProvider());
        companies.save(company);
        return writer.closeAll(company);
    }
}
