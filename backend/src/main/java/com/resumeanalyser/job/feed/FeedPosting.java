package com.resumeanalyser.job.feed;

import java.time.Instant;
import java.util.List;

/**
 * One job as read from a hiring tool's feed, in the same shape for every tool.
 *
 * @param externalId     the posting's id inside the tool
 * @param locations      every location the posting names (a job can list several)
 * @param workplaceType  "onsite" / "hybrid" / "remote", lower case; empty if unknown
 * @param url            the original posting
 * @param applyUrl       the application form, or empty if it is the posting itself
 * @param description    plain text
 * @param publishedAt    when the company published it, or null if the feed doesn't say
 */
public record FeedPosting(
        String externalId,
        String title,
        List<String> locations,
        String workplaceType,
        String employmentType,
        String department,
        String url,
        String applyUrl,
        String description,
        Instant publishedAt
) {}
