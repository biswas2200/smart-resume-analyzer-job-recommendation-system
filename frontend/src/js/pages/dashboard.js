import { getFeedbackFor, submit as submitFeedback } from '../api/feedback-api.js';
import { getInDemand } from '../api/jobs-api.js';
import { getDashboard } from '../api/recommendation-api.js';
import { matchJobDescription, reanalyze } from '../api/resume-api.js';
import { extractApiErrorMessage } from '../core/api-error.js';
import { byId, cloneTemplate, el, field, hide, renderChips, setBusy, setText, show } from '../core/dom.js';
import { readJson, writeJson } from '../core/local-store.js';
import { getUser, requireAuth } from '../core/session.js';
import { hydrateIcons, icon } from '../components/icons.js';
import { renderShell, setActive } from '../components/shell.js';
import {
  JD_MAX_CHARS,
  asPercent,
  canMatchJd,
  canUnlock,
  confidencePercent,
  demandChipLabel,
  demandFor,
  demandHeading,
  engineLabel,
  isBudgetExhausted,
  isCommunityEdition,
  isLlmExplanation,
  isLocked,
} from './dashboard-rules.js';
import {
  atsChange,
  checkSummary,
  describeChange,
  describeCheck,
  findNewMatches,
  formatScore,
  jdVerdict,
  nextSteps,
  paragraphs,
  scoreBand,
  scorePercent,
} from './insights.js';

// The dashboard for the latest resume version, in three tabs driven by the address hash:
// - #overview: ATS score and band, detected field, best match, every ATS check with how to fix
//   it, the suggestions (written by AI when the engine is available) and the next steps.
// - #matches: ranked role matches with the skills the user has and the ones to add, plus
//   helpful/not-helpful feedback (FR-10.1). When the field needs the AI engine and this
//   analysis could not use it, a locked card whose wording follows `lockReason` shows instead.
// - #jd: the job-description match.
// Lock decisions live in dashboard-rules.js, the wording in insights.js.

const TABS = ['overview', 'matches', 'jd'];
const TAB_LABELS = { overview: 'Dashboard', matches: 'Role matches', jd: 'JD match' };

/** The dashboard on screen; the re-analyse and JD-match handlers act on it. */
let dashboard = null;
let versionsReady = Promise.resolve([]);

if (requireAuth()) {
  hydrateIcons();
  init();
}

function init() {
  versionsReady = renderShell(currentTab());
  window.addEventListener('hashchange', showTab);

  byId('reanalyze-button').addEventListener('click', onReanalyze);
  byId('retry-button').addEventListener('click', loadDashboard);

  const jdText = byId('jd-text');
  jdText.maxLength = JD_MAX_CHARS;
  jdText.addEventListener('input', () => {
    byId('jd-match-button').disabled = jdText.value.trim() === '';
    setText(byId('jd-count'), `${jdText.value.length.toLocaleString()} / ${JD_MAX_CHARS.toLocaleString()} characters`);
  });
  byId('jd-form').addEventListener('submit', onMatchJd);

  loadDashboard();
}

function currentTab() {
  const tab = location.hash.slice(1);
  return TABS.includes(tab) ? tab : 'overview';
}

/** Shows the tab named in the hash (only once the dashboard has loaded). */
function showTab() {
  const tab = currentTab();
  setActive(tab);
  setText(byId('crumb'), TAB_LABELS[tab]);
  for (const link of document.querySelectorAll('.tab[data-tab]')) {
    if (link.dataset.tab === tab) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  }
  if (!dashboard) {
    return;
  }
  for (const name of TABS) {
    show(byId(`panel-${name}`), name === tab);
  }
}

