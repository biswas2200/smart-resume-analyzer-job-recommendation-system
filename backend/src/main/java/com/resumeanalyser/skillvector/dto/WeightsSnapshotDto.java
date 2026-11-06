package com.resumeanalyser.skillvector.dto;

import java.time.Instant;
import java.util.Map;

/**
 * The versioned, hashed export of every role's currently-active skill
 * weights (FR-7.5), consumed by the ML service as {@code weights_snapshot.json}
 * (see {@code ml-service/app/services/weights.py} and
 * docs/editions-and-parity.md §2).
 *
 * @param snapshotId this export's identifier (an ISO-8601 instant string)
 * @param createdAt  when this snapshot was assembled
 * @param sha256     a content hash of {@code weights}, so a downstream engine
 *                   can verify it received exactly this export
 * @param weights    every role's currently-active skill weights, keyed by
 *                    role title (matching the ML service's role_skills.json
 *                    role identifier) then skill
 */
public record WeightsSnapshotDto(
        String snapshotId,
        Instant createdAt,
        String sha256,
        Map<String, Map<String, Double>> weights
) {}
