import { test } from 'node:test';
import assert from 'node:assert/strict';

import { ApiError, extractApiErrorMessage } from '../src/js/core/api-error.js';

test('uses the backend message', () => {
  const error = new ApiError(409, { status: 409, message: 'Email already registered', fieldErrors: null });
  assert.equal(extractApiErrorMessage(error), 'Email already registered');
});

test('appends per-field validation errors', () => {
  const error = new ApiError(400, {
    message: 'Validation failed',
    fieldErrors: ['email: must be a well-formed email address', 'password: size must be between 8 and 72'],
  });
  assert.equal(
    extractApiErrorMessage(error),
    'Validation failed: email: must be a well-formed email address, password: size must be between 8 and 72',
  );
});

test('falls back when there is no body (network failure)', () => {
  assert.equal(extractApiErrorMessage(new ApiError(0, null), 'Offline'), 'Offline');
});

test('falls back for anything that is not an ApiError', () => {
  assert.equal(extractApiErrorMessage(new TypeError('boom')), 'Something went wrong. Please try again.');
});
