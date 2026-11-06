import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  SAVED_STATUSES,
  emptyState,
  employmentLabel,
  locationLabel,
  isNewJob,
  isRanked,
  groupSaved,
  jobsQuery,
  matchBand,
  postedLabel,
  safeLink,
  statusLabel,
  workplaceLabel,
} from '../src/js/pages/jobs-rules.js';

const job = (overrides) => ({
  id: 'j1',
  title: 'Backend Engineer',
  company: 'Groww',
  workplaceType: '',
  url: 'https://jobs.lever.co/groww/1',
  applyUrl: 'https://jobs.lever.co/groww/1/apply',
  publishedAt: null,
  firstSeenAt: '2026-10-20T08:00:00Z',
  active: true,
  ...overrides,
});

test('jobsQuery: only the filters that are set, trimmed and encoded', () => {
  assert.equal(jobsQuery({}), '/jobs/recommended?limit=50');
  assert.equal(
    jobsQuery({ q: '  data & ml ', workplace: 'remote', limit: 20 }),
    '/jobs/recommended?q=data+%26+ml&workplace=remote&limit=20',
  );
});

test('jobsQuery: an unknown workplace value is dropped, not sent', () => {
  assert.equal(jobsQuery({ workplace: 'moon' }), '/jobs/recommended?limit=50');
});

test('matchBand: percent and a plain label from the 0..1 score', () => {
  assert.deepEqual(matchBand(0.82), { percent: 82, label: 'Strong match' });
  assert.deepEqual(matchBand(0.6), { percent: 60, label: 'Good match' });
  assert.deepEqual(matchBand(0.31), { percent: 31, label: 'Partial match' });
  assert.deepEqual(matchBand(null), { percent: 0, label: 'Partial match' });
});

test('workplaceLabel: the feeds spell it many ways', () => {
  assert.equal(workplaceLabel('remote'), 'Remote');
  assert.equal(workplaceLabel('REMOTE'), 'Remote');
  assert.equal(workplaceLabel('Hybrid'), 'Hybrid');
  assert.equal(workplaceLabel('onsite'), 'On-site');
  assert.equal(workplaceLabel('On-site'), 'On-site');
  assert.equal(workplaceLabel('In office'), 'On-site');
  assert.equal(workplaceLabel(''), null);
  assert.equal(workplaceLabel(null), null);
});

test('postedLabel: uses the publish date, falls back to when we first saw it', () => {
  const now = new Date('2026-10-22T12:00:00Z');
  assert.equal(postedLabel(job({ publishedAt: '2026-10-22T06:00:00Z' }), now), 'Posted today');
  assert.equal(postedLabel(job({ publishedAt: '2026-10-21T06:00:00Z' }), now), 'Posted yesterday');
  assert.equal(postedLabel(job({ firstSeenAt: '2026-10-18T06:00:00Z' }), now), 'Posted 4 days ago');
  assert.equal(postedLabel(job({ publishedAt: '2026-10-05T06:00:00Z' }), now), 'Posted 2 weeks ago');
  assert.equal(postedLabel(job({ publishedAt: '2026-08-01T06:00:00Z' }), now), 'Posted over a month ago');
  assert.equal(postedLabel(job({ publishedAt: null, firstSeenAt: null }), now), null);
});

test('safeLink: only http and https links from a job feed are used', () => {
  assert.equal(safeLink('https://jobs.lever.co/x'), 'https://jobs.lever.co/x');
  assert.equal(safeLink('http://example.com/a'), 'http://example.com/a');
  assert.equal(safeLink('javascript:alert(1)'), null);
  assert.equal(safeLink('  JavaScript:alert(1)'), null);
  assert.equal(safeLink('data:text/html,hi'), null);
  assert.equal(safeLink('/relative'), null);
  assert.equal(safeLink(''), null);
  assert.equal(safeLink(null), null);
});

test('statuses: the tracking steps in order, with readable labels', () => {
  assert.deepEqual(SAVED_STATUSES.map((s) => s.value), ['SAVED', 'APPLIED', 'INTERVIEW', 'OFFER', 'REJECTED']);
  assert.equal(statusLabel('INTERVIEW'), 'Interviewing');
  assert.equal(statusLabel('SAVED'), 'Saved');
  assert.equal(statusLabel('SOMETHING_NEW'), 'Something new');
});

