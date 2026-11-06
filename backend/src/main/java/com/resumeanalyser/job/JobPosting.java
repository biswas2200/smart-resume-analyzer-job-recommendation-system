package com.resumeanalyser.job;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * One open job at a {@link Company}, as last read from its hiring tool's
 * feed. A posting that drops out of the feed is kept with {@link #active}
 * false, so "New" badges and history survive a refresh.
 */
@Entity
@Table(name = "job_postings")
@Getter
@Setter
public class JobPosting {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "company_id", nullable = false)
    private Company company;

    /** The posting's id inside its hiring tool. Unique per company. */
    @Column(name = "external_id", nullable = false, length = 128)
    private String externalId;

    @Column(nullable = false, length = 512)
    private String title;

    @Column(nullable = false, length = 512)
    private String location = "";

    /** e.g. {@code "onsite"}, {@code "hybrid"}, {@code "remote"}; empty if the feed doesn't say. */
    @Column(name = "workplace_type", nullable = false, length = 32)
    private String workplaceType = "";

    @Column(name = "employment_type", nullable = false, length = 64)
    private String employmentType = "";

    @Column(nullable = false)
    private String department = "";

    /** The original posting, where the full description lives. */
    @Column(nullable = false, columnDefinition = "TEXT")
    private String url;

    @Column(name = "apply_url", nullable = false, columnDefinition = "TEXT")
    private String applyUrl = "";

    /** Plain-text description, kept for matching against resumes. */
    @Column(nullable = false, columnDefinition = "TEXT")
    private String description = "";

    /**
     * The skills the posting asks for, extracted by the ML service and reused
     * for every user's ranking; null until extracted (or after the
     * description changed). See {@link JobSkillService}.
     */
    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private List<String> skills;

    @Column(name = "published_at")
    private Instant publishedAt;

    @Column(name = "first_seen_at", nullable = false, updatable = false)
    private Instant firstSeenAt = Instant.now();

    @Column(name = "last_seen_at", nullable = false)
    private Instant lastSeenAt = Instant.now();

    @Column(nullable = false)
    private boolean active = true;
}
