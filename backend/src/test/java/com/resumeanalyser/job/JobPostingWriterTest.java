package com.resumeanalyser.job;

import com.resumeanalyser.job.feed.FeedPosting;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** How one company's feed is stored: city filter, new vs updated, and closing what left the feed. */
@ExtendWith(MockitoExtension.class)
class JobPostingWriterTest {

    private static final Instant NOW = Instant.parse("2026-10-22T06:30:00Z");

    @Mock
    private JobPostingRepository postings;
    @Mock
    private CompanyRepository companies;

    private JobPostingWriter writer;
    private Company company;

    @BeforeEach
    void setUp() {
        LocationMatcher bengaluru = new LocationMatcher(new JobsProperties(
                "Bengaluru", List.of("bengaluru", "bangalore"), List.of("india"), "t", Duration.ZERO, Duration.ZERO, Duration.ofSeconds(1)));
        writer = new JobPostingWriter(postings, companies, bengaluru, Clock.fixed(NOW, ZoneOffset.UTC));
        company = new Company();
        company.setName("Groww");
        company.setLastError("old error");
    }

    private static FeedPosting feed(String id, String title, String location) {
        return new FeedPosting(id, title, List.of(location), "", "", "", "https://example.com/" + id, "",
                "Description of " + title, null);
    }

    private static JobPosting stored(String id, boolean active) {
        JobPosting posting = new JobPosting();
        posting.setExternalId(id);
        posting.setTitle("Old title");
        posting.setUrl("https://example.com/" + id);
        posting.setActive(active);
        posting.setFirstSeenAt(Instant.parse("2026-10-01T00:00:00Z"));
        return posting;
    }

    @Test
    void keepsOnlyCityJobs_addsNewOnes_updatesKnownOnes_andClosesThoseThatLeft() {
        JobPosting known = stored("1", true);
        JobPosting leaving = stored("2", true);
        JobPosting alreadyClosed = stored("3", false);
        when(postings.findByCompany(company)).thenReturn(List.of(known, leaving, alreadyClosed));
        when(postings.save(any(JobPosting.class))).thenAnswer(inv -> inv.getArgument(0));

        JobPostingWriter.Applied applied = writer.apply(company, List.of(
                feed("1", "SDE II", "Bengaluru, India"),
                feed("4", "Data Analyst", "Bangalore"),
                feed("5", "Sales Lead", "Mumbai")));

        assertThat(applied).isEqualTo(new JobPostingWriter.Applied(3, 2, 1, 1));
        assertThat(known.getTitle()).isEqualTo("SDE II");
        assertThat(known.getFirstSeenAt()).isEqualTo(Instant.parse("2026-10-01T00:00:00Z"));
        assertThat(known.getLastSeenAt()).isEqualTo(NOW);
        assertThat(leaving.isActive()).isFalse();
        assertThat(alreadyClosed.isActive()).isFalse();

        ArgumentCaptor<JobPosting> saved = ArgumentCaptor.forClass(JobPosting.class);
        verify(postings, atLeastOnce()).save(saved.capture());
        JobPosting added = saved.getAllValues().stream().filter(p -> "4".equals(p.getExternalId())).findFirst().orElseThrow();
        assertThat(added.getCompany()).isSameAs(company);
        assertThat(added.getFirstSeenAt()).isEqualTo(NOW);
        assertThat(added.isActive()).isTrue();
        assertThat(saved.getAllValues()).noneMatch(p -> "5".equals(p.getExternalId()));

        assertThat(company.getLastFetchedAt()).isEqualTo(NOW);
        assertThat(company.getLastError()).isNull();
    }

    @Test
    void aJobThatComesBack_isReopened() {
        JobPosting closed = stored("7", false);
        when(postings.findByCompany(company)).thenReturn(List.of(closed));
        when(postings.save(any(JobPosting.class))).thenAnswer(inv -> inv.getArgument(0));

        JobPostingWriter.Applied applied = writer.apply(company, List.of(feed("7", "QA", "Bengaluru")));

        assertThat(closed.isActive()).isTrue();
        assertThat(applied.added()).isZero();
    }

    @Test
    void longDescriptionsAreCut() {
        when(postings.findByCompany(company)).thenReturn(List.of());
        when(postings.save(any(JobPosting.class))).thenAnswer(inv -> inv.getArgument(0));
        FeedPosting huge = new FeedPosting("9", "T", List.of("Bengaluru"), "", "", "", "https://x/9", "",
                "x".repeat(JobPostingWriter.MAX_DESCRIPTION + 50), null);

        writer.apply(company, List.of(huge));

        ArgumentCaptor<JobPosting> saved = ArgumentCaptor.forClass(JobPosting.class);
        verify(postings).save(saved.capture());
        assertThat(saved.getValue().getDescription()).hasSize(JobPostingWriter.MAX_DESCRIPTION);
    }
}
