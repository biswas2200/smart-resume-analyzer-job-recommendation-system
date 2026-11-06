package com.resumeanalyser.resume;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
import java.util.UUID;

/** Persistence for {@link ParsedProfile}. */
public interface ParsedProfileRepository extends JpaRepository<ParsedProfile, UUID> {

    /** The profile extracted from a given resume version, if it's been analyzed. */
    Optional<ParsedProfile> findByResume(Resume resume);
}