async function loadDashboard() {
  showStatus('loading');
  try {
    dashboard = await getDashboard();
  } catch (error) {
    dashboard = null;
    showStatus('error', extractApiErrorMessage(error, 'Please check your connection and try again.'));
    return;
  }
  if (!dashboard) {
    showStatus('empty');
    return;
  }

  renderAtsScore(dashboard);
  renderDomain(dashboard);
  renderTopMatch(dashboard);
  renderChecks(dashboard);
  renderSuggestions(dashboard);
  if (isLocked(dashboard)) {
    hide(byId('recommendations-section'));
    renderLockedCard(dashboard);
  } else {
    hide(byId('locked-card'));
    renderRecommendations(dashboard);
  }
  renderJdPanel(dashboard);
  showStatus('ready');
  showTab();

  versionsReady.then((versions) => {
    const analysed = versions.find((resume) => resume.id === dashboard?.resumeId);
    setText(byId('analysed-version'), analysed ? `Analysis of version ${analysed.version}` : '');
  });
}

/** `loading`, `error` (with a message), `empty` (no resume yet) or `ready`. */
function showStatus(state, message) {
  show(byId('status-loading'), state === 'loading');
  show(byId('status-error'), state === 'error');
  show(byId('status-empty'), state === 'empty');
  if (state === 'error') {
    setText(byId('load-error'), message);
  }
  if (state !== 'ready') {
    TABS.forEach((name) => hide(byId(`panel-${name}`)));
  }
}

// ---------- Overview ----------

function renderAtsScore(data) {
  const ats = data.atsScore;
  const band = scoreBand(ats.score, ats.max_score);
  setText(byId('ats-score'), formatScore(ats.score));
  setText(byId('ats-max'), `/${formatScore(ats.max_score)}`);
  const badge = byId('ats-band');
  setText(badge, band.label);
  badge.className = `badge ${BADGE_FOR_TONE[band.tone]}`;
  const bar = byId('ats-bar');
  bar.className = `bar tone-${band.tone}`;
  bar.firstElementChild.style.width = `${scorePercent(ats.score, ats.max_score)}%`;

  // How the score moved since the previous version this browser saw.
  const key = `resumeAnalyser.lastAts.${getUser()?.id}`;
  const { delta, record } = atsChange(readJson(key), data.resumeId, ats.score);
  writeJson(key, record);
  setText(byId('ats-change'), describeChange(delta));
  show(byId('ats-change'), delta !== null);
}

const BADGE_FOR_TONE = { good: 'badge-green', ok: 'badge-blue', warn: 'badge-amber', bad: 'badge-red' };

function renderDomain(data) {
  const domain = data.domain;
  show(byId('domain-card'), !!domain);
  if (!domain) {
    return;
  }
  setText(byId('domain-name'), domain.name);
  setText(byId('domain-confidence'), `${confidencePercent(domain)}% sure`);
  setText(byId('domain-engine'), engineLabel(domain));
  setText(
    byId('domain-note'),
    domain.engine === 'local' ? 'Analysed in full on our own engine, as often as you like.' : 'Analysed with the AI engine.',
  );
}

function renderTopMatch(data) {
  const best = isLocked(data) ? null : data.recommendations[0];
  show(byId('top-match'), !!best);
  show(byId('top-none'), !best);
  if (best) {
    setText(byId('top-role'), best.role.title);
    setText(byId('top-percent'), String(asPercent(best.matchScore)));
  } else {
    setText(byId('top-none'), isLocked(data) ? 'Locked for this field. See Role matches.' : 'No matches yet.');
  }
  setText(byId('matches-count'), isLocked(data) ? '' : String(data.recommendations.length));
}

function renderChecks(data) {
  const checks = data.atsScore.checks;
  const summary = checkSummary(checks);
  setText(
    byId('checks-summary'),
    summary.toGain > 0
      ? `${summary.passed} of ${summary.total} passed · up to ${formatScore(summary.toGain)} points to gain`
      : `${summary.passed} of ${summary.total} passed`,
  );

  // Failed checks first, the costliest at the top.
  const rows = checks
    .map((check) => ({ check, view: describeCheck(check) }))
    .sort((a, b) => order(a.view) - order(b.view));
  byId('ats-checks').replaceChildren(
    ...rows.map(({ check, view }) => {
      const row = cloneTemplate('ats-check-template');
      row.classList.add(view.status);
      field(row, 'icon').append(icon(view.status === 'pass' ? 'check' : view.status === 'partial' ? 'minus' : 'x'));
      setText(field(row, 'label'), view.label);
      setText(field(row, 'points'), view.weight === null ? '' : `${formatScore(view.earned)} / ${view.weight} pts`);
      setText(field(row, 'detail'), check.detail);
      setText(field(row, 'fix'), view.fix);
      show(field(row, 'fix'), !!view.fix);
      return row;
    }),
  );
}

