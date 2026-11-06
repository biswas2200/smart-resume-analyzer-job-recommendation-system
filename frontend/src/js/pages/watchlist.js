import {
  addCompany,
  browseCompanies,
  getWatchlist,
  getWatchlistLimits,
  unwatchCompany,
  watchCompany,
} from '../api/watchlist-api.js';
import { extractApiErrorMessage } from '../core/api-error.js';
import { byId, cloneTemplate, el, field, setBusy, setText, show } from '../core/dom.js';
import { requireAuth } from '../core/session.js';
import { hydrateIcons, icon } from '../components/icons.js';
import { renderShell } from '../components/shell.js';
import { safeLink } from './jobs-rules.js';
import {
  DIRECTORY_FILTERS,
  addCompanyRequest,
  addedMessage,
  applyAction,
  avatarTone,
  capLabel,
  cardStatusBadge,
  companyInitials,
  companyStatusBadge,
  isFull,
  newJobsLabel,
  normalizeFilter,
  openJobsLabel,
  resultsLabel,
  websiteUrl,
} from './watchlist-rules.js';

// The companies page: every company we know as a grid of cards (search it, filter it to the ones
// hiring now or the ones you watch), with Watch and Apply on each card, above the list of the
// companies you watch (how many of their jobs are open and how many are new this week). Every
// user may watch up to `maxCompanies`; the backend also limits how fast the list changes, and its
// 409/429 messages are shown as-is.

const PAGE_SIZE = 24;
const SEARCH_DELAY_MS = 300;

let watched = [];
// From GET /watchlist/limits; null if that call failed (the backend still enforces the cap).
let maxCompanies = null;
// The browsable list as last loaded; `generation` makes an answer to an old search harmless.
const directory = { q: '', filter: 'all', page: 0, total: 0, hasMore: false, shown: 0, loading: false, generation: 0 };
// Each card on screen: company id -> { company, button }, so a change can repaint its Watch button.
const cards = new Map();
let searchTimer = null;

if (requireAuth()) {
  hydrateIcons();
  renderShell('watchlist');
  directory.filter = normalizeFilter(new URLSearchParams(location.search).get('filter'));
  byId('retry-button').addEventListener('click', load);
  byId('search-form').addEventListener('submit', (event) => {
    event.preventDefault();
    window.clearTimeout(searchTimer);
    searchDirectory();
  });
  byId('company-query').addEventListener('input', () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(searchDirectory, SEARCH_DELAY_MS);
  });
  byId('load-more').addEventListener('click', () => loadDirectory(false));
  byId('directory-retry').addEventListener('click', () => loadDirectory(directory.page === 0));
  byId('add-form').addEventListener('submit', (event) => {
    event.preventDefault();
    add();
  });
  renderFilters();
  load();
  loadDirectory(true);
}

// ---------- The companies you watch ----------

async function load() {
  showStatus('loading');
  try {
    const [list, limits] = await Promise.all([getWatchlist(), getWatchlistLimits().catch(() => null)]);
    watched = list;
    maxCompanies = limits?.maxCompanies ?? null;
    render();
  } catch (error) {
    showStatus('error', extractApiErrorMessage(error, 'Please check your connection and try again.'));
  }
}

function showStatus(state, message) {
  show(byId('status-loading'), state === 'loading');
  show(byId('status-error'), state === 'error');
  show(byId('status-empty'), state === 'empty');
  show(byId('watchlist'), state === 'ready');
  if (message) {
    setText(byId('load-error'), message);
  }
}

function render() {
  paintCap();
  setText(byId('watching-count'), watched.length ? String(watched.length) : '');
  if (watched.length === 0) {
    showStatus('empty');
    return;
  }
  showStatus('ready');
  byId('watchlist').replaceChildren(...watched.map(renderItem));
}

function renderItem(item) {
  const card = cloneTemplate('watched-template');
  setText(field(card, 'name'), item.name);
  setText(field(card, 'domain'), item.domain);

  const badge = companyStatusBadge(item.status);
  const status = field(card, 'status');
  setText(status, badge.label);
  status.className = `badge ${badge.tone ? `badge-${badge.tone}` : ''}`.trim();
  setBadge(field(card, 'open'), openJobsLabel(item.openJobs));
  setBadge(field(card, 'new'), newJobsLabel(item.newJobs));

  const careers = field(card, 'careers');
  const href = safeLink(item.careersUrl);
  show(careers, Boolean(href));
  if (href) {
    careers.href = href;
  }

  field(card, 'remove').addEventListener('click', () => remove(item, card));
  hydrateIcons(card);
  return card;
}

