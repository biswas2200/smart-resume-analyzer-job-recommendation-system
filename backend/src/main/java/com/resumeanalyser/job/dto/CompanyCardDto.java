package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.Company;
import com.resumeanalyser.job.CompanySource;
import com.resumeanalyser.job.CompanyStatus;

import java.util.UUID;

/**
 * One company in the browsable list (the watchlist page's cards): what we know about it,
 * how many of its jobs are open now, and whether the signed-in user watches it.
 *
 * @param careersUrl where to apply: its hiring tool's page when we know it, else null
 */
public record CompanyCardDto(
        UUID id,
        String name,
        String domain,
        CompanyStatus status,
        CompanySource source,
        String careersUrl,
        long openJobs,
        boolean watched
) {
    public static CompanyCardDto of(Company company, long openJobs, boolean watched) {
        return new CompanyCardDto(company.getId(), company.getName(), company.getDomain(), company.getStatus(),
                company.getSource(), company.getCareersUrl(), openJobs, watched);
    }
}
