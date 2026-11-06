package com.resumeanalyser.job;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

/**
 * A company we read jobs from. Its jobs come from its hiring tool's public
 * feed ({@link #atsProvider} + {@link #atsSlug}), refreshed by
 * {@link JobRefreshService}. Identified by {@link #domain}, so the same
 * company added twice under different spellings stays one row.
 */
@Entity
@Table(name = "companies")
@Getter
@Setter
public class Company {

    @Id
    @GeneratedValue
    private UUID id;

    @Column(nullable = false)
    private String name;

    /** Website host without "www.", e.g. {@code "groww.in"}. Unique. */
    @Column(nullable = false, unique = true)
    private String domain;

    /** The city we collect this company's jobs for, e.g. {@code "Bengaluru"}. */
    @Column(nullable = false, length = 64)
    private String city;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private CompanySource source;

    /** The Wikidata item (e.g. {@code "Q7832370"}), for companies seeded from Wikidata. */
    @Column(name = "wikidata_id", length = 32)
    private String wikidataId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private CompanyStatus status = CompanyStatus.PENDING;

    @Enumerated(EnumType.STRING)
    @Column(name = "ats_provider", length = 16)
    private AtsProvider atsProvider;

    /** The company's board name inside its hiring tool, e.g. {@code "cred"}. */
    @Column(name = "ats_slug", length = 128)
    private String atsSlug;

    @Enumerated(EnumType.STRING)
    @Column(name = "detected_by", length = 16)
    private DetectionMethod detectedBy;

    /** The company's jobs page as last seen linked, even when its hiring tool isn't supported yet. */
    @Column(name = "careers_url", columnDefinition = "TEXT")
    private String careersUrl;

    @Column(name = "last_checked_at")
    private Instant lastCheckedAt;

    @Column(name = "last_fetched_at")
    private Instant lastFetchedAt;

    /** Why the last refresh failed, or null if it worked. */
    @Column(name = "last_error", columnDefinition = "TEXT")
    private String lastError;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();
}
