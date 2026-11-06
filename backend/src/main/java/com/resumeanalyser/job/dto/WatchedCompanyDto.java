package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.Company;
import com.resumeanalyser.job.CompanyStatus;
import java.time.Instant;
import java.util.UUID;

/**
 * A company on the user's watchlist. {@code status} says whether we can read
 * its jobs yet (ACTIVE) or only list it (PENDING, UNSUPPORTED); {@code newJobs}
 * counts open jobs first seen in the last few days.
 */
public record WatchedCompanyDto(
        UUID companyId,
        String name,
        String domain,
        CompanyStatus status,
        String careersUrl,
        long openJobs,
        long newJobs,
        Instant addedAt
) {
    public static WatchedCompanyDto of(Company company, long openJobs, long newJobs, Instant addedAt) {
        return new WatchedCompanyDto(company.getId(), company.getName(), company.getDomain(), company.getStatus(),
                company.getCareersUrl(), openJobs, newJobs, addedAt);
    }
}
