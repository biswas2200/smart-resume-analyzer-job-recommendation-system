package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

/** A job a user saved, and where their application stands. One row per user and job. */
@Entity
@Table(name = "saved_jobs")
@Getter
@Setter
public class SavedJob {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "job_posting_id", nullable = false)
    private JobPosting jobPosting;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private SavedJobStatus status = SavedJobStatus.SAVED;

    @Column(name = "saved_at", nullable = false, updatable = false)
    private Instant savedAt = Instant.now();

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();
}
