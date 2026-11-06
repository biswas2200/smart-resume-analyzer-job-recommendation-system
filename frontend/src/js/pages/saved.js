import { getSaved, saveJob, unsaveJob } from '../api/jobs-api.js';
import { extractApiErrorMessage } from '../core/api-error.js';
import { byId, cloneTemplate, el, field, setText, show } from '../core/dom.js';
import { requireAuth } from '../core/session.js';
import { hydrateIcons } from '../components/icons.js';
import { renderShell } from '../components/shell.js';
import { SAVED_STATUSES, groupSaved, locationLabel, postedLabel, safeLink, workplaceLabel } from './jobs-rules.js';

// Saved jobs, grouped by where each application stands (Saved → Applied → Interviewing →
// Offer, or Not selected). Changing a job's status moves it to that group; Remove drops it.
// A job the company has since closed stays, marked as closed.

let saved = [];

if (requireAuth()) {
  hydrateIcons();
  renderShell('saved');
  byId('retry-button').addEventListener('click', load);
  load();
}

async function load() {
  showStatus('loading');
  try {
    saved = await getSaved();
    render();
  } catch (error) {
    showStatus('error', extractApiErrorMessage(error, 'Please check your connection and try again.'));
  }
}

function showStatus(state, message) {
  show(byId('status-loading'), state === 'loading');
  show(byId('status-error'), state === 'error');
  show(byId('status-empty'), state === 'empty');
  show(byId('board'), state === 'ready');
  if (message) {
    setText(byId('load-error'), message);
  }
}

function render() {
  if (saved.length === 0) {
    showStatus('empty');
    return;
  }
  showStatus('ready');
  byId('board').replaceChildren(...groupSaved(saved).map(renderGroup));
}

function renderGroup(group) {
  const section = cloneTemplate('saved-group-template');
  setText(field(section, 'label'), group.label);
  setText(field(section, 'count'), String(group.items.length));
  field(section, 'items').replaceChildren(...group.items.map(renderItem));
  show(field(section, 'none'), group.items.length === 0);
  return section;
}

function renderItem(item) {
  const { job } = item;
  const card = cloneTemplate('saved-job-template');
  setText(field(card, 'title'), job.title);
  setText(field(card, 'company'), job.company);
  setText(
    field(card, 'meta'),
    [locationLabel(job.location), workplaceLabel(job.workplaceType), postedLabel(job)].filter(Boolean).join(' · '),
  );
  field(card, 'meta').title = job.location ?? '';
  show(field(card, 'closed'), job.active === false);

  const select = field(card, 'status');
  const selectId = `status-${job.id}`;
  select.id = selectId;
  field(card, 'status-label').setAttribute('for', selectId);
  select.replaceChildren(
    ...SAVED_STATUSES.map(({ value, label }) => el('option', { value, selected: value === item.status }, label)),
  );
  select.addEventListener('change', () => changeStatus(item, select, card));

  const view = field(card, 'view');
  const href = safeLink(job.url);
  show(view, Boolean(href));
  if (href) {
    view.href = href;
  }

  field(card, 'remove').addEventListener('click', () => remove(item, card));
  hydrateIcons(card);
  return card;
}

async function changeStatus(item, select, card) {
  select.disabled = true;
  try {
    const updated = await saveJob(item.job.id, select.value);
    saved = saved.map((s) => (s.job.id === item.job.id ? updated : s));
    render();
  } catch (error) {
    select.value = item.status;
    select.disabled = false;
    showError(card, extractApiErrorMessage(error, 'Could not change the status. Please try again.'));
  }
}

async function remove(item, card) {
  const button = field(card, 'remove');
  button.disabled = true;
  try {
    await unsaveJob(item.job.id);
    saved = saved.filter((s) => s.job.id !== item.job.id);
    render();
  } catch (error) {
    button.disabled = false;
    showError(card, extractApiErrorMessage(error, 'Could not remove this job. Please try again.'));
  }
}

function showError(card, message) {
  const line = field(card, 'error');
  setText(line, message);
  show(line, true);
}
