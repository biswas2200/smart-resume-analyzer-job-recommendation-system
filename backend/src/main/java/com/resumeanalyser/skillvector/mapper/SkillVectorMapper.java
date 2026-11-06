package com.resumeanalyser.skillvector.mapper;

import com.resumeanalyser.skillvector.SkillVector;
import com.resumeanalyser.skillvector.dto.SkillVectorDto;
import org.springframework.stereotype.Component;

/** Converts a {@link SkillVector} entity into its public-facing {@link SkillVectorDto}. */
@Component
public class SkillVectorMapper {

    /**
     * @param skillVector the entity to convert
     * @return the equivalent DTO
     */
    public SkillVectorDto toDto(SkillVector skillVector) {
        return new SkillVectorDto(
                skillVector.getId(),
                skillVector.getRole().getId(),
                skillVector.getSkill(),
                skillVector.getWeight(),
                skillVector.getVersionTimestamp(),
                skillVector.isCurrent());
    }
}
