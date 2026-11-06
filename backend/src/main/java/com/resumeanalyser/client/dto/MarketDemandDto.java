package com.resumeanalyser.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

/**
 * The ML service's job-market demand ({@code POST /market-demand}, see
 * {@code ml-service/app/services/market_demand.py}): open jobs in, per
 * catalogue role the skills they ask for and one EMA signal per catalogue skill out.
 */
public final class MarketDemandDto {

    private MarketDemandDto() {}

    public record Request(List<RankJobsDto.Job> jobs) {}

    public record SkillDemand(String skill, double share) {}

    /**
     * @param inDemand the skills the role's jobs ask for most, most-asked first
     * @param signals  FR-7.2's new_signal in [0.5, 1.0] for each skill in the role's catalogue entry
     */
    public record RoleDemand(
            String role,
            String domain,
            @JsonProperty("job_count") int jobCount,
            @JsonProperty("in_demand") List<SkillDemand> inDemand,
            Map<String, Double> signals
    ) {}

    public record Response(List<RoleDemand> roles, @JsonProperty("unassigned_jobs") int unassignedJobs) {}
}
