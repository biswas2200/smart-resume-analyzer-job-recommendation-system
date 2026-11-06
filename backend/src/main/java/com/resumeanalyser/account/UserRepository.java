package com.resumeanalyser.account;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
import java.util.UUID;

/**
 * Database access for {@link User} accounts.
 * Spring Data JPA generates the implementation of this interface automatically;
 * the two extra methods below are resolved from their method names by that
 * same mechanism (no hand-written query code needed).
 */
public interface UserRepository extends JpaRepository<User, UUID> {

    /**
     * Looks up an account by its login email.
     *
     * @param email the email to search for
     * @return the matching user, or empty if no account has that email
     */
    Optional<User> findByEmail(String email);

    /**
     * Checks whether an account with the given email already exists.
     * Used at registration time to reject duplicate sign-ups.
     *
     * @param email the email to check
     * @return true if an account with that email already exists
     */
    boolean existsByEmail(String email);
}
