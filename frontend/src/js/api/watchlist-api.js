import { del, get, post, put } from '../core/http.js';

// Backed by com.resumeanalyser.job.WatchlistController.

/**
 * The companies the signed-in user watches, newest first:
 * `[{ companyId, name, domain, status, careersUrl, openJobs, newJobs, addedAt }]`.
 */
export function getWatchlist() {
  return get('/watchlist');
}

/**
 * The limits every user has, and this user's use of the cap:
 * `{ maxCompanies, watching, changesPerMinute, changesPerHour }`. Going past them answers
 * 409 (cap) or 429 with Retry-After (too many changes), each with a message to show.
 */
export function getWatchlistLimits() {
  return get('/watchlist/limits');
}

/** Up to 20 companies whose name contains `query`: `[{ id, name, domain, status, watched }]`. */
export function searchCompanies(query) {
  return get(`/watchlist/companies?${new URLSearchParams({ q: (query ?? '').trim() })}`);
}

/**
 * One page of the whole company list, for the cards: `q` searches name and website, `filter` is
 * `all`, `hiring` (an open job now) or `watching`. Resolves to
 * `{ items: [{ id, name, domain, status, source, careersUrl, sector, area, fundingStage, teamSize, openJobs, watched }], page, size, total, hasMore }`; `sector` limits it to one sector.
 */
export function browseCompanies({ q = '', filter = 'all', sector = '', page = 0, size = 24 } = {}) {
  return get(`/watchlist/companies/browse?${new URLSearchParams({ q: q.trim(), filter, sector, page, size })}`);
}

/** The sectors in use with their company counts, biggest first: `[{ sector, companies }]`. */
export function getCompanySectors() {
  return get('/watchlist/companies/sectors');
}

/** Adds a company to the watchlist (adding it twice is fine). Resolves to the watchlist entry. */
export function watchCompany(companyId) {
  return put(`/watchlist/${encodeURIComponent(companyId)}`);
}

/**
 * Watches a company that isn't in our list yet, by its website (`{ name, website, careersUrl? }`);
 * the backend looks for its job tool straight away, so this takes a few seconds. Resolves to the
 * watchlist entry (201). Same 409/429 limits as watchCompany, plus 400 for a non-website.
 */
export function addCompany(body) {
  return post('/watchlist/companies', { json: body });
}

/** Removes a company from the watchlist (the backend answers 204, even if it wasn't there). */
export function unwatchCompany(companyId) {
  return del(`/watchlist/${encodeURIComponent(companyId)}`);
}
