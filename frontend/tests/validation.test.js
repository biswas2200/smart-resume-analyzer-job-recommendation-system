import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  MAX_FILE_SIZE_BYTES,
  validateConfirmPassword,
  validateEmail,
  validateLoginPassword,
  validateNewPassword,
  validateResumeFile,
} from '../src/js/core/validation.js';

const PDF = 'application/pdf';
const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

test('email: required, well-formed, at most 320 characters', () => {
  assert.equal(validateEmail(''), 'Email is required.');
  assert.equal(validateEmail('not-an-email'), 'Enter a valid email address.');
  assert.equal(validateEmail('a b@example.com'), 'Enter a valid email address.');
  assert.equal(validateEmail(`${'a'.repeat(310)}@example.com`), 'Enter a valid email address.');
  assert.equal(validateEmail('jane@example.com'), null);
});

test('login password only has to be present', () => {
  assert.equal(validateLoginPassword(''), 'Password is required.');
  assert.equal(validateLoginPassword('x'), null);
});

test('new password must be 8-72 characters', () => {
  assert.equal(validateNewPassword(''), 'Password is required.');
  assert.equal(validateNewPassword('a'.repeat(7)), 'Password must be at least 8 characters.');
  assert.equal(validateNewPassword('a'.repeat(8)), null);
  assert.equal(validateNewPassword('a'.repeat(72)), null);
  assert.equal(validateNewPassword('a'.repeat(73)), 'Password must be at most 72 characters.');
});

test('confirm password must match', () => {
  assert.equal(validateConfirmPassword('secret123', ''), 'Please confirm your password.');
  assert.equal(validateConfirmPassword('secret123', 'secret124'), 'Passwords do not match.');
  assert.equal(validateConfirmPassword('secret123', 'secret123'), null);
});

test('resume file: PDF or DOCX, up to 5 MB', () => {
  assert.equal(validateResumeFile(null), 'Choose a file first.');
  assert.equal(validateResumeFile({ type: PDF, size: 1000 }), null);
  assert.equal(validateResumeFile({ type: DOCX, size: MAX_FILE_SIZE_BYTES }), null);
  assert.equal(validateResumeFile({ type: 'image/png', size: 1000 }), 'Only PDF or DOCX files are accepted.');
  assert.equal(
    validateResumeFile({ type: PDF, size: MAX_FILE_SIZE_BYTES + 1 }),
    'File is too large — the maximum size is 5 MB.',
  );
});
