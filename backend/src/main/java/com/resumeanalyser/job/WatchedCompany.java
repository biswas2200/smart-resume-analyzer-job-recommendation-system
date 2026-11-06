package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

/** A company on a user's watchlist. One row per user and company. */
@Entity
@Table(name = "watched_companies")
@Getter
@Setter
public class WatchedCompany {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "company_id", nullable = false)
    private Company company;

    @Column(name = "added_at", nullable = false, updatable = false)
    private Instant addedAt = Instant.now();
}
