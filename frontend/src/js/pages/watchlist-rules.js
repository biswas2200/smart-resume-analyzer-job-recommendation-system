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

// ---- The company cards (the browsable list) ----

/** The directory's filters, as `[value sent to the backend, label]`. */
export const DIRECTORY_FILTERS = [
  ['all', 'All companies'],
  ['hiring', 'Hiring now'],
  ['watching', 'Watching'],
];

/** One or two capital letters to stand in for a logo: "Groww" -> "G", "Meesho Pvt Ltd" -> "MP". */
export function companyInitials(name) {
  const words = (name ?? '').replace(/[^\p{L}\p{N} ]/gu, ' ').split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return '?';
  }
  return (words.length === 1 ? words[0][0] : words[0][0] + words[1][0]).toUpperCase();
}

/** A stable 0-5 for a company name, so a company keeps the same avatar colour. */
export function avatarTone(name) {
  let hash = 0;
  for (const char of name ?? '') {
    hash = (hash * 31 + char.codePointAt(0)) % 997;
  }
  return hash % 6;
}

/**
 * What a company card says about its jobs, as a badge `{ label, tone }`. Open jobs win over the
 * tracking status: "Hiring now" is what a candidate wants to know.
 */
export function cardStatusBadge(company) {
  if (company.openJobs > 0) {
    return { label: 'Hiring now', tone: 'green' };
  }
  switch (company.status) {
    case 'ACTIVE':
      return { label: 'No open jobs right now', tone: '' };
    case 'UNSUPPORTED':
      return company.careersUrl
        ? { label: 'Careers page only', tone: 'amber' }
        : { label: "Jobs not tracked yet", tone: 'amber' };
    default:
      return { label: 'Checking for jobs', tone: '' };
  }
}

/** "Indiranagar · 51-200 people · Series A": what the map says about a company, leaving out what it doesn't. */
export function cardFacts(company) {
  return [company.area, company.teamSize ? `${company.teamSize} people` : '', company.fundingStage]
    .map((part) => (part ?? '').trim())
    .filter(Boolean)
    .join(' · ');
}

/** "SaaS (166)" for the sector filter's options. */
export function sectorOptionLabel({ sector, companies }) {
  return `${sector} (${companies})`;
}

/** The address of a company's website from its domain ("groww.in" -> "https://groww.in"), or null. */
export function websiteUrl(domain) {
  const value = (domain ?? '').trim();
  return value && !/\s/.test(value) && value.includes('.') ? `https://${value}` : null;
}

/**
 * A link to a company's hiring board instead of one posting on it: the startup map's Apply links
 * point at a single job ("jobs.lever.co/acme/1c9f..."), which may be closed by the time someone
 * clicks. Lever, Ashby and Greenhouse links are cut back to the board ("jobs.lever.co/acme");
 * any other link is returned as it is.
 */
export function boardLink(url) {
  try {
    const link = new URL(url);
    const host = link.hostname.replace(/^www\./, '');
    const slug = link.pathname.split('/').filter(Boolean)[0];
    if (slug && ['jobs.lever.co', 'jobs.ashbyhq.com', 'boards.greenhouse.io', 'job-boards.greenhouse.io'].includes(host)) {
      return `${link.protocol}//${link.hostname}/${slug}`;
    }
  } catch {
    // Not a URL; the caller's link check handles it.
  }
  return url;
}

/**
 * The Apply button of a company card:
 * - open jobs we track: a link to those jobs on the Jobs page (`jobs.html?q=<company>`), internal;
 * - else its careers page (the hiring tool's link we found), external;
 * - else its website, external; or null when there is nothing to open.
 * `safe` is the link checker (http and https only) so no `javascript:` link ever reaches an href.
 */
export function applyAction(company, safe = (url) => (/^https?:\/\//i.test((url ?? '').trim()) ? url.trim() : null)) {
  if (company.openJobs > 0) {
    return {
      kind: 'jobs',
      label: company.openJobs === 1 ? 'View 1 job' : `View ${company.openJobs} jobs`,
      href: `jobs.html?${new URLSearchParams({ q: company.name })}`,
    };
  }
  const careers = safe(company.careersUrl);
  if (careers) {
    return { kind: 'external', label: 'Careers page', href: boardLink(careers) };
  }
  const site = websiteUrl(company.domain);
  return site ? { kind: 'external', label: 'Visit website', href: site } : null;
}

/** "Showing 24 of 1,085 companies", or "No companies match" when the list is empty. */
export function resultsLabel(shown, total) {
  if (!total) {
    return 'No companies match';
  }
  return `Showing ${shown.toLocaleString('en-US')} of ${total.toLocaleString('en-US')} ${total === 1 ? 'company' : 'companies'}`;
}

/** A filter value this page knows, else "all" (a hand-edited address must not break the list). */
export function normalizeFilter(value) {
  return DIRECTORY_FILTERS.some(([known]) => known === value) ? value : 'all';
}