function order(view) {
  const rank = { fail: 0, partial: 1, pass: 2 }[view.status];
  return rank * 1000 - ((view.weight ?? 0) - (view.earned ?? 0));
}

function renderSuggestions(data) {
  const llm = isLlmExplanation(data);
  const badge = byId('coaching-badge');
  setText(badge, llm ? 'AI-written' : 'Standard');
  badge.className = `badge ${llm ? 'badge-violet' : ''}`.trim();
  const parts = paragraphs(data.explanation);
  byId('explanation').replaceChildren(
    ...(parts.length > 0 ? parts : ['No suggestions for this version.']).map((text) => el('p', { class: 'preserve-lines' }, text)),
  );
  byId('next-steps').replaceChildren(...nextSteps(data).map((step) => el('li', {}, el('span', {}, step))));
}

// ---------- Role matches ----------

function renderLockedCard(data) {
  const domainName = data.domain?.name ?? 'this field';
  for (const element of document.querySelectorAll('#locked-card [data-field="domain-name"]')) {
    setText(element, domainName);
  }
  const community = isCommunityEdition(data);
  const budget = isBudgetExhausted(data);
  show(byId('locked-community'), community);
  show(byId('locked-budget'), budget);
  show(byId('locked-default'), !community && !budget);

  const unlockable = canUnlock(data);
  show(byId('unlock-section'), unlockable);
  if (unlockable) {
    setText(byId('unlock-message'), 'Re-run the analysis to try again.');
  }
  show(byId('locked-card'));
}

function renderRecommendations(data) {
  const seenKey = `resumeAnalyser.seenRoles.${getUser()?.id}`;
  const { fresh, remember } = findNewMatches(data.recommendations, readJson(seenKey));
  writeJson(seenKey, remember);
  const freshIds = new Set(fresh.map((recommendation) => recommendation.recommendationId));

  const cards = data.recommendations.map((recommendation) => ({
    title: recommendation.role.title,
    card: buildMatchCard(recommendation, freshIds.has(recommendation.recommendationId)),
  }));
  byId('recommendations').replaceChildren(...cards.map(({ card }) => card));
  show(byId('recommendations-empty'), data.recommendations.length === 0);
  show(byId('recommendations-section'));
  if (cards.length > 0) {
    addDemand(cards);
  }
}

/**
 * Fills each role card with what open jobs for that role ask for (job-market demand), once it
 * arrives. Optional extra: on failure the cards simply stay without it.
 */
async function addDemand(cards) {
  let inDemand;
  try {
    inDemand = await getInDemand();
  } catch (error) {
    console.error('Could not load in-demand skills', error);
    return;
  }
  for (const { title, card } of cards) {
    const demand = demandFor(inDemand, title);
    if (!demand) {
      continue;
    }
    setText(field(card, 'demand-heading'), demandHeading(demand.jobCount));
    field(card, 'demand-skills').replaceChildren(
      ...demand.skills.map((skill) => el('li', skill.have ? { class: 'have' } : {}, demandChipLabel(skill))),
    );
    show(field(card, 'demand'));
  }
}

