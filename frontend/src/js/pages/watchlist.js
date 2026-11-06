import {
  addCompany,
  getWatchlist,
  getWatchlistLimits,
  searchCompanies,
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
  addCompanyRequest,
  addedMessage,
  capLabel,
  companyStatusBadge,
  isFull,
  isSearchable,
  newJobsLabel,
  openJobsLabel,
} from './watchlist-rules.js';

// The companies the user watches for new jobs. Search finds a company in our list and Watch
// adds it; each card shows whether we can read its jobs, how many are open and how many are
// new this week. Stop watching drops it. Every user may watch up to `maxCompanies`; the
// backend also limits how fast the list changes, and its 409/429 messages are shown as-is.

let watched = [];
// From GET /watchlist/limits; null if that call failed (the backend still enforces the cap).
let maxCompanies = null;
// The Watch buttons in the current search results, by company id, so Stop watching can re-enable one.
const optionButtons = new Map();

if (requireAuth()) {
  hydrateIcons();
  renderShell('watchlist');
  byId('retry-button').addEventListener('click', load);
  byId('search-form').addEventListener('submit', (event) => {
    event.preventDefault();
    search();
  });
  byId('add-form').addEventListener('submit', (event) => {
    event.preventDefault();
    add();
  });
  load();
}

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
    const option = optionButtons.get(item.companyId);
    if (option) {
      paintOption(option, false);
    }
    render();
  } catch (error) {
    button.disabled = false;
    showError(card, extractApiErrorMessage(error, 'Could not stop watching this company. Please try again.'));
  }
}

async function search() {
  const query = byId('company-query').value;
  const results = byId('search-results');
  if (!isSearchable(query)) {
    showSearchNote('Type at least two letters of the company name.');
    return;
  }
  try {
    const options = await searchCompanies(query);
    optionButtons.clear();
    byId('search-list').replaceChildren(...options.map(renderOption));
    showSearchNote(options.length === 0 ? `No company in our list matches "${query.trim()}".` : null);
  } catch (error) {
    showSearchNote(extractApiErrorMessage(error, 'Could not search. Please try again.'));
  }
  show(results, true);
}

function showSearchNote(message) {
  const note = byId('search-note');
  setText(note, message ?? '');
  show(note, Boolean(message));
  if (message) {
    byId('search-list').replaceChildren();
    show(byId('search-results'), true);
  }
}

function renderOption(option) {
  const button = el('button', { class: 'btn btn-secondary btn-sm', type: 'button' });
  paintOption(button, option.watched);
  optionButtons.set(option.id, button);
  button.addEventListener('click', () => watch(option, button));
  return el(
    'li',
    { class: 'watch-option' },
    el('div', {}, el('p', { class: 'job-company' }, option.name), el('p', { class: 'job-meta muted' }, option.domain)),
    button,
  );
}

function paintOption(button, isWatched) {
  const full = isFull(watched.length, maxCompanies);
  button.disabled = isWatched || full;
  button.title = !isWatched && full ? `You can watch up to ${maxCompanies} companies` : '';
  button.replaceChildren(icon(isWatched ? 'check' : 'plus'), isWatched ? 'Watching' : 'Watch');
}

/** The "3 of 25" line, and the Watch buttons turned off while the list is full. */
function paintCap() {
  const cap = byId('watch-cap');
  const label = capLabel(watched.length, maxCompanies);
  setText(cap, label ?? '');
  show(cap, Boolean(label));
  for (const [companyId, button] of optionButtons) {
    paintOption(button, watched.some((w) => w.companyId === companyId));
  }
  paintAddButton();
}

async function watch(option, button) {
  button.disabled = true;
  try {
    const entry = await watchCompany(option.id);
    watched = [entry, ...watched.filter((w) => w.companyId !== entry.companyId)];
    paintOption(button, true);
    render();
  } catch (error) {
    button.disabled = false;
    showSearchNote(extractApiErrorMessage(error, 'Could not add this company. Please try again.'));
  }
}

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
