package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.SavedJob;
import com.resumeanalyser.job.SavedJobStatus;
import java.time.Instant;

/** A saved job; {@code job.active} is false once the company has closed it. */
public record SavedJobDto(JobPostingDto job, SavedJobStatus status, Instant savedAt, Instant updatedAt) {

    public static SavedJobDto of(SavedJob saved) {
        return new SavedJobDto(JobPostingDto.of(saved.getJobPosting()), saved.getStatus(),
                saved.getSavedAt(), saved.getUpdatedAt());
    }
}
