package com.resumeanalyser.job;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;
import java.time.Instant;
import java.util.UUID;

/** One skill's share of a catalogue role's open jobs, as of the last daily update. */
@Entity
@Table(name = "market_skill_demand")
@Getter
@Setter
public class MarketSkillDemand {

    @Id
    @GeneratedValue
    private UUID id;

    @Column(name = "role_title", nullable = false)
    private String roleTitle;

    @Column(nullable = false)
    private String skill;

    /** 0..1: the share of the role's open jobs asking for this skill. */
    @Column(nullable = false)
    private double share;

    @Column(name = "job_count", nullable = false)
    private int jobCount;

    @Column(name = "computed_at", nullable = false)
    private Instant computedAt;
}
