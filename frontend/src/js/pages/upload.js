import { getParsedProfile, upload } from '../api/resume-api.js';
import { extractApiErrorMessage } from '../core/api-error.js';
import { byId, cloneTemplate, el, field, hide, renderChips, setBusy, setText, show } from '../core/dom.js';
import { requireAuth } from '../core/session.js';
import { validateResumeFile } from '../core/validation.js';
import { hydrateIcons } from '../components/icons.js';
import { renderShell, renderVersions } from '../components/shell.js';

// The resume analyzer: upload a PDF/DOCX as a new resume version (FR-1.5), preview it, and show
// what was read from it. The left column is the resume as we read it (or the original PDF, for
// a file chosen in this browser) above the file card; the right column is the parsing result
// for the version picked in the version menu. `?resume=<id>` opens a given version.

let versions = [];
/** The resume id on screen; a slow profile load for another version never overwrites it. */
let shownId = null;
/** Object URL of a PDF chosen in this browser, for the "Original file" preview. */
let originalUrl = null;

if (requireAuth()) {
  hydrateIcons();
  init();
}

async function init() {
  const fileInput = byId('resume-file');
  const submitButton = byId('upload-submit');
  const dropzone = byId('dropzone');

  fileInput.addEventListener('change', () => chooseFile(fileInput.files[0] ?? null));

  for (const type of ['dragenter', 'dragover']) {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add('dragging');
    });
  }
  for (const type of ['dragleave', 'drop']) {
    dropzone.addEventListener(type, () => dropzone.classList.remove('dragging'));
  }
  dropzone.addEventListener('drop', (event) => {
    event.preventDefault();
    if (event.dataTransfer.files.length > 0) {
      fileInput.files = event.dataTransfer.files;
      fileInput.dispatchEvent(new Event('change'));
    }
  });

  submitButton.addEventListener('click', () => onUpload(fileInput, submitButton));
  byId('version-select').addEventListener('change', (event) => openVersion(event.target.value));
  byId('view-parsed').addEventListener('click', () => setPreview('parsed'));
  byId('view-original').addEventListener('click', () => setPreview('original'));

  versions = await renderShell('resume');
  if (versions.length === 0) {
    return;
  }
  const requested = new URLSearchParams(location.search).get('resume');
  const start = versions.find((resume) => resume.id === requested) ?? versions.at(-1);
  renderVersionSelect();
  show(byId('to-dashboard'));
  openVersion(start.id);
}

function chooseFile(file) {
  hide(byId('upload-error'));
  hide(byId('upload-success'));
  const error = file ? validateResumeFile(file) : null;
  byId('upload-submit').disabled = !file || error !== null;
  if (error) {
    showError(error);
  }
  setText(byId('file-name'), file ? file.name : 'Upload a resume');
  setText(byId('file-detail'), file ? `${formatSize(file.size)} · ready to upload` : 'PDF or DOCX · up to 5 MB');

  if (originalUrl) {
    URL.revokeObjectURL(originalUrl);
    originalUrl = null;
  }
  const isPdf = !!file && !error && file.type === 'application/pdf';
  if (isPdf) {
    originalUrl = URL.createObjectURL(file);
  }
  byId('view-original').disabled = !isPdf;
  setPreview(isPdf ? 'original' : 'parsed');
}

async function onUpload(fileInput, submitButton) {
  const file = fileInput.files[0] ?? null;
  const validationError = validateResumeFile(file);
  if (validationError) {
    showError(validationError);
    return;
  }

  hide(byId('upload-error'));
  hide(byId('upload-success'));
  setBusy(submitButton, true, 'Analysing…');
  show(byId('upload-loader'));
  try {
    const resume = await upload(file);
    versions = [...versions, resume];
    renderVersionSelect();
    await openVersion(resume.id);
    setText(byId('file-name'), file.name);
    setText(byId('file-detail'), `${formatSize(file.size)} · uploaded as version ${resume.version}`);
    setText(byId('upload-success'), `Version ${resume.version} is analysed. Open the dashboard to see your score and role matches.`);
    show(byId('upload-success'));
    show(byId('to-dashboard'));
    fileInput.value = '';
    submitButton.disabled = true;
  } catch (error) {
    // The backend's message is specific where it matters -- an unsupported file format (415)
    // or the AI engine being unavailable for an analysis (503) -- so prefer it.
    showError(extractApiErrorMessage(error, 'Could not upload the resume. Please try again.'));
  } finally {
    setBusy(submitButton, false);
    submitButton.disabled = !fileInput.files[0];
    hide(byId('upload-loader'));
  }
}

