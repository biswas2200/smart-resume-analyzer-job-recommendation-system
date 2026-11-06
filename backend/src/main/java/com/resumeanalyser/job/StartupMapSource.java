package com.resumeanalyser.job;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.HtmlUtils;
import java.net.URI;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Companies listed on the Bangalore Startup Map, read from its public pages
 * only: the sitemap it publishes, and each company page's schema.org
 * Organization data (name, website) plus its "Apply" links, which point at
 * the company's own hiring tool. The site's {@code /api/} is never called --
 * its robots.txt asks crawlers to keep out of it. Used with the site
 * owner's permission requested (22 Oct 2026); credited in the app.
 */
@Component
public class StartupMapSource {

    static final String SITEMAP = "https://www.bangalorestartupmap.com/sitemap.xml";

    private static final Pattern LOC = Pattern.compile("<loc>\\s*([^<\\s]+)\\s*</loc>");
    private static final Pattern LD_JSON = Pattern.compile(
            "<script[^>]*type=\"application/ld\\+json\"[^>]*>(.*?)</script>", Pattern.DOTALL);
    private static final Pattern ANCHOR = Pattern.compile("<a\\b[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", Pattern.DOTALL);
    private static final Pattern TAGS = Pattern.compile("<[^>]+>");

    private final RestClient client;
    private final ObjectMapper json;

    public StartupMapSource(@Qualifier("jobFeedRestClient") RestClient client, ObjectMapper json) {
        this.client = client;
        this.json = json;
    }

    /**
     * One company page.
     *
     * @param applyLinks every "Apply" link on the page, in page order (empty when it lists no open jobs)
     */
    public record MapCompany(String pageUrl, String name, String website, List<String> applyLinks) {}

    /** Every company page the sitemap lists. */
    public List<String> companyPages() {
        return companyPages(get(SITEMAP, MediaType.APPLICATION_XML));
    }

    /** Reads one company page; empty if it has no name or website. */
    public Optional<MapCompany> read(String pageUrl) {
        return parse(pageUrl, get(pageUrl, MediaType.TEXT_HTML));
    }

    static List<String> companyPages(String sitemap) {
        Set<String> pages = new LinkedHashSet<>();
        Matcher match = LOC.matcher(sitemap);
        while (match.find()) {
            String url = match.group(1);
            if (URI.create(url).getPath().startsWith("/company/")) {
                pages.add(url);
            }
        }
        return new ArrayList<>(pages);
    }

    Optional<MapCompany> parse(String pageUrl, String html) {
        String name = null;
        String website = null;
        Matcher block = LD_JSON.matcher(html);
        while (block.find() && name == null) {
            try {
                JsonNode node = json.readTree(block.group(1));
                if ("Organization".equals(node.path("@type").asText())) {
                    name = node.path("name").asText("").trim();
                    website = node.path("url").asText("").trim();
                }
            } catch (Exception e) {
                // Not JSON we understand; try the next block.
            }
        }
        if (name == null || name.isEmpty() || website == null || website.isEmpty()) {
            return Optional.empty();
        }
        List<String> applyLinks = new ArrayList<>();
        Matcher anchor = ANCHOR.matcher(html);
        while (anchor.find()) {
            String text = TAGS.matcher(anchor.group(2)).replaceAll("");
            if (text.trim().startsWith("Apply")) {
                applyLinks.add(HtmlUtils.htmlUnescape(anchor.group(1)));
            }
        }
        return Optional.of(new MapCompany(pageUrl, HtmlUtils.htmlUnescape(name), website, applyLinks));
    }

    private String get(String url, MediaType accept) {
        try {
            String body = client.get().uri(URI.create(url)).accept(accept).retrieve().body(String.class);
            return body == null ? "" : body;
        } catch (RestClientException e) {
            throw new IllegalStateException("Could not read " + url + ": " + e.getMessage(), e);
        }
    }
}
