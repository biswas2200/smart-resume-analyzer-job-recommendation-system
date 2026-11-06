package com.resumeanalyser.job.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * @param careersUrl optional link to the company's jobs page; a Lever, Greenhouse or
 *                   Ashby link there is the surest way to find its feed
 */
public record AddCompanyRequest(
        @NotBlank @Size(max = 255) String name,
        @NotBlank @Size(max = 512) String website,
        @Size(max = 1024) String careersUrl
) {}
