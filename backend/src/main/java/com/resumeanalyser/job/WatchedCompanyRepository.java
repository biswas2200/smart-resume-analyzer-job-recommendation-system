package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Persistence for {@link WatchedCompany}. */
public interface WatchedCompanyRepository extends JpaRepository<WatchedCompany, UUID> {

    /** A user's watchlist, newest first, with each company loaded. */
    @EntityGraph(attributePaths = "company")
    List<WatchedCompany> findByUserOrderByAddedAtDesc(User user);

    Optional<WatchedCompany> findByUserAndCompany(User user, Company company);

    long countByUser(User user);
}
