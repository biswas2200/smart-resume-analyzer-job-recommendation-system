package com.resumeanalyser.job.feed;

import com.fasterxml.jackson.databind.JsonNode;
import com.resumeanalyser.job.AtsProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;
import java.net.URI;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/** Ashby's public job posting API: {@code GET api.ashbyhq.com/posting-api/job-board/{slug}}. */
@Component
public class AshbyFeed implements JobFeed {

    private final RestClient client;

    public AshbyFeed(@Qualifier("jobFeedRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public AtsProvider provider() {
        return AtsProvider.ASHBY;
    }

    @Override
    public Optional<List<FeedPosting>> fetch(String slug) {
        URI uri = UriComponentsBuilder.fromHttpUrl("https://api.ashbyhq.com/posting-api/job-board/{slug}")
                .buildAndExpand(slug).encode().toUri();
        return FeedReader.getJson(client, uri).map(AshbyFeed::parse);
    }

    static List<FeedPosting> parse(JsonNode root) {
        List<FeedPosting> postings = new ArrayList<>();
        for (JsonNode job : root.path("jobs")) {
            if (job.has("isListed") && !job.path("isListed").asBoolean()) {
                continue;
            }
            Set<String> locations = new LinkedHashSet<>();
            locations.add(FeedReader.text(job, "location"));
            for (JsonNode secondary : job.path("secondaryLocations")) {
                locations.add(FeedReader.text(secondary, "location"));
            }
            locations.add(FeedReader.text(job.path("address").path("postalAddress"), "addressLocality"));
            locations.remove("");
            postings.add(new FeedPosting(
                    FeedReader.text(job, "id"),
                    FeedReader.text(job, "title"),
                    List.copyOf(locations),
                    workplace(FeedReader.text(job, "workplaceType"), job.path("isRemote").asBoolean(false)),
                    words(FeedReader.text(job, "employmentType")),
                    FeedReader.text(job, "department"),
                    FeedReader.text(job, "jobUrl"),
                    FeedReader.text(job, "applyUrl"),
                    FeedReader.text(job, "descriptionPlain"),
                    FeedReader.instant(FeedReader.text(job, "publishedAt"))));
        }
        return postings;
    }

    /** "OnSite" / "Hybrid" / "Remote" to the lower-case words the other feeds use. */
    private static String workplace(String value, boolean isRemote) {
        String lower = FeedReader.lower(value).replace("-", "").replace(" ", "");
        if (lower.isEmpty()) {
            return isRemote ? "remote" : "";
        }
        return lower;
    }

    /** "FullTime" -> "full time". */
    private static String words(String camel) {
        return FeedReader.lower(camel.replaceAll("([a-z])([A-Z])", "$1 $2"));
    }
}
