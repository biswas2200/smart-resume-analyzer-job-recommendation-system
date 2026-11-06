package com.resumeanalyser.job;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;
import java.net.URI;
import java.util.ArrayList;
import java.util.List;

/**
 * Companies headquartered in Bengaluru, from Wikidata (open, CC0 data). Only
 * items that look like businesses -- an industry, or a company-type "instance
 * of" -- and that list a website; newspapers, parties and charities without
 * either are left out.
 */
@Component
public class WikidataCompanySource {

    /** Bengaluru on Wikidata. */
    static final String BENGALURU = "Q1355";

    private static final String QUERY = """
            SELECT ?c ?cLabel (SAMPLE(?site) AS ?website) WHERE {
              ?c wdt:P159 wd:%s ; wdt:P856 ?site .
              { ?c wdt:P452 ?industry }
              UNION
              { VALUES ?type { wd:Q4830453 wd:Q783794 wd:Q6881511 wd:Q891723 wd:Q1589009 wd:Q18388277
                               wd:Q1058914 wd:Q167037 wd:Q46970 wd:Q20857065 wd:Q2085381 }
                ?c wdt:P31 ?type }
              SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            }
            GROUP BY ?c ?cLabel
            """;

    private final RestClient client;

    public WikidataCompanySource(@Qualifier("jobFeedRestClient") RestClient client) {
        this.client = client;
    }

    public record WikidataCompany(String wikidataId, String name, String website) {}

    public List<WikidataCompany> bengaluruCompanies() {
        URI uri = UriComponentsBuilder.fromHttpUrl("https://query.wikidata.org/sparql")
                // A template variable, so the braces in the SPARQL are encoded as data.
                .queryParam("query", "{query}")
                .encode().buildAndExpand(QUERY.formatted(BENGALURU)).toUri();
        JsonNode body;
        try {
            body = client.get().uri(uri).accept(MediaType.valueOf("application/sparql-results+json"))
                    .retrieve().body(JsonNode.class);
        } catch (RestClientException e) {
            throw new IllegalStateException("Wikidata query failed: " + e.getMessage(), e);
        }
        return parse(body);
    }

    static List<WikidataCompany> parse(JsonNode body) {
        List<WikidataCompany> companies = new ArrayList<>();
        if (body == null) {
            return companies;
        }
        for (JsonNode row : body.path("results").path("bindings")) {
            String entity = row.path("c").path("value").asText("");
            String name = row.path("cLabel").path("value").asText("").trim();
            String website = row.path("website").path("value").asText("").trim();
            String id = entity.substring(entity.lastIndexOf('/') + 1);
            // An item without an English label comes back labelled with its own id.
            if (name.isEmpty() || website.isEmpty() || name.equals(id)) {
                continue;
            }
            companies.add(new WikidataCompany(id, name, website));
        }
        return companies;
    }
}
