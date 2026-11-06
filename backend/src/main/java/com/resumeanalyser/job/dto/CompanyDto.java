package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.AtsProvider;
import com.resumeanalyser.job.Company;
import com.resumeanalyser.job.CompanySource;
import com.resumeanalyser.job.CompanyStatus;
import com.resumeanalyser.job.DetectionMethod;
import java.time.Instant;
import java.util.UUID;

/** A company in our list, with how (and whether) we read its jobs. */
public record CompanyDto(
        UUID id,
        String name,
        String domain,
        String city,
        CompanySource source,
        CompanyStatus status,
        AtsProvider atsProvider,
        String atsSlug,
        DetectionMethod detectedBy,
        String careersUrl,
        Instant lastFetchedAt,
        String lastError,
        long openJobs
) {
    public static CompanyDto of(Company company, long openJobs) {
        return new CompanyDto(company.getId(), company.getName(), company.getDomain(), company.getCity(),
                company.getSource(), company.getStatus(), company.getAtsProvider(), company.getAtsSlug(),
                company.getDetectedBy(), company.getCareersUrl(), company.getLastFetchedAt(), company.getLastError(), openJobs);
    }
}
