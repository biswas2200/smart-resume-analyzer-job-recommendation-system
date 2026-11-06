package com.resumeanalyser.client.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/**
 * The ML service's job ranking ({@code POST /rank-jobs}, see
 * {@code ml-service/app/services/job_rank.py}): a resume's skills and its
 * best-matched role titles against jobs with their stored skills.
 */
public final class RankJobsDto {

    private RankJobsDto() {}

    public record Job(String id, String title, List<String> skills) {}

    public record Request(
            List<String> skills,
            List<String> roles,
            List<Job> jobs,
            @JsonProperty("top_n") int topN
    ) {}

    /**
     * @param score       0.45 * coverage * min(1, job skills / 5) + 0.30 * similarity + 0.25 * roleFit
     *                    (0.5 * roleFit when the job's skills couldn't be read)
     * @param closestRole which of the resume's roles the job title is closest to, or null
     */
    public record RankedJob(
            String id,
            double score,
            double coverage,
            double similarity,
            @JsonProperty("role_fit") double roleFit,
            @JsonProperty("matched_skills") List<String> matchedSkills,
            @JsonProperty("missing_skills") List<String> missingSkills,
            @JsonProperty("closest_role") String closestRole,
            String explanation
    ) {}

    public record Response(List<RankedJob> jobs) {}
}