function setBadge(badge, label) {
  show(badge, Boolean(label));
  setText(badge, label ?? '');
}

async function remove(item, card) {
  const button = field(card, 'remove');
  button.disabled = true;
  try {
    await unwatchCompany(item.companyId);
    watched = watched.filter((w) => w.companyId !== item.companyId);
    render();
    dropFromWatchingFilter(item.companyId);
  } catch (error) {
    button.disabled = false;
    showError(card, extractApiErrorMessage(error, 'Could not stop watching this company. Please try again.'));
  }
}

/** The "3 of 25" line, and every Watch button repainted (turned off for the rest while the list is full). */
function paintCap() {
  const cap = byId('watch-cap');
  const label = capLabel(watched.length, maxCompanies);
  setText(cap, label ?? '');
  show(cap, Boolean(label));
  for (const { company, button } of cards.values()) {
    paintWatchButton(button, company);
  }
  paintAddButton();
}

// ---------- The company cards ----------

function renderFilters() {
  byId('filters').replaceChildren(
    ...DIRECTORY_FILTERS.map(([value, label]) => {
      const chip = el('button', { class: 'chip', type: 'button', 'aria-pressed': String(value === directory.filter) }, label);
      chip.addEventListener('click', () => {
        if (directory.filter === value) {
          return;
        }
        directory.filter = value;
        renderFilters();
        loadDirectory(true);
      });
      return chip;
    }),
  );
}

function searchDirectory() {
  const query = byId('company-query').value.trim();
  if (query === directory.q && directory.page > 0) {
    return;
  }
  directory.q = query;
  loadDirectory(true);
}

/** The first page (`reset`) or the next one of the current search and filter. */
async function loadDirectory(reset) {
  if (directory.loading && !reset) {
    return;
  }
  if (reset) {
    directory.generation += 1;
    directory.page = 0;
    directory.shown = 0;
    cards.clear();
    byId('company-grid').replaceChildren();
    show(byId('directory-empty'), false);
    setText(byId('results-label'), 'Loading…');
  }
  const generation = directory.generation;
  directory.loading = true;
  show(byId('directory-error'), false);
  setBusy(byId('load-more'), true, 'Loading…');
  try {
    const page = await browseCompanies({
      q: directory.q,
      filter: directory.filter,
      page: directory.page,
      size: PAGE_SIZE,
    });
    if (generation !== directory.generation) {
      return; // a newer search replaced this one while it was loading
    }
    byId('company-grid').append(...page.items.map(renderCard));
    directory.shown += page.items.length;
    directory.total = page.total;
    directory.hasMore = page.hasMore;
    directory.page = page.page + 1;
    paintDirectoryState();
  } catch (error) {
    if (generation !== directory.generation) {
      return;
    }
    setText(byId('directory-error-text'), extractApiErrorMessage(error, 'Please check your connection and try again.'));
    show(byId('directory-error'), true);
    setText(byId('results-label'), '');
    show(byId('load-more-row'), false);
  } finally {
    if (generation === directory.generation) {
      directory.loading = false;
      setBusy(byId('load-more'), false);
    }
  }
}

function paintDirectoryState() {
  setText(byId('results-label'), resultsLabel(directory.shown, directory.total));
  show(byId('load-more-row'), directory.hasMore);
  const empty = directory.total === 0;
  show(byId('directory-empty'), empty);
  if (empty) {
    const watching = directory.filter === 'watching';
    setText(byId('directory-empty-title'), watching ? "You're not watching any of these" : 'No companies match');
    setText(
      byId('directory-empty-text'),
      watching ? 'Press Watch on a company to follow it.' : 'Try a shorter name, or add the company below.',
    );
  }
}

function isWatched(companyId) {
  return watched.some((w) => w.companyId === companyId);
}