function buildMatchCard(recommendation, isNew) {
  const card = cloneTemplate('recommendation-template');
  const percent = asPercent(recommendation.matchScore);
  setText(field(card, 'title'), recommendation.role.title);
  setText(field(card, 'description'), recommendation.role.description);
  setText(field(card, 'match'), `${percent}%`);
  field(card, 'bar').firstElementChild.style.width = `${percent}%`;
  show(field(card, 'new'), isNew);

  renderChips(field(card, 'matched'), recommendation.matchedSkills);
  show(field(card, 'matched-group'), recommendation.matchedSkills.length > 0);
  renderChips(field(card, 'missing'), recommendation.missingSkills);
  show(field(card, 'missing-group'), recommendation.missingSkills.length > 0);

  field(card, 'vote').setAttribute('aria-label', `Is the ${recommendation.role.title} match useful?`);
  const helpfulButton = field(card, 'helpful');
  const notHelpfulButton = field(card, 'not-helpful');
  helpfulButton.prepend(icon('up'));
  notHelpfulButton.prepend(icon('down'));
  const markSelected = (helpful) => {
    helpfulButton.setAttribute('aria-pressed', String(helpful === true));
    notHelpfulButton.setAttribute('aria-pressed', String(helpful === false));
  };
  const rate = async (helpful) => {
    try {
      markSelected((await submitFeedback(recommendation.recommendationId, helpful)).helpful);
    } catch (error) {
      console.error('Could not save feedback', error);
    }
  };
  helpfulButton.addEventListener('click', () => rate(true));
  notHelpfulButton.addEventListener('click', () => rate(false));

  // Show the answer already given, if any (204 → null → nothing selected).
  getFeedbackFor(recommendation.recommendationId).then(
    (feedback) => feedback && markSelected(feedback.helpful),
    (error) => console.error('Could not load existing feedback', error),
  );
  return card;
}

async function onReanalyze() {
  const button = byId('reanalyze-button');
  const errorLine = byId('reanalyze-error');
  if (!dashboard?.resumeId) {
    return;
  }
  hide(errorLine);
  setBusy(button, true, 'Re-analysing…');
  try {
    await reanalyze(dashboard.resumeId);
    setBusy(button, false);
    await loadDashboard();
  } catch (error) {
    console.error('Re-analysis failed', error);
    setBusy(button, false);
    setText(errorLine, 'Could not re-analyse your resume right now. Please try again.');
    show(errorLine);
  }
}

// ---------- JD match ----------

function renderJdPanel(data) {
  const available = canMatchJd(data);
  show(byId('jd-section'), available);
}

async function onMatchJd(event) {
  event.preventDefault();
  const textarea = byId('jd-text');
  const button = byId('jd-match-button');
  const errorLine = byId('jd-match-error');
  const text = textarea.value.trim();
  if (!dashboard?.resumeId || !text) {
    return;
  }
  hide(errorLine);
  setBusy(button, true, 'Matching…');
  textarea.disabled = true;
  try {
    renderJdResult(await matchJobDescription(dashboard.resumeId, text));
  } catch (error) {
    setText(errorLine, extractApiErrorMessage(error, 'Could not match your resume to that job description right now.'));
    show(errorLine);
  } finally {
    setBusy(button, false);
    textarea.disabled = false;
  }
}

function renderJdResult(match) {
  const percent = asPercent(match.score);
  const verdict = jdVerdict(match.score);
  setText(byId('jd-score'), `${percent}%`);
  const ring = byId('jd-ring');
  ring.className = `ring tone-${verdict.tone}`;
  ring.style.setProperty('--p', String(percent));
  const badge = byId('jd-verdict');
  setText(badge, verdict.label);
  badge.className = `badge ${BADGE_FOR_TONE[verdict.tone]}`;

  setText(byId('jd-coverage'), `${asPercent(match.coverage)}% of the skills it asks for`);
  setText(byId('jd-similarity'), `${asPercent(match.similarity)}%`);
  setText(byId('jd-closest'), match.closestRole?.title ?? '');
  show(byId('jd-closest-group'), !!match.closestRole);
  renderChips(byId('jd-matched'), match.matchedSkills);
  show(byId('jd-matched-group'), match.matchedSkills.length > 0);
  renderChips(byId('jd-missing'), match.missingSkills);
  show(byId('jd-missing-group'), match.missingSkills.length > 0);
  setText(byId('jd-explanation'), match.explanation);
  show(byId('jd-explanation'), !!match.explanation);

  hide(byId('jd-placeholder'));
  show(byId('jd-result'));
}
