import { get } from '../core/http.js';

// Backed by com.resumeanalyser.recommendation.RecommendationController.

/**
 * Everything the dashboard renders for the candidate's most recent resume version
 * (`recommendation.dto.DashboardResponse`), or null when no resume has been uploaded yet.
 * Note `atsScore.max_score` is snake_case in the JSON — kept as-is.
 */
export function getDashboard() {
  return get('/recommendations/dashboard');
}
