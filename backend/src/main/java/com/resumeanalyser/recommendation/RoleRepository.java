package com.resumeanalyser.recommendation;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
import java.util.UUID;

/** Persistence for {@link Role}. */
public interface RoleRepository extends JpaRepository<Role, UUID> {

    /** Looks up a curated role by its unique display title. */
    Optional<Role> findByTitle(String title);
}
