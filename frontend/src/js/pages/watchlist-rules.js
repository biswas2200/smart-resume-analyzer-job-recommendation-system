// Pure helpers for the watchlist page, kept apart from the DOM so they can be unit-tested.

/** Whether we can read a company's jobs yet, as a badge `{ label, tone }`. */
export function companyStatusBadge(status) {
  switch (status) {
    case 'ACTIVE':
      return { label: 'Jobs tracked', tone: 'green' };
    case 'UNSUPPORTED':
      return { label: "Can't read its jobs yet", tone: 'amber' };
    default:
      return { label: 'Checking for jobs', tone: '' };
  }
}

/** "12 open jobs", "1 open job", or null when there are none to show. */
export function openJobsLabel(count) {
  if (!count) {
    return null;
  }
  return `${count} open job${count === 1 ? '' : 's'}`;
}

/** "3 new" for the New badge, or null when nothing is new. */
export function newJobsLabel(count) {
  return count ? `${count} new` : null;
}

/** Whether a search for these words is worth sending (two or more characters). */
export function isSearchable(query) {
  return (query ?? '').trim().length >= 2;
}

/** "3 of 25 companies watched", or null while the cap is unknown. */
export function capLabel(watching, maxCompanies) {
  if (!maxCompanies) {
    return null;
  }
  return `${watching} of ${maxCompanies} companies watched`;
}

/**
 * Checks the "add a company by its website" form and builds the request body for
 * `POST /watchlist/companies`. Resolves to `{ body }` or `{ error }` (a message to show).
 * The backend checks the website again; this only catches what is plainly wrong.
 */
export function addCompanyRequest({ name, website, careersUrl }) {
  const cleanName = (name ?? '').trim();
  const cleanWebsite = (website ?? '').trim();
  const cleanCareers = (careersUrl ?? '').trim();
  if (!cleanName) {
    return { error: "Enter the company's name." };
  }
  if (!cleanWebsite || /\s/.test(cleanWebsite) || !cleanWebsite.includes('.')) {
    return { error: 'Enter its website, e.g. acme.com' };
  }
  const body = { name: cleanName, website: cleanWebsite };
  if (cleanCareers) {
    body.careersUrl = cleanCareers;
  }
  return { body };
}

/** What to say after adding a company, from whether we could read its jobs. */
export function addedMessage(entry) {
  if (entry.status === 'ACTIVE') {
    return `Watching ${entry.name}. We found its jobs.`;
  }
  return `Watching ${entry.name}. We couldn't find its jobs on Lever, Greenhouse or Ashby yet; a careers page link helps.`;
}

/** Whether the watchlist is at its cap (never, while the cap is unknown). */
export function isFull(watching, maxCompanies) {
  return Boolean(maxCompanies) && watching >= maxCompanies;
}