test('groupSaved: one group per status in tracking order, newest change first, empty groups kept', () => {
  const saved = [
    { job: job({ id: 'a' }), status: 'APPLIED', updatedAt: '2026-10-20T00:00:00Z' },
    { job: job({ id: 'b' }), status: 'SAVED', updatedAt: '2026-10-19T00:00:00Z' },
    { job: job({ id: 'c' }), status: 'APPLIED', updatedAt: '2026-10-21T00:00:00Z' },
  ];

  const groups = groupSaved(saved);

  assert.deepEqual(groups.map((g) => [g.status, g.items.map((i) => i.job.id)]), [
    ['SAVED', ['b']],
    ['APPLIED', ['c', 'a']],
    ['INTERVIEW', []],
    ['OFFER', []],
    ['REJECTED', []],
  ]);
  assert.equal(groups[1].label, 'Applied');
});

test('emptyState: says why the list is empty, or null when there are jobs', () => {
  assert.equal(emptyState({ resumeId: 'r1', openJobs: 0, jobs: [] }), 'no-open-jobs');
  assert.equal(emptyState({ resumeId: null, openJobs: 0, jobs: [] }), 'no-open-jobs');
  assert.equal(emptyState({ resumeId: 'r1', openJobs: 40, jobs: [] }), 'no-results');
  assert.equal(emptyState({ resumeId: 'r1', openJobs: 40, jobs: [{}] }), null);
});

test('isRanked: without a resume the jobs come back unranked, newest first', () => {
  assert.equal(isRanked({ resumeId: null, jobs: [{}] }), false);
  assert.equal(isRanked({ resumeId: 'r1', jobs: [{}] }), true);
});

test('employmentLabel: feed spellings become one readable form', () => {
  assert.equal(employmentLabel('full-time'), 'Full-time');
  assert.equal(employmentLabel('FullTime'), 'Full-time');
  assert.equal(employmentLabel('Full Time'), 'Full-time');
  assert.equal(employmentLabel('part_time'), 'Part-time');
  assert.equal(employmentLabel('Intern'), 'Internship');
  assert.equal(employmentLabel('contract'), 'Contract');
  assert.equal(employmentLabel('Permanent'), 'Permanent');
  assert.equal(employmentLabel(''), null);
});

test('locationLabel: one location when a feed lists the same place several ways', () => {
  assert.equal(locationLabel('Bangalore · Bangalore, Karnataka, India'), 'Bangalore, Karnataka, India');
  assert.equal(locationLabel('India · Bangalore, Karnataka, India'), 'Bangalore, Karnataka, India');
  assert.equal(locationLabel('Bengaluru, India · Bengaluru-VTP, India'), 'Bengaluru, India');
  assert.equal(locationLabel('Hybrid in Bangalore, India · Hybrid in Bengaluru, India'), 'Hybrid in Bangalore, India');
  assert.equal(locationLabel('Mumbai / Bangalore; Bangalore'), 'Mumbai / Bangalore');
  assert.equal(locationLabel('Bangalore'), 'Bangalore');
  assert.equal(locationLabel(''), null);
  assert.equal(locationLabel(null), null);
});

test('isNewJob: open jobs first seen in the last 7 days are new', () => {
  const now = new Date('2026-10-22T12:00:00Z');
  const seen = (firstSeenAt, active = true) => ({ firstSeenAt, active });
  assert.equal(isNewJob(seen('2026-10-22T09:00:00Z'), now), true);
  assert.equal(isNewJob(seen('2026-10-15T12:00:01Z'), now), true);
  assert.equal(isNewJob(seen('2026-10-15T12:00:00Z'), now), false, 'exactly 7 days old is no longer new');
  assert.equal(isNewJob(seen('2026-10-01T00:00:00Z'), now), false);
  assert.equal(isNewJob(seen('2026-10-22T09:00:00Z', false), now), false, 'a closed job is never new');
  assert.equal(isNewJob(seen(null), now), false);
  assert.equal(
    isNewJob({ ...seen('2026-10-01T00:00:00Z'), publishedAt: '2026-10-21T00:00:00Z' }, now),
    false,
    'uses firstSeenAt, not publishedAt',
  );
});
