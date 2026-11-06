package com.resumeanalyser.job.feed;

import com.resumeanalyser.job.AtsProvider;
import org.springframework.stereotype.Component;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/** Every {@link JobFeed}, by hiring tool. */
@Component
public class JobFeeds {

    private final Map<AtsProvider, JobFeed> byProvider = new EnumMap<>(AtsProvider.class);

    public JobFeeds(List<JobFeed> feeds) {
        feeds.forEach(feed -> byProvider.put(feed.provider(), feed));
    }

    public JobFeed get(AtsProvider provider) {
        JobFeed feed = byProvider.get(provider);
        if (feed == null) {
            throw new IllegalStateException("No job feed for " + provider);
        }
        return feed;
    }

    /** In the order detection tries them. */
    public List<JobFeed> all() {
        return List.copyOf(byProvider.values());
    }
}
