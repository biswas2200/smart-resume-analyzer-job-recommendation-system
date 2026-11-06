package com.resumeanalyser.job;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class WikidataCompanySourceTest {

    @Test
    void parse_keepsLabelledRowsWithAWebsite() throws Exception {
        var body = new ObjectMapper().readTree("""
                {"results": {"bindings": [
                  {"c": {"value": "http://www.wikidata.org/entity/Q7832370"}, "cLabel": {"value": "Infosys"},
                   "website": {"value": "https://www.infosys.com"}},
                  {"c": {"value": "http://www.wikidata.org/entity/Q999"}, "cLabel": {"value": "Q999"},
                   "website": {"value": "https://unlabelled.example"}},
                  {"c": {"value": "http://www.wikidata.org/entity/Q5"}, "cLabel": {"value": "No Site Ltd"}}
                ]}}
                """);

        assertThat(WikidataCompanySource.parse(body))
                .containsExactly(new WikidataCompanySource.WikidataCompany("Q7832370", "Infosys", "https://www.infosys.com"));
    }
}