/** Newest first, so the latest version is the default. */
function renderVersionSelect() {
  const select = byId('version-select');
  select.replaceChildren(
    ...[...versions].reverse().map((resume, index) =>
      el('option', { value: resume.id }, `Version ${resume.version}${index === 0 ? ' (latest)' : ''} · ${formatDate(resume.uploadedAt)}`),
    ),
  );
  show(select, versions.length > 0);
}

async function openVersion(resumeId) {
  const resume = versions.find((candidate) => candidate.id === resumeId);
  if (!resume) {
    return;
  }
  shownId = resumeId;
  byId('version-select').value = resumeId;
  renderVersions(versions, resumeId);
  try {
    history.replaceState(null, '', `?resume=${encodeURIComponent(resumeId)}`);
  } catch {
    // Some sandboxed previews refuse; the page works without it.
  }

  hide(byId('profile-empty'));
  show(byId('profile-loading'));
  try {
    const profile = await getParsedProfile(resumeId);
    if (shownId === resumeId) {
      renderProfile(profile, resume);
    }
  } catch (error) {
    if (shownId === resumeId) {
      showError(extractApiErrorMessage(error, 'Could not load this version. Please try again.'));
    }
  } finally {
    if (shownId === resumeId) {
      hide(byId('profile-loading'));
    }
  }
}

function renderProfile(profile, resume) {
  const skills = profile.skills ?? [];
  const experience = (profile.experience ?? []).map((entry) => [entry.title, entry.organization, entry.duration]);
  const education = (profile.education ?? []).map((entry) => [entry.degree, entry.institution, entry.year]);
  const contact = [profile.email, profile.phone].filter(Boolean).join(' · ');

  // Right column: the parsing result.
  setText(byId('kv-name'), profile.name || 'Not found');
  setText(byId('kv-email'), profile.email || 'Not found');
  setText(byId('kv-phone'), profile.phone || 'Not found');
  setText(byId('kv-version'), `${resume.version} of ${versions.length}`);
  setText(byId('kv-uploaded'), formatDateTime(resume.uploadedAt));
  renderChips(byId('profile-skills'), skills);
  setText(byId('skills-count'), String(skills.length));
  show(byId('skills-empty'), skills.length === 0);
  renderTimeline('profile-experience', experience);
  show(byId('experience-empty'), experience.length === 0);
  renderTimeline('profile-education', education);
  show(byId('education-empty'), education.length === 0);
  show(byId('profile-body'));

  // Left column: the same data laid out as a page.
  setText(byId('paper-name'), profile.name || 'Your name');
  setText(byId('paper-contact'), contact);
  setText(byId('paper-skills'), skills.join(' · '));
  show(byId('paper-skills-block'), skills.length > 0);
  fillPaperList('paper-experience', experience);
  show(byId('paper-experience-block'), experience.length > 0);
  fillPaperList('paper-education', education);
  show(byId('paper-education-block'), education.length > 0);
  hide(byId('paper-empty'));
  show(byId('paper-content'));
  setText(byId('preview-version'), `v${resume.version}`);
}

/** Each entry is [what, where, when]; any of them may be missing from a resume. */
function renderTimeline(listId, entries) {
  byId(listId).replaceChildren(
    ...entries.map(([what, where, when]) => {
      const item = cloneTemplate('timeline-template');
      setText(field(item, 'what'), what || where || '');
      setText(field(item, 'where'), what && where ? `, ${where}` : '');
      setText(field(item, 'when'), when);
      return item;
    }),
  );
}

function fillPaperList(listId, entries) {
  byId(listId).replaceChildren(
    ...entries.map(([what, where, when]) =>
      el('li', {}, el('span', {}, [what, where].filter(Boolean).join(', ')), el('span', {}, when ?? '')),
    ),
  );
}

function setPreview(mode) {
  const original = mode === 'original' && !!originalUrl;
  byId('view-parsed').setAttribute('aria-selected', String(!original));
  byId('view-original').setAttribute('aria-selected', String(original));
  const frame = byId('original-frame');
  if (original && frame.src !== originalUrl) {
    frame.src = originalUrl;
  }
  show(frame, original);
  show(byId('paper'), !original);
}

function showError(message) {
  setText(byId('upload-error'), message);
  show(byId('upload-error'));
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

function formatDateTime(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function formatSize(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
