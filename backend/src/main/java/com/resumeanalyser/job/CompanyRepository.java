package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
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

    /**
     * The browsable company list: by name or website when {@code q} is not blank (already escaped for
     * LIKE with {@code \}), optionally only companies with an open job, optionally only the ones
     * {@code user} watches. Companies hiring now come first, then by name.
     */
    @Query("""
            select c from Company c
            where (:q = '' or lower(c.name) like concat('%', :q, '%') escape '\\'
                   or c.domain like concat('%', :q, '%') escape '\\')
              and (:hiringOnly = false
                   or exists (select 1 from JobPosting p where p.company = c and p.active = true))
              and (:watchingOnly = false
                   or exists (select 1 from WatchedCompany w where w.company = c and w.user = :user))
            order by case when exists (select 1 from JobPosting p2 where p2.company = c and p2.active = true)
                          then 0 else 1 end,
                     lower(c.name), c.id
            """)
    Page<Company> browse(@Param("q") String q, @Param("hiringOnly") boolean hiringOnly,
                         @Param("watchingOnly") boolean watchingOnly, @Param("user") User user, Pageable pageable);
}
