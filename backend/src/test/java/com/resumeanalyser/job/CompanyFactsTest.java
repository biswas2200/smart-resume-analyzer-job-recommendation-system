package com.resumeanalyser.job;

import com.resumeanalyser.job.dto.CompanyFactsRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Clock;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CompanyFactsTest {

    @Mock private CompanyRepository companies;
    @Mock private WikidataCompanySource wikidata;
    @Mock private StartupMapSource startupMap;
    @Mock private AtsDetector detector;
    @Mock private JobPostingWriter writer;
    @Mock private Throttle throttle;
    @Mock private JobsProperties properties;

    private CompanyService service;
    private Company groww;

    @BeforeEach
    void setUp() {
        service = new CompanyService(companies, wikidata, startupMap, detector, writer, throttle, properties, Clock.systemUTC());
        groww = new Company();
        groww.setName("Groww");
        groww.setDomain("groww.in");
        groww.setSector("Fintech");
    }

    @Test
    void facts_areMatchedOnDomain_andAddedToTheCompany() {
        when(companies.findByDomain("groww.in")).thenReturn(Optional.of(groww));

        var summary = service.applyFacts(List.of(new CompanyFactsRequest(
                "https://www.Groww.in/", "", "Indiranagar", "Series E", "201-1000", 2016, "investing; stocks",
                "https://boards.greenhouse.io/groww")));

        assertThat(summary.updated()).isEqualTo(1);
        assertThat(summary.unmatched()).isZero();
        assertThat(groww.getSector()).as("a blank fact leaves ours as it is").isEqualTo("Fintech");
        assertThat(groww.getArea()).isEqualTo("Indiranagar");
        assertThat(groww.getFundingStage()).isEqualTo("Series E");
        assertThat(groww.getTeamSize()).isEqualTo("201-1000");
        assertThat(groww.getFounded()).isEqualTo(2016);
        assertThat(groww.getTags()).isEqualTo("investing; stocks");
        assertThat(groww.getCareersUrl()).isEqualTo("https://boards.greenhouse.io/groww");
        verify(companies).save(groww);
    }

    @Test
    void anExistingCareersLink_isNotReplaced_andAnUnknownDomainIsCounted() {
        groww.setCareersUrl("https://jobs.lever.co/groww");
        when(companies.findByDomain("groww.in")).thenReturn(Optional.of(groww));
        when(companies.findByDomain("nowhere.example")).thenReturn(Optional.empty());

        var summary = service.applyFacts(List.of(
                new CompanyFactsRequest("groww.in", null, null, null, null, null, null, "https://other.example/jobs"),
                new CompanyFactsRequest("nowhere.example", "AI", null, null, null, null, null, null),
                new CompanyFactsRequest("not a domain", "AI", null, null, null, null, null, null)));

        assertThat(summary.updated()).isEqualTo(1);
        assertThat(summary.unmatched()).isEqualTo(2);
        assertThat(groww.getCareersUrl()).isEqualTo("https://jobs.lever.co/groww");
        verify(companies).save(groww);
    }
}
