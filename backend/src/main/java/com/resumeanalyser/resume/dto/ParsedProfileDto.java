package com.resumeanalyser.resume.dto;

import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.UUID;

/**
 * Public-facing view of a {@link com.resumeanalyser.resume.ParsedProfile}.
 *
 * @param id         the profile's database identifier
 * @param resumeId   the id of the resume version this was extracted from
 * @param name       candidate's full name
 * @param email      contact email
 * @param phone      contact phone number
 * @param skills     raw, unnormalized skill names
 * @param experience work history entries
 * @param education  education entries
 */
public record ParsedProfileDto(
        UUID id,

        @NotNull
        UUID resumeId,

        String name,
        String email,
        String phone,
        List<String> skills,
        List<ExperienceEntryDto> experience,
        List<EducationEntryDto> education
) {

    /**
     * One entry in a candidate's work history.
     *
     * @param title        job title
     * @param organization employer name
     * @param duration     free-text duration as written on the resume
     * @param description  free-text description of the role
     */
    public record ExperienceEntryDto(String title, String organization, String duration, String description) {}

    /**
     * One entry in a candidate's education history.
     *
     * @param degree      degree name
     * @param institution school/university name
     * @param year        free-text graduation year
     */
    public record EducationEntryDto(String degree, String institution, String year) {}
}
