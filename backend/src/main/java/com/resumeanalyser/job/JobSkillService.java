package com.resumeanalyser.job;

import com.resumeanalyser.client.MlServiceClient;
import com.resumeanalyser.client.MlServiceException;
import com.resumeanalyser.client.dto.JobSkillsDto;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Fills in the skills each open posting asks for, by asking the ML service
 * in batches. Runs after every collection task, so a new or changed posting
 * is ready for ranking by the time anyone asks for recommendations.
 */
@Service
public class JobSkillService {

    private static final Logger log = LoggerFactory.getLogger(JobSkillService.class);
    /** Enough for tens of thousands of postings; stops a run that keeps failing to save. */
    private static final int MAX_BATCHES = 1_000;

    private final JobPostingRepository postings;
    private final MlServiceClient mlServiceClient;

    public JobSkillService(JobPostingRepository postings, MlServiceClient mlServiceClient) {
        this.postings = postings;
        this.mlServiceClient = mlServiceClient;
    }

    /** Re-extracts every posting's skills -- after the ML service's extractor changed. */
    public String reextractAll() {
        int cleared = postings.clearAllSkills();
        return cleared + " jobs cleared; " + extractMissing();
    }

    /** @return a one-line summary of what was extracted (or why it stopped) */
    public String extractMissing() {
        int done = 0;
        try {
            for (int batch = 0; batch < MAX_BATCHES; batch++) {
                List<JobPosting> pending = postings.findTop50ByActiveTrueAndSkillsIsNullOrderByFirstSeenAtAsc();
                if (pending.isEmpty()) {
                    break;
                }
                List<JobSkillsDto.JobText> texts = pending.stream()
                        .map(p -> new JobSkillsDto.JobText(p.getId().toString(), p.getTitle(), p.getDescription()))
                        .toList();
                JobSkillsDto.Response response = mlServiceClient.extractJobSkills(texts);
                Map<String, List<String>> skillsById = response == null || response.jobs() == null ? Map.of()
                        : response.jobs().stream().collect(Collectors.toMap(
                                JobSkillsDto.JobSkills::id, JobSkillsDto.JobSkills::skills, (a, b) -> a, HashMap::new));
                for (JobPosting posting : pending) {
                    posting.setSkills(skillsById.getOrDefault(posting.getId().toString(), List.of()));
                    postings.save(posting);
                }
                done += pending.size();
            }
        } catch (MlServiceException e) {
            log.warn("Job skill extraction stopped after {} postings: {}", done, e.getMessage());
            return "skills extracted for " + done + " jobs, then stopped: " + e.getMessage();
        }
        log.info("Job skills extracted for {} postings", done);
        return "skills extracted for " + done + " jobs";
    }
}
