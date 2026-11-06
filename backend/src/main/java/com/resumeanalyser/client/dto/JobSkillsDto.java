package com.resumeanalyser.client.dto;

import java.util.List;

/**
 * The ML service's job skill extraction ({@code POST /extract-job-skills}),
 * both ways: a request carries each posting's text, a response its skills.
 */
public final class JobSkillsDto {

    private JobSkillsDto() {}

    public record JobText(String id, String title, String text) {}

    public record Request(List<JobText> jobs) {}

    public record JobSkills(String id, List<String> skills) {}

    public record Response(List<JobSkills> jobs) {}
}
