package com.resumeanalyser.job.feed;

import com.fasterxml.jackson.databind.JsonNode;
import com.resumeanalyser.job.AtsProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;
import java.net.URI;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/** Lever's public postings API: {@code GET api.lever.co/v0/postings/{slug}?mode=json}. */
@Component
public class LeverFeed implements JobFeed {

    private final RestClient client;

    public LeverFeed(@Qualifier("jobFeedRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public AtsProvider provider() {
        return AtsProvider.LEVER;
    }

    @Override
    public Optional<List<FeedPosting>> fetch(String slug) {
        URI uri = UriComponentsBuilder.fromHttpUrl("https://api.lever.co/v0/postings/{slug}")
                .queryParam("mode", "json")
                .buildAndExpand(slug).encode().toUri();
        return FeedReader.getJson(client, uri).map(LeverFeed::parse);
    }

    static List<FeedPosting> parse(JsonNode root) {
        List<FeedPosting> postings = new ArrayList<>();
        if (!root.isArray()) {
            return postings;
        }
        for (JsonNode job : root) {
            JsonNode categories = job.path("categories");
            Set<String> locations = new LinkedHashSet<>();
            categories.path("allLocations").forEach(location -> locations.add(location.asText().trim()));
            String primary = FeedReader.text(categories, "location");
            if (!primary.isEmpty()) {
                locations.add(primary);
            }
            String department = FeedReader.text(categories, "department");
            if (department.isEmpty()) {
                department = FeedReader.text(categories, "team");
            }
            String workplace = FeedReader.lower(FeedReader.text(job, "workplaceType"));
            long createdAt = job.path("createdAt").asLong(0);
            postings.add(new FeedPosting(
                    FeedReader.text(job, "id"),
                    FeedReader.text(job, "text"),
                    List.copyOf(locations),
                    "unspecified".equals(workplace) ? "" : workplace,
                    FeedReader.lower(FeedReader.text(categories, "commitment")),
                    department,
                    FeedReader.text(job, "hostedUrl"),
                    FeedReader.text(job, "applyUrl"),
                    description(job),
                    createdAt > 0 ? Instant.ofEpochMilli(createdAt) : null));
        }
        return postings;
    }

    /** The opening text, then each list ("What you'll do", "Requirements"...), then the closing text. */
    private static String description(JsonNode job) {
        StringBuilder text = new StringBuilder(FeedReader.text(job, "descriptionPlain"));
        for (JsonNode list : job.path("lists")) {
            text.append("\n\n").append(FeedReader.text(list, "text")).append('\n')
                    .append(FeedReader.plainText(FeedReader.text(list, "content")));
        }
        String closing = FeedReader.text(job, "additionalPlain");
        if (!closing.isEmpty()) {
            text.append("\n\n").append(closing);
        }
        return text.toString().trim();
    }
}
