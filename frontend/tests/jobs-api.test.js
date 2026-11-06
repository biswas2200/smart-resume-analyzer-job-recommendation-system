import { beforeEach, test } from 'node:test';
import assert from 'node:assert/strict';

import { API_BASE_URL } from '../src/js/config.js';
import { getRecommended, getSaved, saveJob, unsaveJob } from '../src/js/api/jobs-api.js';

// jobs-api.js goes through http.js, which only needs localStorage, location and fetch.
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
});
globalThis.location = { replace: () => {} };

let calls;
beforeEach(() => {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, method: init.method, body: init.body });
    return new Response(init.method === 'DELETE' ? null : '{}', { status: init.method === 'DELETE' ? 204 : 200 });
  };
});

test('getRecommended asks for ranked jobs with the filters', async () => {
  await getRecommended({ q: 'data', workplace: 'hybrid' });
  assert.deepEqual(calls, [{ url: `${API_BASE_URL}/jobs/recommended?q=data&workplace=hybrid&limit=50`, method: 'GET', body: undefined }]);
});

test('getSaved lists the saved jobs', async () => {
  await getSaved();
  assert.equal(calls[0].url, `${API_BASE_URL}/jobs/saved`);
});

test('saveJob saves with or without a status; the job id is encoded', async () => {
  await saveJob('a/b');
  await saveJob('j1', 'APPLIED');
  assert.deepEqual(calls.map((c) => [c.method, c.url.replace(API_BASE_URL, ''), c.body]), [
    ['PUT', '/jobs/a%2Fb/saved', undefined],
    ['PUT', '/jobs/j1/saved', '{"status":"APPLIED"}'],
  ]);
});

test('unsaveJob deletes the saved entry', async () => {
  assert.equal(await unsaveJob('j1'), null);
  assert.deepEqual([calls[0].method, calls[0].url], ['DELETE', `${API_BASE_URL}/jobs/j1/saved`]);
});
