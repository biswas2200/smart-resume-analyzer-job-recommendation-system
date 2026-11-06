package com.resumeanalyser.job.dto;

import com.resumeanalyser.job.Company;
import com.resumeanalyser.job.CompanyStatus;
import java.util.UUID;

/** A company the user can add to their watchlist, from a name search. */
public record CompanyOptionDto(UUID id, String name, String domain, CompanyStatus status, boolean watched) {

    public static CompanyOptionDto of(Company company, boolean watched) {
        return new CompanyOptionDto(company.getId(), company.getName(), company.getDomain(), company.getStatus(), watched);
    }
}
