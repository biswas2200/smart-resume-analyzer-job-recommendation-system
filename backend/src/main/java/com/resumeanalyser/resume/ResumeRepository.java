package com.resumeanalyser.resume;

import com.resumeanalyser.account.User;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Persistence for {@link Resume}. */
public interface ResumeRepository extends JpaRepository<Resume, UUID> {

    /** Every version a user has uploaded, oldest first (FR-1.5). */
    List<Resume> findByUserOrderByVersionAsc(User user);

    /** The most recently uploaded version for a user, if any. */
    Optional<Resume> findTopByUserOrderByVersionDesc(User user);

    /** How many versions a user has already uploaded, used to assign the next version number. */
    int countByUser(User user);
}
