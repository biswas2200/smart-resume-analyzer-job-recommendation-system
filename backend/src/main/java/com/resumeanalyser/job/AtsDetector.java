package com.resumeanalyser.job;

import com.resumeanalyser.job.feed.FeedPosting;
import com.resumeanalyser.job.feed.JobFeed;
import com.resumeanalyser.job.feed.JobFeeds;
import org.springframework.stereotype.Component;
import java.net.URI;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Finds which hiring tool publishes a company's jobs. Only the tools' own
 * public feeds are asked -- no company website is crawled:
 * <ol>
 *   <li>a careers link that already points at a tool (jobs.lever.co/acme) is read directly;</li>
 *   <li>otherwise each tool is asked for a board named after the website (groww.in -> groww),</li>
 *   <li>then after the company name ("Bharat Pe" -> bharatpe, bharat-pe).</li>
 * </ol>
 * A hit is only accepted once the feed actually answers. A board found by
 * guessing (2 and 3) must also have at least one job in our country: the
 * first discovery run matched "The Better India" to Lever's "better" and
 * via.com to Greenhouse's "via", both other companies' boards with no jobs
 * here. A board the careers link names needs no such check.
 */
@Component
public class AtsDetector {

    private static final Pattern LEVER_URL = Pattern.compile("^jobs(?:\\.eu)?\\.lever\\.co$");
    private static final Pattern GREENHOUSE_URL = Pattern.compile("^(?:job-)?boards(?:\\.eu)?\\.greenhouse\\.io$");
    private static final Pattern ASHBY_URL = Pattern.compile("^jobs\\.ashbyhq\\.com$");
    private static final Pattern GREENHOUSE_EMBED_FOR = Pattern.compile("[?&]for=([A-Za-z0-9_-]+)");
    private static final Set<String> NAME_NOISE = Set.of(
            "private", "pvt", "limited", "ltd", "llp", "inc", "corp", "corporation", "company", "co",
            "technologies", "technology", "india", "the");

    private final JobFeeds feeds;
    private final Throttle throttle;
    private final LocationMatcher locations;

    public AtsDetector(JobFeeds feeds, Throttle throttle, LocationMatcher locations) {
        this.feeds = feeds;
        this.throttle = throttle;
        this.locations = locations;
    }

    /** A found feed and the postings it returned (so the caller can store them without asking again). */
    public record Detection(AtsProvider provider, String slug, DetectionMethod method, List<FeedPosting> postings) {}

    /**
     * @param careersUrl optional; a link to the company's jobs page
     * @throws com.resumeanalyser.job.feed.JobFeedException if a feed could not be read (try again later)
     */
    public Optional<Detection> detect(String name, String domain, String careersUrl) {
        Optional<Board> fromUrl = boardFromUrl(careersUrl);
        if (fromUrl.isPresent()) {
            Board board = fromUrl.get();
            return ask(feeds.get(board.provider()), board.slug(), DetectionMethod.CAREERS_URL);
        }
        List<String> domainSlugs = domainSlugs(domain);
        for (String slug : domainSlugs) {
            Optional<Detection> hit = askEveryTool(slug, DetectionMethod.DOMAIN_SLUG);
            if (hit.isPresent()) {
                return hit;
            }
        }
        for (String slug : nameSlugs(name)) {
            if (domainSlugs.contains(slug)) {
                continue;
            }
            Optional<Detection> hit = askEveryTool(slug, DetectionMethod.NAME_SLUG);
            if (hit.isPresent()) {
                return hit;
            }
        }
        return Optional.empty();
    }

    private Optional<Detection> askEveryTool(String slug, DetectionMethod method) {
        for (JobFeed feed : feeds.all()) {
            Optional<Detection> hit = ask(feed, slug, method);
            if (hit.isPresent()) {
                return hit;
            }
        }
        return Optional.empty();
    }

    private Optional<Detection> ask(JobFeed feed, String slug, DetectionMethod method) {
        throttle.pause();
        return feed.fetch(slug)
                .filter(postings -> method == DetectionMethod.CAREERS_URL || hasJobInCountry(postings))
                .map(postings -> new Detection(feed.provider(), slug, method, postings));
    }

    private boolean hasJobInCountry(List<FeedPosting> postings) {
        return postings.stream().anyMatch(posting -> locations.inCountry(posting.locations()));
    }

    record Board(AtsProvider provider, String slug) {}

    /** jobs.lever.co/acme, boards.greenhouse.io/acme, job-boards.greenhouse.io/acme, jobs.ashbyhq.com/acme. */
    static Optional<Board> boardFromUrl(String url) {
        if (url == null || url.isBlank()) {
            return Optional.empty();
        }
        URI uri;
        try {
            uri = URI.create(url.contains("://") ? url.trim() : "https://" + url.trim());
        } catch (IllegalArgumentException e) {
            return Optional.empty();
        }
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase(Locale.ROOT);
        String path = uri.getPath() == null ? "" : uri.getPath();
        String first = path.replaceFirst("^/", "").split("/")[0];
        if (GREENHOUSE_URL.matcher(host).matches() && first.equals("embed") && uri.getRawQuery() != null) {
            Matcher match = GREENHOUSE_EMBED_FOR.matcher("?" + uri.getRawQuery());
            return match.find() ? Optional.of(new Board(AtsProvider.GREENHOUSE, match.group(1))) : Optional.empty();
        }
        if (first.isEmpty()) {
            return Optional.empty();
        }
        if (LEVER_URL.matcher(host).matches()) {
            return Optional.of(new Board(AtsProvider.LEVER, first));
        }
        if (GREENHOUSE_URL.matcher(host).matches()) {
            return Optional.of(new Board(AtsProvider.GREENHOUSE, first));
        }
        if (ASHBY_URL.matcher(host).matches()) {
            return Optional.of(new Board(AtsProvider.ASHBY, first));
        }
        return Optional.empty();
    }

    /** "groww.in" -> [groww]; "bharat-pe.com" -> [bharat-pe, bharatpe]. */
    static List<String> domainSlugs(String domain) {
        if (domain == null || domain.isBlank()) {
            return List.of();
        }
        String label = Domains.brandLabel(domain);
        Set<String> slugs = new LinkedHashSet<>();
        slugs.add(label);
        slugs.add(label.replace("-", ""));
        return new ArrayList<>(slugs);
    }

    /** "BharatPe Private Limited" -> [bharatpe]; "Ather Energy" -> [atherenergy, ather-energy]. */
    static List<String> nameSlugs(String name) {
        if (name == null || name.isBlank()) {
            return List.of();
        }
        String cleaned = name.toLowerCase(Locale.ROOT)
                .replaceAll("\\(.*?\\)", " ")
                .replace("&", " and ")
                .replaceAll("[^a-z0-9]+", " ")
                .trim();
        List<String> words = new ArrayList<>();
        for (String word : cleaned.split(" ")) {
            if (!word.isEmpty() && !NAME_NOISE.contains(word)) {
                words.add(word);
            }
        }
        if (words.isEmpty()) {
            return List.of();
        }
        Set<String> slugs = new LinkedHashSet<>();
        slugs.add(String.join("", words));
        slugs.add(String.join("-", words));
        return new ArrayList<>(slugs);
    }
}
