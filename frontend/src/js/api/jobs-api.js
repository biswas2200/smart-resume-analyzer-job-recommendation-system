import { del, get, put } from '../core/http.js';
import { jobsQuery } from '../pages/jobs-rules.js';

// Backed by com.resumeanalyser.job.JobController.

/**
 * Open jobs ranked for the signed-in user's latest resume, best first. Resolves to
 * `{ resumeId, resumeVersion, roles, openJobs, jobs: [{ job, score, coverage, matchedSkills,
 * missingSkills, closestRole, why, savedStatus }] }`. With no resume, `resumeId` is null and
 * the jobs come newest first, unranked.
 */
export function getRecommended(filters = {}) {
  return get(jobsQuery(filters));
}

/**
 * What open jobs ask for in the user's top role matches: `{ roles: [{ role, jobCount,
 * computedAt, skills: [{ skill, share, have }] }] }`, most-asked skills first. `jobCount` 0
 * means too few jobs to say; `roles` is empty before the first resume.
 */
export function getInDemand() {
  return get('/jobs/in-demand');
}

/** The user's saved jobs, newest first: `[{ job, status, savedAt, updatedAt }]`. */
export function getSaved() {
  return get('/jobs/saved');
}

/**
 * Saves a job, or sets where its application stands. Without a status a new save starts at
 * SAVED and an existing one keeps its status. Resolves to the saved entry.
 */
export function saveJob(jobId, status) {
  return put(`/jobs/${encodeURIComponent(jobId)}/saved`, status ? { json: { status } } : {});
}

/** Removes a job from the saved list (the backend answers 204, even if it wasn't saved). */
export function unsaveJob(jobId) {
  return del(`/jobs/${encodeURIComponent(jobId)}/saved`);
}
