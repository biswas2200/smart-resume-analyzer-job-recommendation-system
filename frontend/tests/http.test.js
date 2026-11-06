import { beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';

import { API_BASE_URL } from '../src/js/config.js';
import { ApiError } from '../src/js/core/api-error.js';
import { del, get, post, put } from '../src/js/core/http.js';
import { getToken, saveSession } from '../src/js/core/session.js';

// Minimal browser stand-ins: http.js only needs localStorage, location.replace and fetch.
const store = new Map();
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  },
});
const redirects = [];
globalThis.location = { replace: (url) => redirects.push(url) };

let calls;
function respondWith(status, body) {
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(body === undefined ? null : JSON.stringify(body), { status });
  };
}

beforeEach(() => {
  store.clear();
  redirects.length = 0;
  calls = [];
  saveSession({ token: 'jwt-123', user: { id: 'u1', email: 'a@b.c', role: 'USER' } });
});

test('attaches the Bearer token and returns the parsed body', async () => {
  respondWith(200, { ok: true });
  assert.deepEqual(await get('/recommendations/dashboard'), { ok: true });
  assert.equal(calls[0].url, `${API_BASE_URL}/recommendations/dashboard`);
  assert.equal(calls[0].init.headers.Authorization, 'Bearer jwt-123');
});

test('never sends the token to login/register', async () => {
  respondWith(200, { token: 't' });
  await post('/auth/login', { json: { email: 'a@b.c', password: 'x' } });
  assert.equal(calls[0].init.headers.Authorization, undefined);
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json');
  assert.equal(calls[0].init.body, '{"email":"a@b.c","password":"x"}');
});

test('204 No Content resolves to null', async () => {
  respondWith(204);
  assert.equal(await get('/feedback/r1'), null);
});

test('a failed request rejects with ApiError carrying the error body', async () => {
  respondWith(403, { status: 403, message: 'Forbidden', fieldErrors: null });
  await assert.rejects(post('/resumes/r1/jd-match', { json: { jdText: 'x' } }), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 403);
    assert.equal(error.body.message, 'Forbidden');
    return true;
  });
  assert.equal(getToken(), 'jwt-123', 'a 403 must not end the session');
});

test('a 401 on an authenticated call ends the session and goes to login', async () => {
  respondWith(401, { status: 401, message: 'Token expired' });
  await assert.rejects(get('/resumes'), ApiError);
  assert.equal(getToken(), null);
  assert.deepEqual(redirects, ['login.html']);
});

test('a 401 from login (wrong password) keeps the user on the page', async () => {
  respondWith(401, { status: 401, message: 'Invalid email or password' });
  await assert.rejects(post('/auth/login', { json: {} }), ApiError);
  assert.deepEqual(redirects, []);
});

test('a network failure rejects with status 0', async () => {
  globalThis.fetch = async () => {
    throw new TypeError('Failed to fetch');
  };
  const originalError = console.error;
  console.error = () => {};
  try {
    await assert.rejects(get('/resumes'), (error) => error instanceof ApiError && error.status === 0);
  } finally {
    console.error = originalError;
  }
});

test('put sends a JSON body with the token', async () => {
  respondWith(200, { status: 'APPLIED' });
  assert.deepEqual(await put('/jobs/j1/saved', { json: { status: 'APPLIED' } }), { status: 'APPLIED' });
  assert.equal(calls[0].init.method, 'PUT');
  assert.equal(calls[0].init.body, '{"status":"APPLIED"}');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer jwt-123');
});

test('del sends DELETE and resolves to null on 204', async () => {
  respondWith(204);
  assert.equal(await del('/jobs/j1/saved'), null);
  assert.equal(calls[0].init.method, 'DELETE');
});
