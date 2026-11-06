package com.resumeanalyser.skillvector;

import com.resumeanalyser.recommendation.Role;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Owns the versioned, EMA-weighted skill-vector store (FR-7.1-FR-7.4): the
 * "temporal" half of the temporal recommendation system, as opposed to
 * {@code matcher.py}'s current implicit "every skill weighted equally"
 * assumption. Deliberately has no knowledge of {@code Feedback} -- computing
 * {@code new_signal} from accumulated feedback is {@code FeedbackService}'s
 * job (it already depends on this package via {@code Feedback.skillVectorVersion});
 * this class only knows how to read a weight, blend it with a signal, and
 * version the result. That keeps the dependency between the two modules
 * one-directional.
 */
@Service
public class SkillVectorService {

    /**
     * The weight a (role, skill) pair starts at before any EMA update has ever
     * touched it -- matches {@code matcher.py}'s current implicit "every skill
     * weighted equally" assumption (see docs/database-schema.md §4), so a
     * freshly matched skill doesn't silently start at 0 and get under-weighted
     * relative to skills that already have real feedback behind them.
     */
    static final double DEFAULT_WEIGHT = 1.0;

    private final SkillVectorRepository skillVectorRepository;
    private final double alpha;

    /**
     * @param skillVectorRepository persistence for {@link SkillVector}
     * @param alpha                 FR-7.2's smoothing factor ({@code app.skill-vector.alpha}) --
     *                              how much a fresh signal moves the weight vs. how much of the
     *                              old weight is retained; closer to 1 reacts faster, closer to 0 is more stable
     */
    public SkillVectorService(SkillVectorRepository skillVectorRepository, @Value("${app.skill-vector.alpha}") double alpha) {
        this.skillVectorRepository = skillVectorRepository;
        this.alpha = alpha;
    }

    /**
     * The active weight for one (role, skill) pair, initializing it at
     * {@link #DEFAULT_WEIGHT} the first time this pair is ever looked up.
     *
     * @param role  the role the skill belongs to
     * @param skill the canonical skill name
     * @return the current, active {@link SkillVector} row
     */
    public SkillVector getCurrent(Role role, String skill) {
        return skillVectorRepository.findByRoleAndSkillAndCurrentTrue(role, skill)
                .orElseGet(() -> initialize(role, skill));
    }

    /** Every currently-active skill weight for a role. */
    public List<SkillVector> getAllCurrent(Role role) {
        return skillVectorRepository.findByRoleAndCurrentTrue(role);
    }

    /**
     * Makes sure every one of a role's skills has a vector row, without
     * disturbing any that already exist. Called by {@code RecommendationService}
     * right after an analysis run, so a role's skills are visible (at the
     * default weight) even before any feedback has come in for them.
     *
     * @param role   the role the skills belong to
     * @param skills the skills to ensure exist; duplicates are ignored
     */
    public void ensureInitialized(Role role, Collection<String> skills) {
        new LinkedHashSet<>(skills).forEach(skill -> getCurrent(role, skill));
    }

    /**
     * The actual EMA update for one skill (FR-7.2): blends {@code newSignal}
     * with whatever the current weight is (or {@link #DEFAULT_WEIGHT} if this
     * skill has never been scored before), retires the prior version rather
     * than overwriting it, and writes the result as a new, current row (FR-7.4)
     * -- so the full weight history stays queryable for the trend reporting
     * FR-7.4 requires.
     *
     * @param role      the role the skill belongs to
     * @param skill     the skill being reweighted
     * @param newSignal the freshly computed signal in {@code [0.0, 1.0]}, e.g. a
     *                  helpful-feedback ratio (see {@code FeedbackService})
     * @return the newly written, now-current {@link SkillVector} row
     */
    @Transactional
    public SkillVector recompute(Role role, String skill, double newSignal) {
        Optional<SkillVector> priorVersion = skillVectorRepository.findByRoleAndSkillAndCurrentTrue(role, skill);
        double oldWeight = priorVersion.map(SkillVector::getWeight).orElse(DEFAULT_WEIGHT);
        double newWeight = alpha * newSignal + (1 - alpha) * oldWeight;

        priorVersion.ifPresent(version -> {
            version.setCurrent(false);
            skillVectorRepository.save(version);
        });

        SkillVector next = new SkillVector();
        next.setRole(role);
        next.setSkill(skill);
        next.setWeight(newWeight);
        next.setCurrent(true);
        return skillVectorRepository.save(next);
    }

    /**
     * Applies {@link #recompute} to every skill in {@code signalsBySkill} --
     * one role-wide EMA update pass, triggered either automatically once enough
     * feedback has accumulated, or manually via the admin recompute endpoint.
     *
     * @param role           the role being recomputed
     * @param signalsBySkill each skill's freshly computed signal, keyed by skill name
     * @return the newly written, now-current rows, one per entry in {@code signalsBySkill}
     */
    @Transactional
    public List<SkillVector> recomputeAll(Role role, Map<String, Double> signalsBySkill) {
        // Calling recompute(...) via "this" bypasses its own @Transactional (Spring
        // proxies can't intercept self-invocation) -- safe here only because this
        // method's own @Transactional already wraps the whole batch in one transaction.
        return signalsBySkill.entrySet().stream()
                .map(entry -> recompute(role, entry.getKey(), entry.getValue()))
                .toList();
    }

    private SkillVector initialize(Role role, String skill) {
        SkillVector vector = new SkillVector();
        vector.setRole(role);
        vector.setSkill(skill);
        vector.setWeight(DEFAULT_WEIGHT);
        vector.setCurrent(true);
        return skillVectorRepository.save(vector);
    }
}
