package com.resumeanalyser.job.feed;

import com.resumeanalyser.job.AtsProvider;
import java.util.List;
import java.util.Optional;

/**
 * A hiring tool's public job feed. Implementations read only the feed the
 * tool publishes for job boards and career sites -- never scraped pages.
 */
public interface JobFeed {

    AtsProvider provider();

    /**
     * Every open posting on the company's board.
     *
     * @param slug the company's board name inside the tool, e.g. {@code "cred"}
     * @return empty if the tool has no board under that name
     * @throws JobFeedException if the feed could not be read (network error, 5xx, bad JSON)
     */
    Optional<List<FeedPosting>> fetch(String slug);
}
