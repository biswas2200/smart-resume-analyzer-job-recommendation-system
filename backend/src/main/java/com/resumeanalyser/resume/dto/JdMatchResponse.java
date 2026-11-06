package com.resumeanalyser.resume.dto;

import java.util.List;
import java.util.UUID;

/**
 * Result of matching one resume version against a pasted job description
 * (FR-8.2): a 0-1 score, its two components, and the JD's recognised skills
 * split into what the resume already has and what it lacks.
 *
 * @param resumeId      the resume version that was matched
 * @param score         {@code 0.6 * coverage + 0.4 * similarity}, 2 dp
 * @param coverage      share of the JD's recognised skills the resume has exactly
 * @param similarity    cosine similarity of the two skill sets' embeddings
 * @param jdSkills      every skill recognised in the JD, in order of appearance
 * @param matchedSkills the JD skills the resume has
 * @param missingSkills the JD skills the resume lacks -- the actionable list
 * @param closestRole   the catalogue role the JD most resembles, or null
 * @param explanation   deterministic prose over the lists above
 */
public record JdMatchResponse(
        UUID resumeId,
        double score,
        double coverage,
        double similarity,
        List<String> jdSkills,
        List<String> matchedSkills,
        List<String> missingSkills,
        ClosestRole closestRole,
        String explanation
) {
    /** The role the JD reads like, with how well the JD itself fits that role's skill profile. */
    public record ClosestRole(String title, String description, String domain, double score) {}
}
