package com.resumeanalyser.job.dto;

import java.time.Instant;
import java.util.List;

/**
 * What Bengaluru's open jobs ask for in the user's best-matched roles.
 *
 * @param roles one entry per top role match, best first
 */
public record InDemandDto(List<RoleDemand> roles) {

    /**
     * @param jobCount   open jobs counted for the role (0 = too few to say)
     * @param computedAt when the demand was last measured, or null if never
     * @param skills     most-asked first
     */
    public record RoleDemand(String role, int jobCount, Instant computedAt, List<SkillDemand> skills) {}

    /**
     * @param share 0..1 of the role's open jobs asking for it
     * @param have  whether the user's latest resume has it
     */
    public record SkillDemand(String skill, double share, boolean have) {}
}
