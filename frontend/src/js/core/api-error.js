const DEFAULT_FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

/**
 * Thrown by `http.js` for every failed request.
 *
 * `status` is the HTTP status, or 0 when the request never got a response (backend down,
 * CORS rejection, no network). `body` is the parsed JSON error body when there was one — the
 * backend's uniform `com.resumeanalyser.common.ApiError`:
 * `{ timestamp, status, message, fieldErrors: string[] | null }`.
 */
export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message ?? `Request failed with status ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body ?? null;
  }
}

/**
 * Turns any error thrown by an API call into a message safe to show a user.
 * Reads the backend's error body when present, including any per-field validation details;
 * otherwise falls back to a generic message, since the error could be a network failure
 * with no server-generated body at all.
 */
export function extractApiErrorMessage(error, fallback = DEFAULT_FALLBACK_MESSAGE) {
  if (!(error instanceof ApiError)) {
    return fallback;
  }

  const body = error.body;
  if (!body?.message) {
    return fallback;
  }

  if (body.fieldErrors?.length) {
    return `${body.message}: ${body.fieldErrors.join(', ')}`;
  }

  return body.message;
}
