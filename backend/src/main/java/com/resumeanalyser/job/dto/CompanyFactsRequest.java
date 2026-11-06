package com.resumeanalyser.job.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * What a directory such as the Bangalore Startup Map says about one company, matched to ours by its
 * website domain. Every field except the domain may be blank; a blank field leaves ours as it is.
 */
public record CompanyFactsRequest(
        @NotBlank @Size(max = 255) String domain,
        @Size(max = 32) String sector,
        @Size(max = 64) String area,
        @Size(max = 32) String fundingStage,
        @Size(max = 16) String teamSize,
        Integer founded,
        @Size(max = 255) String tags,
        @Size(max = 1024) String careersUrl
) {}
