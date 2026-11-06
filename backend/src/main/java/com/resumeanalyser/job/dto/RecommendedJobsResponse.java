package com.resumeanalyser.job.dto;

import java.util.List;
import java.util.UUID;

/**
 * @param resumeId      the resume version the jobs were ranked against, or null if the user has none yet
 * @param roles         the user's best-matched roles that steered the ranking
 * @param openJobs      open jobs in the city before filters
 * @param jobs          best first
 */
public record RecommendedJobsResponse(
        UUID resumeId,
        Integer resumeVersion,
        List<String> roles,
        long openJobs,
        List<RecommendedJobDto> jobs
) {}