function renderCard(company) {
  const card = cloneTemplate('company-card-template');
  const avatar = field(card, 'avatar');
  setText(avatar, companyInitials(company.name));
  avatar.dataset.tone = String(avatarTone(company.name));
  setText(field(card, 'name'), company.name);

  const site = field(card, 'site');
  setText(site, company.domain);
  const siteHref = websiteUrl(company.domain);
  if (siteHref) {
    site.href = siteHref;
  } else {
    site.removeAttribute('href');
  }

  const badge = cardStatusBadge(company);
  const status = field(card, 'status');
  setText(status, badge.label);
  status.className = `badge ${badge.tone ? `badge-${badge.tone}` : ''}`.trim();

  const apply = field(card, 'apply');
  const action = applyAction(company, safeLink);
  show(apply, Boolean(action));
  if (action) {
    apply.replaceChildren(icon(action.kind === 'jobs' ? 'search' : 'external'), action.label);
    apply.href = action.href;
    if (action.kind === 'external') {
      apply.target = '_blank';
      apply.rel = 'noopener noreferrer';
    }
  }

  const button = field(card, 'watch');
  cards.set(company.id, { company, button });
  paintWatchButton(button, company);
  button.addEventListener('click', () => toggleWatch(company, button, card));
  hydrateIcons(card);
  return card;
}

function paintWatchButton(button, company) {
  const mine = isWatched(company.id);
  const full = isFull(watched.length, maxCompanies);
  button.disabled = !mine && full;
  button.title = mine ? 'Stop watching this company' : full ? `You can watch up to ${maxCompanies} companies` : '';
  button.setAttribute('aria-pressed', String(mine));
  button.replaceChildren(icon(mine ? 'check' : 'plus'), mine ? 'Watching' : 'Watch');
}

async function toggleWatch(company, button, card) {
  button.disabled = true;
  const wasWatched = isWatched(company.id);
  try {
    if (wasWatched) {
      await unwatchCompany(company.id);
      watched = watched.filter((w) => w.companyId !== company.id);
    } else {
      const entry = await watchCompany(company.id);
      watched = [entry, ...watched.filter((w) => w.companyId !== entry.companyId)];
    }
    render();
    if (wasWatched) {
      dropFromWatchingFilter(company.id);
    }
    hideCardError(card);
  } catch (error) {
    paintWatchButton(button, company);
    showError(card, extractApiErrorMessage(error, 'Could not update your watchlist. Please try again.'));
  }
}

/** On the "Watching" filter, a company you stopped watching leaves the grid. */
function dropFromWatchingFilter(companyId) {
  if (directory.filter !== 'watching') {
    return;
  }
  const entry = cards.get(companyId);
  if (!entry) {
    return;
  }
  entry.button.closest('.company-card')?.remove();
  cards.delete(companyId);
  directory.shown = Math.max(0, directory.shown - 1);
  directory.total = Math.max(0, directory.total - 1);
  paintDirectoryState();
}

// ---------- Add a company that is not in the list ----------

/** Adds a company that isn't in our list, by its website, and watches it. */
async function add() {
  const errorLine = byId('add-error');
  const note = byId('add-note');
  show(errorLine, false);
  show(note, false);
  const { body, error } = addCompanyRequest({
    name: byId('add-name').value,
    website: byId('add-website').value,
    careersUrl: byId('add-careers').value,
  });
  if (error) {
    setText(errorLine, error);
    show(errorLine, true);
    return;
  }
  const button = byId('add-submit');
  setBusy(button, true, 'Looking for its jobs…');
  try {
    const entry = await addCompany(body);
    watched = [entry, ...watched.filter((w) => w.companyId !== entry.companyId)];
    render();
    byId('add-form').reset();
    setText(note, addedMessage(entry));
    show(note, true);
    loadDirectory(true); // the new company is in the list now
  } catch (failure) {
    setText(errorLine, extractApiErrorMessage(failure, 'Could not add this company. Please try again.'));
    show(errorLine, true);
  } finally {
    setBusy(button, false);
    paintAddButton();
  }
}

/** The add form's button is off while the watchlist is full, like the Watch buttons. */
function paintAddButton() {
  const button = byId('add-submit');
  const full = isFull(watched.length, maxCompanies);
  button.disabled = full;
  button.title = full ? `You can watch up to ${maxCompanies} companies` : '';
}

function showError(card, message) {
  const line = field(card, 'error');
  setText(line, message);
  show(line, true);
}

function hideCardError(card) {
  show(field(card, 'error'), false);
}
