package com.resumeanalyser.job;

import com.resumeanalyser.job.feed.FeedPosting;
import com.resumeanalyser.job.feed.JobFeed;
import com.resumeanalyser.job.feed.JobFeeds;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class AtsDetectorTest {

    /** A feed that knows only the boards it is given, and records every slug asked for. */
    private static final class FakeFeed implements JobFeed {
        private final AtsProvider provider;
        private final Map<String, List<FeedPosting>> boards;
        final List<String> asked = new ArrayList<>();

        FakeFeed(AtsProvider provider, Map<String, List<FeedPosting>> boards) {
            this.provider = provider;
            this.boards = boards;
        }

        @Override
        public AtsProvider provider() {
            return provider;
        }

        @Override
        public Optional<List<FeedPosting>> fetch(String slug) {
            asked.add(slug);
            return Optional.ofNullable(boards.get(slug));
        }
    }

    private static List<FeedPosting> jobsIn(String location) {
        return List.of(new FeedPosting("1", "Engineer", List.of(location), "", "", "", "https://x/1", "", "", null));
    }

    // "cred" on Lever has no open jobs at all; "better" is another company's board, jobs in the US only.
    private final FakeFeed lever = new FakeFeed(AtsProvider.LEVER, Map.of("cred", List.of(), "better", jobsIn("New York, NY")));
    private final FakeFeed greenhouse = new FakeFeed(AtsProvider.GREENHOUSE,
            Map.of("groww", jobsIn("Bengaluru-VTP"), "atherenergy", jobsIn("Pune, India")));
    private final FakeFeed ashby = new FakeFeed(AtsProvider.ASHBY, Map.of());
    private final JobsProperties properties =
            new JobsProperties("Bengaluru", List.of("bengaluru"), List.of("india"), "t", Duration.ZERO, Duration.ZERO, Duration.ofSeconds(1));
    private final AtsDetector detector = new AtsDetector(new JobFeeds(List.of(lever, greenhouse, ashby)),
            new Throttle(properties), new LocationMatcher(properties));

    @Test
    void aCareersLinkToATool_isReadDirectly() {
        var found = detector.detect("Cred", "cred.club", "https://jobs.lever.co/cred/abc-123");

        assertThat(found).get().extracting(AtsDetector.Detection::provider, AtsDetector.Detection::slug,
                AtsDetector.Detection::method).containsExactly(AtsProvider.LEVER, "cred", DetectionMethod.CAREERS_URL);
        assertThat(greenhouse.asked).isEmpty();
    }

    @Test
    void theWebsiteName_isTriedOnEveryTool_beforeTheCompanyName() {
        var found = detector.detect("Groww (Nextbillion Technology)", "groww.in", null);

        assertThat(found).get().extracting(AtsDetector.Detection::provider, AtsDetector.Detection::method)
                .containsExactly(AtsProvider.GREENHOUSE, DetectionMethod.DOMAIN_SLUG);
        assertThat(lever.asked).containsExactly("groww");
    }

    @Test
    void theCompanyName_isTheFallback_andIsMarkedAsWeakerEvidence() {
        var found = detector.detect("Ather Energy Pvt Ltd", "atherenergy.com", null);
        // "atherenergy" is also the website name here, so it is a DOMAIN_SLUG hit.
        assertThat(found).get().extracting(AtsDetector.Detection::method).isEqualTo(DetectionMethod.DOMAIN_SLUG);

        var byName = detector.detect("Ather Energy", "ather.in", null);
        assertThat(byName).get().extracting(AtsDetector.Detection::slug, AtsDetector.Detection::method)
                .containsExactly("atherenergy", DetectionMethod.NAME_SLUG);
    }

    @Test
    void aGuessedBoardWithNoJobInTheCountry_isAnotherCompanys_andIsRejected() {
        assertThat(detector.detect("The Better India", "thebetterindia.com", null)).isEmpty();
        assertThat(lever.asked).contains("better");
        // A guessed board with no open jobs can't be told apart either, so it waits for a retry.
        assertThat(detector.detect("Cred", "cred.club", null)).isEmpty();
    }

    @Test
    void aBoardNamedByTheCareersLink_needsNoJobInTheCountry() {
        assertThat(detector.detect("Better", "better.com", "https://jobs.lever.co/better")).isPresent();
    }

    @Test
    void noBoardAnywhere_isEmpty() {
        assertThat(detector.detect("Razorpay", "razorpay.com", null)).isEmpty();
        assertThat(ashby.asked).contains("razorpay");
    }

    @Test
    void boardFromUrl_knowsEachToolsLinkShapes() {
        assertThat(AtsDetector.boardFromUrl("https://boards.greenhouse.io/groww/jobs/1"))
                .contains(new AtsDetector.Board(AtsProvider.GREENHOUSE, "groww"));
        assertThat(AtsDetector.boardFromUrl("job-boards.greenhouse.io/acme"))
                .contains(new AtsDetector.Board(AtsProvider.GREENHOUSE, "acme"));
        assertThat(AtsDetector.boardFromUrl("https://boards.greenhouse.io/embed/job_board?for=acme&b=x"))
                .contains(new AtsDetector.Board(AtsProvider.GREENHOUSE, "acme"));
        assertThat(AtsDetector.boardFromUrl("https://jobs.ashbyhq.com/zepto"))
                .contains(new AtsDetector.Board(AtsProvider.ASHBY, "zepto"));
        assertThat(AtsDetector.boardFromUrl("https://acme.com/careers")).isEmpty();
        assertThat(AtsDetector.boardFromUrl("https://jobs.lever.co/")).isEmpty();
    }

    @Test
    void nameSlugs_dropCompanySuffixesAndBrackets() {
        assertThat(AtsDetector.nameSlugs("BharatPe Private Limited")).containsExactly("bharatpe");
        assertThat(AtsDetector.nameSlugs("Ather Energy")).containsExactly("atherenergy", "ather-energy");
        assertThat(AtsDetector.nameSlugs("Infosys Technologies (India)")).containsExactly("infosys");
        assertThat(AtsDetector.nameSlugs("Pvt Ltd")).isEmpty();
    }

    @Test
    void domainSlugs_tryWithAndWithoutHyphens() {
        assertThat(AtsDetector.domainSlugs("bharat-pe.com")).containsExactly("bharat-pe", "bharatpe");
        assertThat(AtsDetector.domainSlugs("groww.in")).containsExactly("groww");
    }
}
