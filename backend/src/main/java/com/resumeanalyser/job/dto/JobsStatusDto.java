package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.JobsRunner;

/**
 * @param run the task running now or the last to finish (null if none since start-up)
 */
public record JobsStatusDto(
        JobsRunner.Run run,
        long companiesActive,
        long companiesPending,
        long companiesUnsupported,
        long openJobs
) {}
