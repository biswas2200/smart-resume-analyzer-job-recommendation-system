package com.resumeanalyser.job;

/** Whether we can read a company's jobs. */
public enum CompanyStatus {
    /** Added, not checked for a job feed yet. */
    PENDING,
    /** A job feed was found; its jobs are refreshed daily. */
    ACTIVE,
    /** None of the supported hiring tools has a feed for it. */
    UNSUPPORTED
}
