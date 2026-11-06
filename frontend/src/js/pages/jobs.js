import { getRecommended, saveJob, unsaveJob } from '../api/jobs-api.js';
import { extractApiErrorMessage } from '../core/api-error.js';
import { byId, cloneTemplate, field, renderChips, setText, show } from '../core/dom.js';
import { requireAuth } from '../core/session.js';
import { hydrateIcons } from '../components/icons.js';
import { renderShell } from '../components/shell.js';
import {
  emptyState,
  employmentLabel,
  isNewJob,
  isRanked,
  locationLabel,
  matchBand,
  postedLabel,
  safeLink,
  workplaceLabel,
} from './jobs-rules.js';

// Jobs for you: open jobs in our city, ranked for the user's latest resume (or newest first
// when there is none), with search and a workplace filter. Each card says why it ranks where
// it does, links to the company's own posting, and can be saved for tracking (saved.html).
// Everything here comes from third-party job feeds, so it goes in as text and every link
// passes through safeLink().

const BAND_BADGE = { 'Strong match': 'badge-green', 'Good match': 'badge-blue', 'Partial match': '' };

if (requireAuth()) {
  hydrateIcons();
  renderShell('jobs');
  byId('filters').addEventListener('submit', (event) => {
    event.preventDefault();
    load();
  });
  byId('job-workplace').addEventListener('change', load);
  byId('retry-button').addEventListener('click', load);
  load();
}

async function load() {
  showStatus('loading');
  try {
    const response = await getRecommended({
      q: byId('job-query').value,
      workplace: byId('job-workplace').value,
    });
    render(response);
  } catch (error) {
    showStatus('error', extractApiErrorMessage(error, 'Please check your connection and try again.'));
  }
}

function showStatus(state, message) {
  show(byId('status-loading'), state === 'loading');
  show(byId('status-error'), state === 'error');
  show(byId('status-no-open-jobs'), state === 'no-open-jobs');
  show(byId('status-no-results'), state === 'no-results');
  if (state !== 'ready') {
    byId('jobs').replaceChildren();
    show(byId('summary'), false);
  }
  if (message) {
    setText(byId('load-error'), message);
  }
}

function render(response) {
  const ranked = isRanked(response);
  show(byId('no-resume-note'), !ranked);
  showStatus(emptyState(response) ?? 'ready');

  if (response.jobs.length > 0) {
    show(byId('summary'), true);
    setText(byId('summary-text'), summaryText(response, ranked));
    renderChips(byId('summary-roles'), ranked ? response.roles : []);
  }
  byId('jobs').replaceChildren(...response.jobs.map((item) => renderJob(item, ranked)));
}

function summaryText(response, ranked) {
  const shown = `${response.jobs.length} of ${response.openJobs} open jobs`;
  if (!ranked) {
    return `${shown}, newest first.`;
  }
  const ranking = `${shown}, ranked for your resume (version ${response.resumeVersion}).`;
  return response.roles?.length ? `${ranking} Matched roles:` : ranking;
}

function renderJob(item, ranked) {
  const { job } = item;
  const card = cloneTemplate('job-template');

  setText(field(card, 'title'), job.title);
  setText(field(card, 'company'), job.company);
  show(field(card, 'new'), isNewJob(job));
  const meta = [locationLabel(job.location), workplaceLabel(job.workplaceType), employmentLabel(job.employmentType), postedLabel(job)]
    .filter(Boolean)
    .join(' · ');
  setText(field(card, 'meta'), meta);
  field(card, 'meta').title = job.location ?? '';

  show(field(card, 'score-group'), ranked);
  if (ranked) {
    const band = matchBand(item.score);
    setText(field(card, 'match'), `${band.percent}%`);
    const badge = field(card, 'band');
    setText(badge, band.label);
    badge.className = `badge ${BAND_BADGE[band.label]}`.trim();
  }

  setText(field(card, 'why'), item.why);
  const matched = ranked ? item.matchedSkills ?? [] : [];
  const missing = ranked ? item.missingSkills ?? [] : [];
  renderChips(field(card, 'matched'), matched);
  renderChips(field(card, 'missing'), missing);
  show(field(card, 'matched-group'), matched.length > 0);
  show(field(card, 'missing-group'), missing.length > 0);
  show(field(card, 'skills'), matched.length + missing.length > 0);

  setText(field(card, 'excerpt'), job.excerpt);
  show(field(card, 'excerpt'), Boolean(job.excerpt));
  setLink(field(card, 'apply'), job.applyUrl);
  setLink(field(card, 'view'), job.url);

  wireSave(field(card, 'save'), field(card, 'save-label'), job.id, item.savedStatus);
  hydrateIcons(card);
  return card;
}

function setLink(anchor, url) {
  const href = safeLink(url);
  show(anchor, Boolean(href));
  if (href) {
    anchor.href = href;
  }
}

function wireSave(button, label, jobId, initialStatus) {
  let saved = Boolean(initialStatus);
  const paint = () => {
    button.setAttribute('aria-pressed', String(saved));
    setText(label, saved ? 'Saved' : 'Save');
  };
  paint();

  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      if (saved) {
        await unsaveJob(jobId);
      } else {
        await saveJob(jobId);
      }
      saved = !saved;
      paint();
    } catch (error) {
      setText(label, 'Try again');
      console.error('Could not update the saved job', error);
    } finally {
      button.disabled = false;
    }
  });
}
