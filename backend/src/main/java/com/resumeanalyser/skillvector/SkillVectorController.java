package com.resumeanalyser.skillvector;

import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.feedback.FeedbackService;
import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.recommendation.RoleRepository;
import com.resumeanalyser.skillvector.dto.SkillVectorDto;
import com.resumeanalyser.skillvector.mapper.SkillVectorMapper;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;
import java.util.UUID;

/**
 * Exposes a role's EMA-weighted skill vectors (FR-7.1-FR-7.4). Reading them is
 * open to any authenticated user -- weights aren't sensitive, and the dashboard
 * may want to show "why" a match scored the way it did. Triggering a recompute
 * is restricted to ADMIN: it's an operational action (force the weights to
 * reflect accumulated feedback right now, rather than waiting for the
 * feedback-count threshold in {@link FeedbackService#submit}), not something
 * any candidate should be able to do to a shared, global resource.
 */
@RestController
@RequestMapping("/roles/{roleId}/skill-vectors")
public class SkillVectorController {

    private final SkillVectorService skillVectorService;
    private final FeedbackService feedbackService;
    private final RoleRepository roleRepository;
    private final SkillVectorMapper skillVectorMapper;

    public SkillVectorController(
            SkillVectorService skillVectorService,
            FeedbackService feedbackService,
            RoleRepository roleRepository,
            SkillVectorMapper skillVectorMapper
    ) {
        this.skillVectorService = skillVectorService;
        this.feedbackService = feedbackService;
        this.roleRepository = roleRepository;
        this.skillVectorMapper = skillVectorMapper;
    }

    /**
     * The role's currently-active skill weights.
     *
     * @param roleId the role to look up
     * @return one entry per skill the role currently has a vector for
     * @throws ResourceNotFoundException if no role has this id
     */
    @GetMapping
    public List<SkillVectorDto> list(@PathVariable UUID roleId) {
        Role role = findRole(roleId);
        return skillVectorService.getAllCurrent(role).stream().map(skillVectorMapper::toDto).toList();
    }

    /**
     * Forces an immediate EMA recompute of every skill this role has accumulated
     * feedback for, instead of waiting for the automatic feedback-count threshold.
     *
     * @param roleId the role to recompute
     * @return the freshly written, now-current skill vectors
     * @throws ResourceNotFoundException if no role has this id
     */
    @PostMapping("/recompute")
    @PreAuthorize("hasRole('ADMIN')")
    public List<SkillVectorDto> recompute(@PathVariable UUID roleId) {
        Role role = findRole(roleId);
        return feedbackService.recomputeSkillVectors(role).stream().map(skillVectorMapper::toDto).toList();
    }

    private Role findRole(UUID roleId) {
        return roleRepository.findById(roleId)
                .orElseThrow(() -> new ResourceNotFoundException("Role not found: " + roleId));
    }
}
