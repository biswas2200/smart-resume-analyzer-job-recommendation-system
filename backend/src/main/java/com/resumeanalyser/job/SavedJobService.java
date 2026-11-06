package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.job.dto.SavedJobDto;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Clock;
import java.util.List;
import java.util.UUID;

/** A user's saved jobs and the status they track for each. */
@Service
public class SavedJobService {

    private final SavedJobRepository saved;
    private final JobPostingRepository postings;
    private final Clock clock;

    public SavedJobService(SavedJobRepository saved, JobPostingRepository postings, Clock clock) {
        this.saved = saved;
        this.postings = postings;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<SavedJobDto> list(User user) {
        return saved.findByUserOrderBySavedAtDesc(user).stream().map(SavedJobDto::of).toList();
    }

    /**
     * Saves a job, or changes the status of one already saved.
     *
     * @param status null = SAVED for a new save, unchanged for an existing one
     * @throws ResourceNotFoundException if there is no such job
     */
    @Transactional
    public SavedJobDto save(User user, UUID jobId, SavedJobStatus status) {
        JobPosting posting = postings.findById(jobId)
                .orElseThrow(() -> new ResourceNotFoundException("No job with id " + jobId));
        SavedJob entry = saved.findByUserAndJobPosting(user, posting).orElseGet(() -> {
            SavedJob created = new SavedJob();
            created.setUser(user);
            created.setJobPosting(posting);
            created.setSavedAt(clock.instant());
            return created;
        });
        if (status != null) {
            entry.setStatus(status);
        }
        entry.setUpdatedAt(clock.instant());
        return SavedJobDto.of(saved.save(entry));
    }

    /** Removes a saved job; nothing happens if it wasn't saved. */
    @Transactional
    public void remove(User user, UUID jobId) {
        postings.findById(jobId).flatMap(posting -> saved.findByUserAndJobPosting(user, posting)).ifPresent(saved::delete);
    }
}
