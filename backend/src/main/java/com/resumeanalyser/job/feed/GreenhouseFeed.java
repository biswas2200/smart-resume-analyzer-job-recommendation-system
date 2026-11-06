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

/** Greenhouse's Job Board API: {@code GET boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true}. */
@Component
public class GreenhouseFeed implements JobFeed {

    private final RestClient client;

    public GreenhouseFeed(@Qualifier("jobFeedRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public AtsProvider provider() {
        return AtsProvider.GREENHOUSE;
    }

    @Override
    public Optional<List<FeedPosting>> fetch(String slug) {
        URI uri = UriComponentsBuilder.fromHttpUrl("https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
                .queryParam("content", "true")
                .buildAndExpand(slug).encode().toUri();
        return FeedReader.getJson(client, uri).map(GreenhouseFeed::parse);
    }

    static List<FeedPosting> parse(JsonNode root) {
        List<FeedPosting> postings = new ArrayList<>();
        for (JsonNode job : root.path("jobs")) {
            Set<String> locations = new LinkedHashSet<>();
            String primary = FeedReader.text(job.path("location"), "name");
            if (!primary.isEmpty()) {
                locations.add(primary);
            }
            for (JsonNode office : job.path("offices")) {
                String officeLocation = FeedReader.text(office, "location");
                locations.add(officeLocation.isEmpty() ? FeedReader.text(office, "name") : officeLocation);
            }
            locations.remove("");
            String published = FeedReader.text(job, "first_published");
            postings.add(new FeedPosting(
                    FeedReader.text(job, "id"),
                    FeedReader.text(job, "title"),
                    List.copyOf(locations),
                    "",
                    "",
                    FeedReader.text(job.path("departments").path(0), "name"),
                    FeedReader.text(job, "absolute_url"),
                    "",
                    FeedReader.plainText(FeedReader.text(job, "content")),
                    FeedReader.instant(published.isEmpty() ? FeedReader.text(job, "updated_at") : published)));
        }
        return postings;
    }
}
