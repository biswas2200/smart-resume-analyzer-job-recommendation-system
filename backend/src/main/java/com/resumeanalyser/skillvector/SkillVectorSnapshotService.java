package com.resumeanalyser.skillvector;

import com.resumeanalyser.skillvector.dto.WeightsSnapshotDto;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.Map;
import java.util.TreeMap;

/**
 * Builds the versioned, hashed weights snapshot (FR-7.5) the core engine
 * consumes as {@code weights_snapshot.json} -- see
 * docs/editions-and-parity.md §2 and docs/lld.md §7.4. Kept separate from
 * {@link SkillVectorService}, which only ever reasons about one role at a
 * time; this class's one job is collecting every role's currently-active
 * weights into the single exported document.
 */
@Service
public class SkillVectorSnapshotService {

    private final SkillVectorRepository skillVectorRepository;

    public SkillVectorSnapshotService(SkillVectorRepository skillVectorRepository) {
        this.skillVectorRepository = skillVectorRepository;
    }

    /**
     * @return every role's currently-active skill weights, keyed by role
     * title (matching the ML service's role_skills.json role identifier)
     * then skill, plus a snapshot id and a sha256 of the weights payload.
     * {@code TreeMap} at both levels guarantees deterministic key ordering,
     * so the hash (and the exported JSON) is stable across calls.
     */
    @Transactional(readOnly = true)
    public WeightsSnapshotDto exportSnapshot() {
        Map<String, Map<String, Double>> weights = new TreeMap<>();
        for (SkillVector vector : skillVectorRepository.findByCurrentTrue()) {
            weights.computeIfAbsent(vector.getRole().getTitle(), key -> new TreeMap<>())
                    .put(vector.getSkill(), vector.getWeight());
        }

        Instant createdAt = Instant.now();
        return new WeightsSnapshotDto(createdAt.toString(), createdAt, sha256Of(weights), weights);
    }

    private String sha256Of(Map<String, Map<String, Double>> weights) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(weights.toString().getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                hex.append(String.format("%02x", b));
            }
            return hex.toString();
        } catch (NoSuchAlgorithmException e) {
            // SHA-256 is a JDK-guaranteed MessageDigest algorithm -- this can
            // never actually be thrown at runtime.
            throw new IllegalStateException(e);
        }
    }
}
