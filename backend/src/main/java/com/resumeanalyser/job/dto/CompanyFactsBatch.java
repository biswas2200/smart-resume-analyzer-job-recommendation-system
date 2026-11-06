package com.resumeanalyser.job.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;

/** Up to 5,000 companies' facts in one call to {@code POST /admin/jobs/companies/facts}. */
public record CompanyFactsBatch(@NotNull @Size(max = 5000) List<@Valid CompanyFactsRequest> companies) {}
