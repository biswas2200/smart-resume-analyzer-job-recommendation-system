package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.common.ResourceNotFoundException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class SavedJobServiceTest {

    private static final Instant NOW = Instant.parse("2026-10-22T10:00:00Z");

    @Mock private SavedJobRepository saved;
    @Mock private JobPostingRepository postings;

    private SavedJobService service;
    private final User user = new User();
    private JobPosting posting;

    @BeforeEach
    void setUp() {
        service = new SavedJobService(saved, postings, Clock.fixed(NOW, ZoneOffset.UTC));
        Company company = new Company();
        company.setName("Groww");
        posting = new JobPosting();
        posting.setId(UUID.randomUUID());
        posting.setCompany(company);
        posting.setTitle("SDE II");
        posting.setUrl("https://x");
    }

    @Test
    void savingANewJob_startsAsSaved() {
        when(postings.findById(posting.getId())).thenReturn(Optional.of(posting));
        when(saved.findByUserAndJobPosting(user, posting)).thenReturn(Optional.empty());
        when(saved.save(any(SavedJob.class))).thenAnswer(inv -> inv.getArgument(0));

        var dto = service.save(user, posting.getId(), null);

        assertThat(dto.status()).isEqualTo(SavedJobStatus.SAVED);
        assertThat(dto.savedAt()).isEqualTo(NOW);
        assertThat(dto.job().title()).isEqualTo("SDE II");
    }

    @Test
    void savingAgainWithAStatus_updatesTheSameEntry() {
        SavedJob existing = new SavedJob();
        existing.setUser(user);
        existing.setJobPosting(posting);
        existing.setSavedAt(Instant.parse("2026-10-20T00:00:00Z"));
        when(postings.findById(posting.getId())).thenReturn(Optional.of(posting));
        when(saved.findByUserAndJobPosting(user, posting)).thenReturn(Optional.of(existing));
        when(saved.save(existing)).thenReturn(existing);

        var dto = service.save(user, posting.getId(), SavedJobStatus.APPLIED);

        assertThat(dto.status()).isEqualTo(SavedJobStatus.APPLIED);
        assertThat(dto.savedAt()).isEqualTo(Instant.parse("2026-10-20T00:00:00Z"));
        assertThat(dto.updatedAt()).isEqualTo(NOW);
    }

    @Test
    void savingAMissingJob_isNotFound() {
        UUID missing = UUID.randomUUID();
        when(postings.findById(missing)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.save(user, missing, null)).isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void removing_deletesOnlyThatUsersEntry() {
        SavedJob existing = new SavedJob();
        when(postings.findById(posting.getId())).thenReturn(Optional.of(posting));
        when(saved.findByUserAndJobPosting(user, posting)).thenReturn(Optional.of(existing));

        service.remove(user, posting.getId());

        verify(saved).delete(existing);
    }
}
