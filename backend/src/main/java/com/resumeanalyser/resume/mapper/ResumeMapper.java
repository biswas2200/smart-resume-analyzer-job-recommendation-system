package com.resumeanalyser.resume.mapper;

import com.resumeanalyser.resume.Resume;
import com.resumeanalyser.resume.dto.ResumeDto;
import org.springframework.stereotype.Component;

/** Maps {@link Resume} entities to their public-facing {@link ResumeDto}. */
@Component
public class ResumeMapper {

    public ResumeDto toDto(Resume resume) {
        return new ResumeDto(
                resume.getId(),
                resume.getUser().getId(),
                resume.getFileRef(),
                resume.getVersion(),
                resume.getUploadedAt());
    }
}
