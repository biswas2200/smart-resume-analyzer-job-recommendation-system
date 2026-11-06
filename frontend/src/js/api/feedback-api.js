import { get, post } from '../core/http.js';

// Backed by com.resumeanalyser.feedback.FeedbackController (FR-10.1).

/**
 * Records whether the candidate found a recommendation helpful. Resolves to a `FeedbackDto`:
 * `{ id, recommendationId, skillVectorVersionId, helpful, createdAt }`.
 */
export function submit(recommendationId, helpful) {
  return post('/feedback', { json: { recommendationId, helpful } });
}

/** The latest feedback for a recommendation, or null (the backend answers 204) if none yet. */
export function getFeedbackFor(recommendationId) {
  return get(`/feedback/${encodeURIComponent(recommendationId)}`);
}
