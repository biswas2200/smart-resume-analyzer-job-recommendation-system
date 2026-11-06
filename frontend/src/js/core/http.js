import { API_BASE_URL } from '../config.js';
import { ApiError } from './api-error.js';
import { clearSession, getToken } from './session.js';

// The login/register endpoints must never carry a (possibly stale) Bearer token — the backend
// treats them as unauthenticated on purpose (see AuthController), and an unrelated 401 from a
// leftover token would be confusing to debug.
const UNAUTHENTICATED_PATHS = ['/auth/login', '/auth/register'];

/**
 * The one place every backend call goes through.
 *
 * - `json` is sent as an `application/json` body; `formData` as multipart (the browser sets the
 *   boundary header itself, so no Content-Type is set for it).
 * - The session's JWT is attached as `Authorization: Bearer <token>`, except on login/register.
 * - Resolves to the parsed JSON body, or null for 204 No Content / an empty body.
 * - Rejects with an {@link ApiError} for any non-2xx status or network failure.
 * - A 401 on a request that carried a token means the session expired: it is cleared and the
 *   browser is sent to the login page.
 */
export async function request(method, path, { json, formData } = {}) {
  const headers = {};
  let body;
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  } else if (formData !== undefined) {
    body = formData;
  }

  const token = getToken();
  const sendsToken = token !== null && !UNAUTHENTICATED_PATHS.some((p) => path.startsWith(p));
  if (sendsToken) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body });
  } catch (networkError) {
    console.error(`${method} ${path} failed before a response arrived`, networkError);
    throw new ApiError(0, null);
  }

  const responseBody = await readBody(response);

  if (!response.ok) {
    if (response.status === 401 && sendsToken) {
      clearSession();
      location.replace('login.html');
    }
    throw new ApiError(response.status, responseBody);
  }

  return responseBody;
}

export const get = (path) => request('GET', path);
export const post = (path, options) => request('POST', path, options);
export const put = (path, options) => request('PUT', path, options);
export const del = (path) => request('DELETE', path);

async function readBody(response) {
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    // Not JSON (e.g. an HTML error page from a proxy) — no structured body to offer.
    return null;
  }
}
