package com.resumeanalyser.job;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import java.util.List;
import java.util.UUID;

/** Persistence for {@link MarketSkillDemand}. */
public interface MarketSkillDemandRepository extends JpaRepository<MarketSkillDemand, UUID> {

    List<MarketSkillDemand> findByRoleTitleOrderByShareDescSkillAsc(String roleTitle);

    @Modifying
    @Query("delete from MarketSkillDemand")
    int deleteAllRows();
}
