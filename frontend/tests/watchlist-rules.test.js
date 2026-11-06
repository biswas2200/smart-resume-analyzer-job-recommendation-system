import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  addCompanyRequest,
  addedMessage,
  applyAction,
  avatarTone,
  boardLink,
  capLabel,
  cardStatusBadge,
  companyInitials,
  companyStatusBadge,
  isFull,
  isSearchable,
  newJobsLabel,
  normalizeFilter,
  openJobsLabel,
  resultsLabel,
  websiteUrl,
} from '../src/js/pages/watchlist-rules.js';

test('addCompanyRequest trims the form and leaves out an empty careers link', () => {
  assert.deepEqual(addCompanyRequest({ name: ' Acme ', website: ' acme.com ', careersUrl: '  ' }), {
    body: { name: 'Acme', website: 'acme.com' },
  });
  assert.deepEqual(
    addCompanyRequest({ name: 'Acme', website: 'https://acme.com', careersUrl: 'https://jobs.lever.co/acme' }),
    { body: { name: 'Acme', website: 'https://acme.com', careersUrl: 'https://jobs.lever.co/acme' } },
  );
});

test('addCompanyRequest catches a missing name or a plainly wrong website', () => {
  assert.equal(addCompanyRequest({ name: '', website: 'acme.com' }).error, "Enter the company's name.");
  for (const website of ['', 'acme', 'acme dot com', 'acme .com']) {
    assert.equal(addCompanyRequest({ name: 'Acme', website }).error, 'Enter its website, e.g. acme.com', website);
  }
});

