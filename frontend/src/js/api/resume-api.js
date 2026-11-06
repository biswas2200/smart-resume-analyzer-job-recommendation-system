import { get, post } from '../core/http.js';

// Backed by com.resumeanalyser.resume.ResumeController.

/**
 * Uploads a new resume version (`POST /resumes`, multipart field `file`). The backend analyses
 * it synchronously, so by the time this resolves the parsed profile and recommendations exist.
 * Resolves to a `ResumeDto`: `{ id, userId, fileRef, version, uploadedAt }`.
 */
export function upload(file) {
  const formData = new FormData();
  formData.append('file', file);
  return post('/resumes', { formData });
}

/** Every resume version uploaded by the current user, oldest first (FR-1.5). */
export function listVersions() {
  return get('/resumes');
}

/**
 * The structured profile extracted from one resume version (`ParsedProfileDto`):
 * `{ id, resumeId, name, email, phone, skills[], experience[], education[] }`.
 */
export function getParsedProfile(resumeId) {
  return get(`/resumes/${encodeURIComponent(resumeId)}/profile`);
}

/**
 * Re-runs the analysis of an existing resume version — how a result that was locked at upload
 * time (the AI engine was unavailable) is recovered. Nothing is re-uploaded.
 */
export function reanalyze(resumeId) {
  return post(`/resumes/${encodeURIComponent(resumeId)}/reanalyze`);
}

/**
 * Scores a resume version against a pasted job description (FR-8.1/8.2). Resolves to a
 * `JdMatchResponse`: `{ resumeId, score, coverage, similarity, jdSkills[], matchedSkills[],
 * missingSkills[], closestRole | null, explanation }`.
 */
export function matchJobDescription(resumeId, jdText) {
  return post(`/resumes/${encodeURIComponent(resumeId)}/jd-match`, { json: { jdText } });
}
