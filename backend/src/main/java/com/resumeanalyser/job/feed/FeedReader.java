package com.resumeanalyser.job.feed;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.HtmlUtils;
import java.net.URI;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.Optional;
import java.util.regex.Pattern;

/** The HTTP and JSON plumbing the three feeds share. */
final class FeedReader {

    private static final Pattern TAGS = Pattern.compile("<[^>]+>");
    private static final Pattern BLOCK_TAGS = Pattern.compile("(?i)</?(p|div|br|li|ul|ol|h[1-6])[^>]*>");
    private static final Pattern SPACES = Pattern.compile("[ \\t\\x0B\\f\\r]+");
    private static final Pattern BLANK_LINES = Pattern.compile("\\n\\s*\\n+");

    private FeedReader() {}

    /** GETs a JSON document; empty on 404 (no such board), {@link JobFeedException} on anything else that fails. */
    static Optional<JsonNode> getJson(RestClient client, URI uri) {
        try {
            return client.get().uri(uri).accept(MediaType.APPLICATION_JSON).exchange((request, response) -> {
                int status = response.getStatusCode().value();
                if (status == 404) {
                    return Optional.empty();
                }
                if (!response.getStatusCode().is2xxSuccessful()) {
                    throw new JobFeedException("HTTP " + status + " from " + uri.getHost(), null);
                }
                return Optional.ofNullable(response.bodyTo(JsonNode.class));
            });
        } catch (RestClientException e) {
            throw new JobFeedException("Could not read " + uri.getHost() + ": " + e.getMessage(), e);
        }
    }

    static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isValueNode() && !value.isNull() ? value.asText().trim() : "";
    }

    /** ISO-8601 with an offset, or null. */
    static Instant instant(String iso) {
        if (iso == null || iso.isBlank()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(iso).toInstant();
        } catch (DateTimeParseException e) {
            return null;
        }
    }

    /** HTML (possibly entity-escaped, as Greenhouse sends it) to readable plain text. */
    static String plainText(String html) {
        if (html == null || html.isBlank()) {
            return "";
        }
        String unescaped = HtmlUtils.htmlUnescape(html);
        String withBreaks = BLOCK_TAGS.matcher(unescaped).replaceAll("\n");
        String noTags = HtmlUtils.htmlUnescape(TAGS.matcher(withBreaks).replaceAll(""));
        String tidy = SPACES.matcher(noTags.replace(' ', ' ')).replaceAll(" ");
        return BLANK_LINES.matcher(tidy).replaceAll("\n\n").trim();
    }

    static String lower(String value) {
        return value == null ? "" : value.trim().toLowerCase();
    }
}
