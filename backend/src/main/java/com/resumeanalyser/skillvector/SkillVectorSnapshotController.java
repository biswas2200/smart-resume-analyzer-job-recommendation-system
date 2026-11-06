package com.resumeanalyser.skillvector;

import com.resumeanalyser.skillvector.dto.WeightsSnapshotDto;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Exports the versioned weights snapshot every core-engine release consumes
 * (FR-7.5). Kept as its own controller rather than a method on
 * {@link SkillVectorController} since it isn't scoped to one role -- it's a
 * role-spanning, operational export, restricted to ADMIN for the same reason
 * {@link SkillVectorController#recompute} is.
 */
@RestController
public class SkillVectorSnapshotController {

    private final SkillVectorSnapshotService snapshotService;

    public SkillVectorSnapshotController(SkillVectorSnapshotService snapshotService) {
        this.snapshotService = snapshotService;
    }

    /**
     * @return every role's currently-active skill weights as a single,
     * hashed, versioned document (FR-7.5)
     */
    @GetMapping("/roles/skill-vectors/snapshot")
    @PreAuthorize("hasRole('ADMIN')")
    public WeightsSnapshotDto snapshot() {
        return snapshotService.exportSnapshot();
    }
}
