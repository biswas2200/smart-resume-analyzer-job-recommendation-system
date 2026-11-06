package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Persistence for {@link SavedJob}. */
public interface SavedJobRepository extends JpaRepository<SavedJob, UUID> {

    /** A user's saved jobs, newest first, with each job and its company loaded. */
    @EntityGraph(attributePaths = {"jobPosting", "jobPosting.company"})
    List<SavedJob> findByUserOrderBySavedAtDesc(User user);

    Optional<SavedJob> findByUserAndJobPosting(User user, JobPosting jobPosting);
}
