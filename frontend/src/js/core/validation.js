// Client-side mirrors of the backend's own checks, so a user sees the problem before submitting.
// Every function here is pure (no DOM), so tests/validation.test.js can exercise it under Node.

// The backend (RegisterRequest) enforces 8-72 characters; bcrypt silently ignores anything
// past 72 bytes, so the upper bound is a real constraint, not just an arbitrary UI limit.
export const MIN_PASSWORD_LENGTH = 8;
export const MAX_PASSWORD_LENGTH = 72;
export const MAX_EMAIL_LENGTH = 320;

// FR-1.1/FR-1.3 (docs/process-flow.md §2): only PDF/DOCX, up to 5 MB, is accepted.
// The backend (com.resumeanalyser.resume.ResumeService) enforces the same size limit.
export const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024;
const ALLOWED_MIME_TYPES = new Set([
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

// Same shape of check as a browser's <input type="email">: something@something.tld-ish.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+$/;

/** @returns a user-facing error message for the email field, or null when it is fine. */
export function validateEmail(email) {
  if (!email) {
    return 'Email is required.';
  }
  if (!EMAIL_PATTERN.test(email) || email.length > MAX_EMAIL_LENGTH) {
    return 'Enter a valid email address.';
  }
  return null;
}

/** Login only needs a non-empty password; the backend decides whether it's right. */
export function validateLoginPassword(password) {
  return password ? null : 'Password is required.';
}

/** Register enforces the backend's 8-72 character rule. */
export function validateNewPassword(password) {
  if (!password) {
    return 'Password is required.';
  }
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    return `Password must be at most ${MAX_PASSWORD_LENGTH} characters.`;
  }
  return null;
}

export function validateConfirmPassword(password, confirmPassword) {
  if (!confirmPassword) {
    return 'Please confirm your password.';
  }
  return password === confirmPassword ? null : 'Passwords do not match.';
}

/**
 * Checks a chosen resume file against FR-1.1/FR-1.3 before it's ever sent anywhere.
 * Takes anything with `type` and `size` (a browser `File`, or a plain object in tests).
 * @returns a user-facing error message, or null when the file is acceptable.
 */
export function validateResumeFile(file) {
  if (!file) {
    return 'Choose a file first.';
  }
  if (!ALLOWED_MIME_TYPES.has(file.type)) {
    return 'Only PDF or DOCX files are accepted.';
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return 'File is too large — the maximum size is 5 MB.';
  }
  return null;
}
