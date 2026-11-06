package com.resumeanalyser.resume.mapper;

import com.resumeanalyser.resume.ParsedProfile;
import com.resumeanalyser.resume.dto.ParsedProfileDto;
import org.springframework.stereotype.Component;

/** Maps {@link ParsedProfile} entities to their public-facing {@link ParsedProfileDto}. */
@Component
public class ParsedProfileMapper {

    public ParsedProfileDto toDto(ParsedProfile profile) {
        return new ParsedProfileDto(
                profile.getId(),
                profile.getResume().getId(),
                profile.getName(),
                profile.getEmail(),
                profile.getPhone(),
                profile.getSkills(),
                profile.getExperience().stream()
                        .map(e -> new ParsedProfileDto.ExperienceEntryDto(
                                e.title(), e.organization(), e.duration(), e.description()))
                        .toList(),
                profile.getEducation().stream()
                        .map(e -> new ParsedProfileDto.EducationEntryDto(e.degree(), e.institution(), e.year()))
                        .toList());
    }
}
