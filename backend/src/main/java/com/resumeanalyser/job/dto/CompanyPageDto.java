package com.resumeanalyser.job.dto;

import java.util.List;

/** One page of {@link CompanyCardDto}s, with enough to show "24 of 1,085" and a Load more button. */
public record CompanyPageDto(List<CompanyCardDto> items, int page, int size, long total, boolean hasMore) {}
