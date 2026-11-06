package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.SavedJobStatus;
import java.util.List;

/**
 * A job ranked for the signed-in user's latest resume.
 *
 * @param score       0..1, see the ML service's {@code job_rank.py}
 * @param closestRole which of the user's matched roles the job title is closest to, or null
 * @param why         one deterministic sentence or three on why it ranks here
 * @param savedStatus the user's tracking status if they saved it, else null
 */
public record RecommendedJobDto(
        JobPostingDto job,
        double score,
        double coverage,
        List<String> matchedSkills,
        List<String> missingSkills,
        String closestRole,
        String why,
        SavedJobStatus savedStatus
) {}
