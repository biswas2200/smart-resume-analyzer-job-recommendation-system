// What the Jobs and Saved jobs pages decide: the request for ranked jobs, how a match and a
// posting read, which links are safe to open, and how saved jobs group by application status.
// Pure functions of the `/jobs` responses, so tests/jobs-rules.test.js runs them under Node.

const WORKPLACES = ['onsite', 'hybrid', 'remote'];
const DAY_MS = 24 * 60 * 60 * 1000;

/** The tracking steps of a saved job (backend `SavedJobStatus`), in order. */
export const SAVED_STATUSES = [
  { value: 'SAVED', label: 'Saved' },
  { value: 'APPLIED', label: 'Applied' },
  { value: 'INTERVIEW', label: 'Interviewing' },
  { value: 'OFFER', label: 'Offer' },
  { value: 'REJECTED', label: 'Not selected' },
];

/**
 * The path for `GET /jobs/recommended` with only the filters that are set. An unknown
 * workplace value is dropped rather than sent, so the backend never gets a filter it ignores.
 */
export function jobsQuery({ q, workplace, limit = 50 } = {}) {
  const params = new URLSearchParams();
  const words = (q ?? '').trim();
  if (words) {
    params.set('q', words);
  }
  if (WORKPLACES.includes(workplace)) {
    params.set('workplace', workplace);
  }
  params.set('limit', String(limit));
  return `/jobs/recommended?${params}`;
}

/** The job's 0..1 score as a whole percent and a plain label. */
export function matchBand(score) {
  const percent = Math.round((score ?? 0) * 100);
  const label = percent >= 75 ? 'Strong match' : percent >= 50 ? 'Good match' : 'Partial match';
  return { percent, label };
}

/** "Remote", "Hybrid" or "On-site" from however a job feed spells it, or null when unknown. */
export function workplaceLabel(raw) {
  const value = (raw ?? '').toLowerCase();
  if (value.includes('remote')) {
    return 'Remote';
  }
  if (value.includes('hybrid')) {
    return 'Hybrid';
  }
  if (/on-?site|office/.test(value)) {
    return 'On-site';
  }
  return null;
}

/**
 * One location for the card. A posting that names several (the backend joins them with " · ")
 * usually lists the same city more than once, so this picks the first that gives a city and
 * region ("Bangalore, Karnataka, India" over "Bangalore" or "India"), else the first. The full
 * list stays available as a tooltip. Null when blank.
 */
export function locationLabel(raw) {
  const parts = (raw ?? '').split(/\s+·\s+|;/).map((part) => part.trim()).filter(Boolean);
  if (parts.length === 0) {
    return null;
  }
  return parts.find((part) => part.includes(',')) ?? parts[0];
}

/**
 * The job type in one readable form ("full-time", "FullTime" and "Full Time" are all
 * "Full-time"); anything else is shown as the feed wrote it, capitalised. Null when blank.
 */
export function employmentLabel(raw) {
  const value = (raw ?? '').trim();
  if (!value) {
    return null;
  }
  const key = value.toLowerCase().replace(/[^a-z]/g, '');
  const known = { fulltime: 'Full-time', parttime: 'Part-time', intern: 'Internship', internship: 'Internship', contract: 'Contract', temporary: 'Temporary' };
  return known[key] ?? value.charAt(0).toUpperCase() + value.slice(1);
}

/**
 * How long ago the job was posted: its publish date, or when we first saw it in the feed when
 * the feed gives none. Null when neither is known.
 */
export function postedLabel(job, now = new Date()) {
  const when = job.publishedAt ?? job.firstSeenAt;
  if (!when) {
    return null;
  }
  const days = Math.floor((startOfDay(now) - startOfDay(new Date(when))) / DAY_MS);
  if (days <= 0) {
    return 'Posted today';
  }
  if (days === 1) {
    return 'Posted yesterday';
  }
  if (days < 7) {
    return `Posted ${days} days ago`;
  }
  if (days < 31) {
    const weeks = Math.floor(days / 7);
    return `Posted ${weeks} week${weeks === 1 ? '' : 's'} ago`;
  }
  return 'Posted over a month ago';
}

function startOfDay(date) {
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

/**
 * A link from a job feed, only if it is plain http(s). Feeds are third-party data, so a
 * `javascript:` or `data:` URL must never become a clickable link.
 */
export function safeLink(url) {
  const value = (url ?? '').trim();
  return /^https?:\/\//i.test(value) ? value : null;
}

/** A status's label, or a readable form of a value this page doesn't know yet. */
export function statusLabel(value) {
  const known = SAVED_STATUSES.find((s) => s.value === value);
  if (known) {
    return known.label;
  }
  const words = String(value ?? '').toLowerCase().replaceAll('_', ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Saved jobs grouped by status in tracking order, the most recently changed first in each
 * group. Every status gets a group, empty or not, so the board's columns never move.
 */
export function groupSaved(saved) {
  return SAVED_STATUSES.map(({ value, label }) => ({
    status: value,
    label,
    items: saved
      .filter((item) => item.status === value)
      .sort((a, b) => String(b.updatedAt).localeCompare(String(a.updatedAt))),
  }));
}

/**
 * Why the recommended list is empty: no open jobs at all, or none left after the filters.
 * Null when there are jobs to show.
 */
export function emptyState(response) {
  if (!response.openJobs) {
    return 'no-open-jobs';
  }
  return response.jobs.length === 0 ? 'no-results' : null;
}

/**
 * Whether the jobs were ranked for a resume. Without one the backend still returns the open
 * jobs, newest first with a score of 0, so the page shows them with an upload prompt instead
 * of match percentages.
 */
export function isRanked(response) {
  return Boolean(response.resumeId);
}

/** How long a job counts as new: the same 7 days the watchlist's "N new" uses (backend `WatchlistService.NEW_FOR`). */
export const NEW_FOR_DAYS = 7;

/**
 * Whether the card gets a New badge: an open job we first saw in its feed within the last
 * NEW_FOR_DAYS. Uses firstSeenAt, not publishedAt, so a job a company backdated still counts
 * as new to us, matching the watchlist's count.
 */
export function isNewJob(job, now = new Date()) {
  if (!job?.active || !job.firstSeenAt) {
    return false;
  }
  const age = now - new Date(job.firstSeenAt);
  return age >= 0 && age < NEW_FOR_DAYS * DAY_MS;
}
