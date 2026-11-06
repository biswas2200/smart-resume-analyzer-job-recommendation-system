package com.resumeanalyser.job;

import com.resumeanalyser.client.dto.MarketDemandDto;
import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.recommendation.RoleRepository;
import com.resumeanalyser.skillvector.SkillVectorService;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;

/**
 * Stores one market-demand result in one transaction: replaces the demand
 * table, and feeds each role's signals into its EMA skill weights (FR-7.2),
 * so the table and the weights never disagree.
 */
@Component
public class MarketDemandStore {

    private final MarketSkillDemandRepository demand;
    private final RoleRepository roles;
    private final SkillVectorService skillVectors;

    public MarketDemandStore(MarketSkillDemandRepository demand, RoleRepository roles, SkillVectorService skillVectors) {
        this.demand = demand;
        this.roles = roles;
        this.skillVectors = skillVectors;
    }

    /** @return how many skill weights were updated */
    @Transactional
    public int store(MarketDemandDto.Response result, Instant computedAt) {
        demand.deleteAllRows();
        int weightsUpdated = 0;
        for (MarketDemandDto.RoleDemand role : result.roles()) {
            for (MarketDemandDto.SkillDemand skill : role.inDemand()) {
                MarketSkillDemand row = new MarketSkillDemand();
                row.setRoleTitle(role.role());
                row.setSkill(skill.skill());
                row.setShare(skill.share());
                row.setJobCount(role.jobCount());
                row.setComputedAt(computedAt);
                demand.save(row);
            }
            if (role.signals() != null && !role.signals().isEmpty()) {
                weightsUpdated += skillVectors.recomputeAll(roleNamed(role), role.signals()).size();
            }
        }
        return weightsUpdated;
    }

    private Role roleNamed(MarketDemandDto.RoleDemand demanded) {
        return roles.findByTitle(demanded.role()).orElseGet(() -> {
            Role created = new Role();
            created.setTitle(demanded.role());
            if (demanded.domain() != null && !demanded.domain().isBlank()) {
                created.setDomain(demanded.domain());
            }
            return roles.save(created);
        });
    }
}
