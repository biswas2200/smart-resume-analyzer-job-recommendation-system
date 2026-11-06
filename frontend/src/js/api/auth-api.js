import { get, post } from '../core/http.js';
import { saveSession, saveUser } from '../core/session.js';

// Backed by com.resumeanalyser.auth.AuthController.

/**
 * Creates a new account via `POST /auth/register` and, on success, starts a session for it —
 * the backend returns the same `AuthResponse` as login, so a freshly registered user is
 * immediately signed in.
 */
export async function register(email, password) {
  const authResponse = await post('/auth/register', { json: { email, password } });
  saveSession(authResponse);
  return authResponse;
}

/** Authenticates an existing account via `POST /auth/login` and starts a session for it. */
export async function login(email, password) {
  const authResponse = await post('/auth/login', { json: { email, password } });
  saveSession(authResponse);
  return authResponse;
}

/**
 * Re-reads the signed-in account from `GET /auth/me` and updates the stored user. The role
 * inside a stored session goes stale the moment an admin changes it, so pages whose UI depends
 * on the role call this on load.
 */
export async function refreshCurrentUser() {
  const user = await get('/auth/me');
  saveUser(user);
  return user;
}
