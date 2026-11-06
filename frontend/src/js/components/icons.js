// The app's line icons, drawn for this project on a 24-unit grid. `icon(name)` returns an
// <svg> that references a symbol in a sprite injected once per page, so every icon follows the
// current text colour through `stroke: currentColor` (see .icon in app.css).

const PATHS = {
  home: 'M3.5 10.5 12 3.5l8.5 7V20a1 1 0 0 1-1 1h-5v-6h-5v6h-5a1 1 0 0 1-1-1z',
  file: 'M14 3H6.5a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7.5zM14 3v4.5h4.5M9 12.5h6M9 16.5h4',
  target: 'M12 3a9 9 0 1 0 0 18 9 9 0 1 0 0-18zM12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 1 0 0-9zM12 11.2a.8.8 0 1 0 0 1.6.8.8 0 1 0 0-1.6z',
  briefcase: 'M4 7.5h16a1 1 0 0 1 1 1V19a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8.5a1 1 0 0 1 1-1zM8.5 7.5V5.5a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1v2M3 13h18',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 1 0 0-18zM12 7.5V12l3 2',
  upload: 'M12 15.5V4M7.5 8.5 12 4l4.5 4.5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4',
  logout: 'M9.5 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4.5M15 16l4-4-4-4M19 12H9.5',
  check: 'M5 12.5 10 17.5 19 7',
  x: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  alert: 'M12 3.5 2.8 19.5h18.4zM12 9.5v4.5M12 17v.3',
  minus: 'M6 12h12',
  sparkle: 'M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9zM18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z',
  plus: 'M12 5v14M5 12h14',
  menu: 'M4 7h16M4 12h16M4 17h16',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  up: 'M7.5 10.5V20H4.5v-9.5zM7.5 10.5 11 3.6a2 2 0 0 1 3.4 1.9L13.5 9h5.3a2 2 0 0 1 2 2.4l-1.3 6.9A2 2 0 0 1 17.5 20H7.5',
  down: 'M16.5 13.5V4h3v9.5zM16.5 13.5 13 20.4a2 2 0 0 1-3.4-1.9l.9-3.5H5.2a2 2 0 0 1-2-2.4l1.3-6.9A2 2 0 0 1 6.5 4h10',
  lock: 'M6 11h12a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
  refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4v4.5H15',
  close: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 1 0 0-13zM15.3 15.3 20 20',
  bookmark: 'M7 3.5h10a1 1 0 0 1 1 1V20.5l-6-4-6 4V4.5a1 1 0 0 1 1-1z',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9a3 3 0 1 0 0 6 3 3 0 1 0 0-6z',
  pin: 'M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.8-6.5 11-6.5 11zM12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 1 0 0-5z',
};

const SVG_NS = 'http://www.w3.org/2000/svg';

function ensureSprite() {
  if (document.getElementById('icon-sprite')) {
    return;
  }
  const sprite = document.createElementNS(SVG_NS, 'svg');
  sprite.id = 'icon-sprite';
  sprite.setAttribute('aria-hidden', 'true');
  sprite.style.display = 'none';
  for (const [name, d] of Object.entries(PATHS)) {
    const symbol = document.createElementNS(SVG_NS, 'symbol');
    symbol.id = `i-${name}`;
    symbol.setAttribute('viewBox', '0 0 24 24');
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', d);
    symbol.append(path);
    sprite.append(symbol);
  }
  document.body.prepend(sprite);
}

/** An `<svg class="icon">` showing the named icon; decorative, so hidden from screen readers. */
export function icon(name, className = '') {
  ensureSprite();
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', `icon ${className}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

/** Replaces every `<i data-icon="name">` placeholder in the static HTML with its icon. */
export function hydrateIcons(root = document) {
  for (const placeholder of root.querySelectorAll('i[data-icon]')) {
    placeholder.replaceWith(icon(placeholder.dataset.icon, placeholder.className));
  }
}
