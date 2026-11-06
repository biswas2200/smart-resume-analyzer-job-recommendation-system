// The signed-in session lives in localStorage so a page load (every navigation, in a multi-page
// app) doesn't log the user out. Inspect or clear it in DevTools → Application → Local Storage.
const TOKEN_STORAGE_KEY = 'resumeAnalyser.auth.token';
const USER_STORAGE_KEY = 'resumeAnalyser.auth.user';

/** The current JWT to send as `Authorization: Bearer <token>`, or null if signed out. */
export function getToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

/**
 * The signed-in user (`account.dto.UserDto`: `{ id, email, role, createdAt }`),
 * or null when no one is signed in.
 */
export function getUser() {
  const raw = localStorage.getItem(USER_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  // The value could be corrupted (or hand-edited in DevTools) — treat any parse failure as
  // "no session" rather than crashing the page.
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function isAuthenticated() {
  return getToken() !== null && getUser() !== null;
}

/** Starts a session from an `AuthResponse` (`{ token, tokenType, expiresAt, user }`). */
export function saveSession(authResponse) {
  localStorage.setItem(TOKEN_STORAGE_KEY, authResponse.token);
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(authResponse.user));
}

/** Replaces the stored user, e.g. after `GET /auth/me` picked up a role change. */
export function saveUser(user) {
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
}

/**
 * Page guard: call first thing in every protected page's script. Sends a signed-out visitor
 * to the login page and returns false, so the caller can stop right there.
 */
export function requireAuth() {
  if (isAuthenticated()) {
    return true;
  }
  location.replace('login.html');
  return false;
}
