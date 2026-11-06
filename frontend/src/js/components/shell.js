import { refreshCurrentUser } from '../api/auth-api.js';
import { listVersions } from '../api/resume-api.js';
import { el, setText } from '../core/dom.js';
import { clearSession, getUser } from '../core/session.js';
import { initials, shortDate } from '../pages/insights.js';
import { hydrateIcons, icon } from './icons.js';

// The app shell shared by the signed-in pages (upload, dashboard, jobs, saved, watchlist): the sidebar with the
// account, the main navigation and the resume versions, plus the mobile drawer behaviour.
// The page's HTML holds an empty <aside id="sidebar">, a #scrim and a #menu-button.

const NAV = [
  { key: 'overview', label: 'Overview', icon: 'home', href: 'dashboard.html#overview' },
  { key: 'resume', label: 'Resume analyzer', icon: 'file', href: 'upload.html' },
  { key: 'matches', label: 'Role matches', icon: 'target', href: 'dashboard.html#matches' },
  { key: 'jd', label: 'JD match', icon: 'briefcase', href: 'dashboard.html#jd' },
  { key: 'jobs', label: 'Jobs for you', icon: 'search', href: 'jobs.html' },
  { key: 'saved', label: 'Saved jobs', icon: 'bookmark', href: 'saved.html' },
  { key: 'watchlist', label: 'Watchlist', icon: 'eye', href: 'watchlist.html' },
];

let versionList = null;

/**
 * Builds the sidebar with `active` highlighted. Resolves to the user's resume versions
 * (oldest first, `[]` if they could not be loaded), which the pages reuse.
 */
export function renderShell(active) {
  const sidebar = document.getElementById('sidebar');
  const user = getUser();

  // Only administrators get a badge; everyone else has the same product.
  const roleBadge = el('span', { class: 'badge badge-blue' });
  const paintRole = (role) => {
    setText(roleBadge, role === 'ADMIN' ? 'Admin' : '');
    roleBadge.hidden = role !== 'ADMIN';
  };
  paintRole(user?.role);

  const nav = el(
    'nav',
    { class: 'sb-nav', 'aria-label': 'Main' },
    ...NAV.map((item) =>
      el('a', { class: 'sb-link', href: item.href, 'data-nav': item.key }, icon(item.icon), item.label),
    ),
  );

  versionList = el('ul', { class: 'sb-versions' }, el('li', { class: 'sb-empty' }, 'Loading…'));

  const signOut = el('button', { class: 'sb-link', type: 'button' }, icon('logout'), 'Sign out');
  signOut.addEventListener('click', () => {
    clearSession();
    location.href = 'login.html';
  });

  const close = el('button', { class: 'icon-btn sb-close', type: 'button', 'aria-label': 'Close navigation' }, icon('close'));
  close.addEventListener('click', () => setDrawer(false));

  sidebar.replaceChildren(
    el('div', { class: 'sb-top' }, brandLink(), close),
    el(
      'div',
      { class: 'sb-user' },
      el('span', { class: 'avatar', 'aria-hidden': 'true' }, initials(user?.email)),
      el('div', {}, el('p', { class: 'sb-email', title: user?.email ?? '' }, user?.email ?? ''), roleBadge),
    ),
    el('p', { class: 'sb-label' }, 'General'),
    nav,
    el('p', { class: 'sb-label' }, 'Resume versions'),
    versionList,
    el('div', { class: 'sb-foot' }, signOut),
  );
  setActive(active);

  // Drawer on small screens.
  const menuButton = document.getElementById('menu-button');
  menuButton.addEventListener('click', () => setDrawer(true));
  document.getElementById('scrim').addEventListener('click', () => setDrawer(false));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.body.classList.contains('nav-open')) {
      setDrawer(false);
      menuButton.focus();
    }
  });
  nav.addEventListener('click', () => setDrawer(false));
  hydrateIcons();

  // The stored role goes stale after an admin changes it; refresh it quietly.
  refreshCurrentUser().then(
    (fresh) => paintRole(fresh.role),
    () => undefined,
  );

  return listVersions().then(
    (versions) => {
      renderVersions(versions);
      return versions;
    },
    (error) => {
      console.error('Could not load resume versions', error);
      versionList.replaceChildren(el('li', { class: 'sb-empty' }, 'Versions unavailable'));
      return [];
    },
  );
}

/** Highlights a navigation item (the dashboard calls this as its tabs change). */
export function setActive(key) {
  for (const link of document.querySelectorAll('.sb-link[data-nav]')) {
    if (link.dataset.nav === key) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  }
}

/** Newest first; `currentId` marks the version on screen. */
export function renderVersions(versions, currentId = null) {
  if (!versionList) {
    return;
  }
  if (versions.length === 0) {
    versionList.replaceChildren(el('li', { class: 'sb-empty' }, 'No uploads yet'));
    return;
  }
  versionList.replaceChildren(
    ...[...versions].reverse().map((resume) =>
      el(
        'li',
        {},
        el(
          'a',
          {
            class: 'sb-version',
            href: `upload.html?resume=${encodeURIComponent(resume.id)}`,
            'aria-current': resume.id === currentId ? 'true' : null,
          },
          el('span', { class: 'sb-dot', 'aria-hidden': 'true' }),
          `Version ${resume.version}`,
          el('span', { class: 'when' }, shortDate(resume.uploadedAt)),
        ),
      ),
    ),
  );
}

/** The logo link used in the sidebar and on the public pages. */
export function brandLink() {
  const link = el('a', { class: 'brand', href: 'index.html' });
  link.append(brandMark(), 'Smart Resume Analyser');
  return link;
}

function brandMark() {
  // Static markup written here, never backend data.
  const holder = document.createElement('span');
  holder.innerHTML = BRAND_SVG;
  return holder.firstElementChild;
}

function setDrawer(open) {
  document.body.classList.toggle('nav-open', open);
  document.getElementById('scrim').hidden = !open;
  document.getElementById('menu-button').setAttribute('aria-expanded', String(open));
}

export const BRAND_SVG =
  '<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#3b5bdb"/>' +
  '<path d="M11 7.5h7.2l4.3 4.3V24a1 1 0 0 1-1 1H11a1 1 0 0 1-1-1V8.5a1 1 0 0 1 1-1z" fill="#fff"/>' +
  '<path d="M18.2 7.5v4.3h4.3z" fill="#c7d2fe"/>' +
  '<path d="M13 15.5h6.5M13 19h4.5" stroke="#3b5bdb" stroke-width="1.7" stroke-linecap="round"/></svg>';
