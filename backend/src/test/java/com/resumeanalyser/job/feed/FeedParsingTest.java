package com.resumeanalyser.job.feed;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The three feed readers turn each tool's JSON into the same {@link FeedPosting}.
 * Samples are trimmed copies of real responses (field names as the tools send them).
 */
class FeedParsingTest {

    private final ObjectMapper json = new ObjectMapper();

    private JsonNode read(String body) throws Exception {
        return json.readTree(body);
    }

    @Test
    void lever_readsLocationsCommitmentListsAndCreatedAt() throws Exception {
        List<FeedPosting> postings = LeverFeed.parse(read("""
                [{"id": "abc-1", "text": "Backend Engineer",
                  "categories": {"commitment": "Full Time", "department": "Engineering", "team": "Payments",
                                 "location": "bengaluru", "allLocations": ["bengaluru", "hyderabad"]},
                  "workplaceType": "hybrid",
                  "hostedUrl": "https://jobs.lever.co/cred/abc-1", "applyUrl": "https://jobs.lever.co/cred/abc-1/apply",
                  "descriptionPlain": "Build payments.",
                  "lists": [{"text": "Requirements", "content": "<li>Java</li><li>Kafka &amp; SQL</li>"}],
                  "additionalPlain": "We are an equal opportunity employer.",
                  "createdAt": 1790573982021}]
                """));

        assertThat(postings).hasSize(1);
        FeedPosting posting = postings.get(0);
        assertThat(posting.externalId()).isEqualTo("abc-1");
        assertThat(posting.locations()).containsExactly("bengaluru", "hyderabad");
        assertThat(posting.workplaceType()).isEqualTo("hybrid");
        assertThat(posting.employmentType()).isEqualTo("full time");
        assertThat(posting.department()).isEqualTo("Engineering");
        assertThat(posting.description()).contains("Build payments.", "Requirements", "Java", "Kafka & SQL", "equal opportunity");
        assertThat(posting.publishedAt()).isEqualTo(Instant.ofEpochMilli(1790573982021L));
    }

    @Test
    void lever_treatsUnspecifiedWorkplaceAsUnknown_andFallsBackToTeam() throws Exception {
        FeedPosting posting = LeverFeed.parse(read("""
                [{"id": "x", "text": "Analyst", "categories": {"team": "Finance", "location": "Bangalore"},
                  "workplaceType": "unspecified", "hostedUrl": "https://jobs.lever.co/a/x"}]
                """)).get(0);

        assertThat(posting.workplaceType()).isEmpty();
        assertThat(posting.department()).isEqualTo("Finance");
        assertThat(posting.locations()).containsExactly("Bangalore");
        assertThat(posting.publishedAt()).isNull();
    }

    @Test
    void greenhouse_readsLocationAndOffices_andUnescapesTheHtmlContent() throws Exception {
        List<FeedPosting> postings = GreenhouseFeed.parse(read("""
                {"jobs": [{"id": 4018, "title": "SDE II",
                  "location": {"name": "Bengaluru-VTP, India"},
                  "offices": [{"name": "Bengaluru-VTP", "location": "Bengaluru-VTP, India"}, {"name": "Pune", "location": ""}],
                  "departments": [{"name": "Engineering"}],
                  "absolute_url": "https://groww.in/careers/4018",
                  "content": "&lt;p&gt;Own the &lt;strong&gt;orders&lt;/strong&gt; service&amp;nbsp;end to end.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Go&lt;/li&gt;&lt;/ul&gt;",
                  "first_published": "2026-09-14T03:49:28-04:00", "updated_at": "2026-09-20T00:00:00-04:00"}]}
                """));

        FeedPosting posting = postings.get(0);
        assertThat(posting.externalId()).isEqualTo("4018");
        assertThat(posting.locations()).containsExactly("Bengaluru-VTP, India", "Pune");
        assertThat(posting.department()).isEqualTo("Engineering");
        assertThat(posting.description()).isEqualTo("Own the orders service end to end.\n\nGo");
        assertThat(posting.publishedAt()).isEqualTo(Instant.parse("2026-09-14T07:49:28Z"));
        assertThat(posting.applyUrl()).isEmpty();
    }

    @Test
    void ashby_skipsUnlistedJobs_andNormalisesWorkplaceAndEmploymentType() throws Exception {
        List<FeedPosting> postings = AshbyFeed.parse(read("""
                {"apiVersion": "1", "jobs": [
                  {"id": "j1", "title": "Data Engineer", "location": "Bengaluru",
                   "secondaryLocations": [{"location": "Remote - India"}],
                   "address": {"postalAddress": {"addressLocality": "Bengaluru"}},
                   "workplaceType": "OnSite", "isRemote": false, "employmentType": "FullTime",
                   "department": "Data", "jobUrl": "https://jobs.ashbyhq.com/acme/j1",
                   "applyUrl": "https://jobs.ashbyhq.com/acme/j1/application",
                   "descriptionPlain": "Pipelines.", "publishedAt": "2026-10-01T10:00:00.000+00:00", "isListed": true},
                  {"id": "j2", "title": "Hidden", "location": "Bengaluru", "jobUrl": "https://x", "isListed": false},
                  {"id": "j3", "title": "Support", "location": "Remote", "isRemote": true, "jobUrl": "https://y"}]}
                """));

        assertThat(postings).extracting(FeedPosting::externalId).containsExactly("j1", "j3");
        FeedPosting first = postings.get(0);
        assertThat(first.locations()).containsExactly("Bengaluru", "Remote - India");
        assertThat(first.workplaceType()).isEqualTo("onsite");
        assertThat(first.employmentType()).isEqualTo("full time");
        assertThat(first.publishedAt()).isEqualTo(Instant.parse("2026-10-01T10:00:00Z"));
        assertThat(postings.get(1).workplaceType()).isEqualTo("remote");
    }

    @Test
    void anUnexpectedShape_yieldsNoPostings_ratherThanAnError() throws Exception {
        assertThat(LeverFeed.parse(read("{\"ok\": false}"))).isEmpty();
        assertThat(GreenhouseFeed.parse(read("[]"))).isEmpty();
        assertThat(AshbyFeed.parse(read("{}"))).isEmpty();
    }
}
