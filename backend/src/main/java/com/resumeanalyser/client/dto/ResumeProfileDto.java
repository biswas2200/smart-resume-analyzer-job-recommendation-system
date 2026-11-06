package com.resumeanalyser.client.dto;

import java.util.List;

/**
 * Mirrors the ML service's {@code ResumeProfile} Pydantic model
 * (ml-service/app/models/schemas.py) field-for-field -- this is the raw shape
 * {@code POST /analyze-file} returns, before it's mapped into
 * {@link com.resumeanalyser.resume.ParsedProfile}.
 */
public record ResumeProfileDto(
        String name,
        String email,
        String phone,
        List<String> skills,
        List<ExperienceEntryDto> experience,
        List<EducationEntryDto> education
) {

    /** Mirrors the ML service's {@code ExperienceEntry}. */
    public record ExperienceEntryDto(String title, String organization, String duration, String description) {}

    /** Mirrors the ML service's {@code EducationEntry}. */
    public record EducationEntryDto(String degree, String institution, String year) {}
}
