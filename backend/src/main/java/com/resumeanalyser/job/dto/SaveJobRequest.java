package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.SavedJobStatus;

/** @param status where the application stands; omitted = SAVED (or unchanged if already saved) */
public record SaveJobRequest(SavedJobStatus status) {}
