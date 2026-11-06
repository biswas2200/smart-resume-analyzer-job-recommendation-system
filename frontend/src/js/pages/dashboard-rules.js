// The dashboard's decision logic, kept free of the DOM so tests/dashboard-rules.test.js can
// cover every lock-reason combination under Node. `dashboard` is the
// `GET /recommendations/dashboard` body (recommendation.dto.DashboardResponse).

/** Matches the backend's `JdMatchRequest` size cap. */
export const JD_MAX_CHARS = 20_000;

export function asPercent(score) {
  return Math.round(score * 100);
}

/**
 * Whether the explanation is the AI-written narrative rather than the deterministic
 * template — an absent `explanationSource` counts as template, matching the
 * backend's own default.
 */
export function isLlmExplanation(dashboard) {
  return dashboard.explanationSource === 'llm';
}

/** Recommendations were withheld because the domain needs the AI engine and this analysis could not use it. */
export function isLocked(dashboard) {
  return dashboard.recommendationsLocked === true;
}

export function isCommunityEdition(dashboard) {
  return dashboard.lockReason === 'community_edition';
}

export function isBudgetExhausted(dashboard) {
  return dashboard.lockReason === 'ai_budget_exhausted';
}

/**
 * A locked result the account can unlock right now by re-analysing. Never in the Community
 * Edition, where there is no AI engine to re-analyse with.
 */
export function canUnlock(dashboard) {
  return isLocked(dashboard) && !!dashboard.resumeId && !isCommunityEdition(dashboard);
}

export function engineLabel(domain) {
  return domain.engine === 'local' ? 'Local engine' : 'AI engine';
}

export function confidencePercent(domain) {
  return Math.round(domain.confidence * 100);
}

/** The JD form is only offered where it can work: an analysed resume. */
export function canMatchJd(dashboard) {
  return !!dashboard.resumeId;
}

/**
 * The job-market demand (`GET /jobs/in-demand`) for one role match, or null when there is
 * nothing worth showing: the role wasn't measured, too few open jobs to say (jobCount 0), or
 * no skills. Roles are matched by title, which is how the backend keys them.
 */
export function demandFor(inDemand, roleTitle) {
  const role = (inDemand?.roles ?? []).find((entry) => entry.role === roleTitle);
  if (!role || !role.jobCount || !(role.skills ?? []).length) {
    return null;
  }
  return role;
}

/** "Python · 62%": a skill and the share of the role's open jobs asking for it. */
export function demandChipLabel(skill) {
  return `${skill.skill} · ${Math.round((skill.share ?? 0) * 100)}%`;
}

/** "What 14 open jobs for this role ask for" (one job reads "1 open job asks"). */
export function demandHeading(jobCount) {
  return jobCount === 1 ? 'What 1 open job for this role asks for' : `What ${jobCount} open jobs for this role ask for`;
}
