// Small per-browser memories that only add polish: which roles a user has already seen and
// the last ATS score. Losing one costs nothing, so every read and write
// tolerates a browser that blocks storage instead of breaking the page.

export function readJson(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage blocked or full: the page works without it.
  }
}