test('addedMessage says whether we found the jobs', () => {
  assert.equal(addedMessage({ name: 'Acme', status: 'ACTIVE' }), 'Watching Acme. We found its jobs.');
  assert.match(addedMessage({ name: 'Acme', status: 'UNSUPPORTED' }), /couldn't find its jobs/);
});

test('capLabel shows how much of the cap is used, once the cap is known', () => {
  assert.equal(capLabel(3, 25), '3 of 25 companies watched');
  assert.equal(capLabel(0, 25), '0 of 25 companies watched');
  assert.equal(capLabel(3, null), null);
});

test('isFull is true only at or over a known cap', () => {
  assert.equal(isFull(24, 25), false);
  assert.equal(isFull(25, 25), true);
  assert.equal(isFull(30, 25), true);
  assert.equal(isFull(30, null), false);
});

test('companyStatusBadge says whether we can read the company\'s jobs', () => {
  assert.deepEqual(companyStatusBadge('ACTIVE'), { label: 'Jobs tracked', tone: 'green' });
  assert.equal(companyStatusBadge('UNSUPPORTED').tone, 'amber');
  assert.equal(companyStatusBadge('PENDING').label, 'Checking for jobs');
  assert.equal(companyStatusBadge(undefined).label, 'Checking for jobs');
});

test('openJobsLabel counts open jobs and hides zero', () => {
  assert.equal(openJobsLabel(0), null);
  assert.equal(openJobsLabel(undefined), null);
  assert.equal(openJobsLabel(1), '1 open job');
  assert.equal(openJobsLabel(12), '12 open jobs');
});

test('newJobsLabel shows the New badge only when something is new', () => {
  assert.equal(newJobsLabel(0), null);
  assert.equal(newJobsLabel(3), '3 new');
});

test('isSearchable needs two letters after trimming', () => {
  assert.equal(isSearchable(' g '), false);
  assert.equal(isSearchable(null), false);
  assert.equal(isSearchable('gr'), true);
});

test('companyInitials: one letter for one word, two for more, "?" for nothing usable', () => {
  assert.equal(companyInitials('Groww'), 'G');
  assert.equal(companyInitials('meesho pvt ltd'), 'MP');
  assert.equal(companyInitials('  3one4 Capital '), '3C');
  assert.equal(companyInitials('★'), '?');
  assert.equal(companyInitials(undefined), '?');
});

test('avatarTone is stable per name and always one of six', () => {
  assert.equal(avatarTone('Groww'), avatarTone('Groww'));
  for (const name of ['Groww', 'CRED', 'Meesho', '', '56 Secure']) {
    const tone = avatarTone(name);
    assert.ok(Number.isInteger(tone) && tone >= 0 && tone < 6, `${name} -> ${tone}`);
  }
});

test('cardStatusBadge: open jobs win, then the tracking status, with a careers page noted', () => {
  assert.deepEqual(cardStatusBadge({ openJobs: 3, status: 'ACTIVE' }), { label: 'Hiring now', tone: 'green' });
  assert.deepEqual(cardStatusBadge({ openJobs: 0, status: 'ACTIVE' }), { label: 'No open jobs right now', tone: '' });
  assert.equal(cardStatusBadge({ openJobs: 0, status: 'UNSUPPORTED', careersUrl: 'https://x.com/jobs' }).label, 'Careers page only');
  assert.equal(cardStatusBadge({ openJobs: 0, status: 'UNSUPPORTED' }).label, 'Jobs not tracked yet');
  assert.equal(cardStatusBadge({ openJobs: 0, status: 'PENDING' }).label, 'Checking for jobs');
});

test('applyAction: the Jobs page for open jobs, else careers page, else website, else nothing', () => {
  assert.deepEqual(applyAction({ name: 'Meesho', domain: 'meesho.com', openJobs: 12 }), {
    kind: 'jobs',
    label: 'View 12 jobs',
    href: 'jobs.html?q=Meesho',
  });
  assert.equal(applyAction({ name: 'A & B', openJobs: 1 }).href, 'jobs.html?q=A+%26+B');
  assert.equal(applyAction({ name: 'A', openJobs: 1 }).label, 'View 1 job');
  assert.deepEqual(applyAction({ name: 'Acme', domain: 'acme.com', openJobs: 0, careersUrl: 'https://acme.com/careers' }), {
    kind: 'external',
    label: 'Careers page',
    href: 'https://acme.com/careers',
  });
  assert.deepEqual(applyAction({ name: 'Acme', domain: 'acme.com', openJobs: 0, careersUrl: null }), {
    kind: 'external',
    label: 'Visit website',
    href: 'https://acme.com',
  });
  assert.equal(applyAction({ name: 'Acme', domain: '', openJobs: 0 }), null);
});

test('applyAction never produces a link that is not http(s)', () => {
  const action = applyAction({ name: 'Evil', domain: 'evil.com', openJobs: 0, careersUrl: 'javascript:alert(1)' });
  assert.equal(action.href, 'https://evil.com');
  assert.equal(websiteUrl('not a domain'), null);
  assert.equal(websiteUrl('nodots'), null);
});

test('resultsLabel and normalizeFilter', () => {
  assert.equal(resultsLabel(24, 1085), 'Showing 24 of 1,085 companies');
  assert.equal(resultsLabel(1, 1), 'Showing 1 of 1 company');
  assert.equal(resultsLabel(0, 0), 'No companies match');
  assert.equal(normalizeFilter('hiring'), 'hiring');
  assert.equal(normalizeFilter('<script>'), 'all');
  assert.equal(normalizeFilter(undefined), 'all');
});

test('boardLink cuts a posting link back to the company board on the tools we know', () => {
  assert.equal(boardLink('https://jobs.lever.co/acceldata/c1d6cc81-a14e-4f22'), 'https://jobs.lever.co/acceldata');
  assert.equal(boardLink('https://jobs.ashbyhq.com/bureau/54c0efa8-d02e/application'), 'https://jobs.ashbyhq.com/bureau');
  assert.equal(boardLink('https://boards.greenhouse.io/groww/jobs/12345'), 'https://boards.greenhouse.io/groww');
  // Anything else is left alone, and so is a link with no board name.
  assert.equal(boardLink('https://acme.keka.com/careers/jobdetails/9'), 'https://acme.keka.com/careers/jobdetails/9');
  assert.equal(boardLink('https://jobs.lever.co/'), 'https://jobs.lever.co/');
  assert.equal(boardLink('not a url'), 'not a url');
});

test('applyAction sends a company with no open jobs to its board, not to one old posting', () => {
  const action = applyAction({ name: 'Acme', domain: 'acme.com', openJobs: 0, careersUrl: 'https://jobs.lever.co/acme/1c9f' });
  assert.equal(action.href, 'https://jobs.lever.co/acme');
});
