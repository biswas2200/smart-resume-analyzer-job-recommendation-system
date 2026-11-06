package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.JobPosting;
import java.time.Instant;
import java.util.UUID;

/**
 * A job for the list view. Carries a short excerpt, not the full text: the
 * card links to the company's original posting.
 */
public record JobPostingDto(
        UUID id,
        String title,
        String company,
        String companyDomain,
        String location,
        String workplaceType,
        String employmentType,
        String department,
        String url,
        String applyUrl,
        String excerpt,
        Instant publishedAt,
        Instant firstSeenAt,
        boolean active
) {
    static final int EXCERPT = 280;

    public static JobPostingDto of(JobPosting posting) {
        return new JobPostingDto(posting.getId(), posting.getTitle(), posting.getCompany().getName(),
                posting.getCompany().getDomain(), posting.getLocation(), posting.getWorkplaceType(),
                posting.getEmploymentType(), posting.getDepartment(), posting.getUrl(),
                posting.getApplyUrl().isEmpty() ? posting.getUrl() : posting.getApplyUrl(),
                excerpt(posting.getDescription()), posting.getPublishedAt(), posting.getFirstSeenAt(), posting.isActive());
    }

    static String excerpt(String description) {
        String flat = description.replaceAll("\\s+", " ").trim();
        if (flat.length() <= EXCERPT) {
            return flat;
        }
        int cut = flat.lastIndexOf(' ', EXCERPT);
        return flat.substring(0, cut > 0 ? cut : EXCERPT) + "…";
    }
}
