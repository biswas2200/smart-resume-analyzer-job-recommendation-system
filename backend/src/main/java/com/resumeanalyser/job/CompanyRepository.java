package com.resumeanalyser.job;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/** Persistence for {@link Company}. */
public interface CompanyRepository extends JpaRepository<Company, UUID> {

    Optional<Company> findByDomain(String domain);

    List<Company> findByStatusOrderByNameAsc(CompanyStatus status);

    long countByStatus(CompanyStatus status);

    /** Name search for the watchlist's company picker. */
    List<Company> findTop20ByNameContainingIgnoreCaseOrderByNameAsc(String name);
}
