import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  atsChange,
  checkSummary,
  describeChange,
  describeCheck,
  findNewMatches,
  initials,
  jdVerdict,
  nextSteps,
  paragraphs,
  scoreBand,
  scorePercent,
} from '../src/js/pages/insights.js';

const check = (name, passed, detail = '') => ({ name, passed, detail });
const role = (id, title, missingSkills = [], matchScore = 0.8) => ({
  recommendationId: `rec-${id}`,
  role: { id, title, description: '' },
  matchScore,
  matchedSkills: [],
  missingSkills,
});
const dashboard = (checks, recommendations = [], overrides = {}) => ({
  resumeId: 'r1',
  atsScore: { score: 70, max_score: 100, checks },
  recommendations,
  recommendationsLocked: false,
  ...overrides,
});

test('describeCheck: a passed check earns its weight and needs no fix', () => {
  assert.deepEqual(describeCheck(check('section_skills', true)), {
    label: 'Skills section',
    status: 'pass',
    earned: 15,
    weight: 15,
    fix: null,
  });
});

test('describeCheck: a failed check earns nothing and says how to fix it', () => {
  const view = describeCheck(check('contact_phone', false));
  assert.equal(view.status, 'fail');
  assert.equal(view.earned, 0);
  assert.match(view.fix, /phone number/);
});

test('describeCheck: keyword coverage earns its share and is partial below half', () => {
  const view = describeCheck(check('keyword_coverage', false, '6/20 target keywords found in resume'));
  assert.equal(view.status, 'partial');
  assert.equal(view.earned, 6);
  assert.ok(view.fix);
  assert.equal(describeCheck(check('keyword_coverage', false, '0/20 target keywords')).status, 'fail');
  assert.equal(describeCheck(check('keyword_coverage', true, '13/20 target keywords')).earned, 13);
});

test('describeCheck: an unknown check gets a readable label and no points', () => {
  assert.deepEqual(describeCheck(check('new_rule', false)), {
    label: 'New rule',
    status: 'fail',
    earned: null,
    weight: null,
    fix: null,
  });
});

test('checkSummary counts passes and the points still to gain', () => {
  const summary = checkSummary([
    check('contact_email', true),
    check('section_skills', false),
    check('keyword_coverage', true, '15/20 target keywords'),
  ]);
  assert.deepEqual(summary, { passed: 2, total: 3, toGain: 20 });
});

test('scorePercent and scoreBand', () => {
  assert.equal(scorePercent(78, 100), 78);
  assert.equal(scorePercent(5, 0), 0);
  assert.deepEqual(scoreBand(85, 100), { label: 'Strong', tone: 'good' });
  assert.deepEqual(scoreBand(65, 100), { label: 'Good', tone: 'ok' });
  assert.deepEqual(scoreBand(45, 100), { label: 'Needs work', tone: 'warn' });
  assert.deepEqual(scoreBand(10, 100), { label: 'Weak', tone: 'bad' });
});

test('nextSteps: costliest fixes first, then skills for the best match', () => {
  const steps = nextSteps(
    dashboard(
      [check('contact_phone', false), check('section_skills', false), check('sufficient_length', false)],
      [role('a', 'Data Analyst', ['Power BI', 'dbt', 'Airflow'], 0.86)],
    ),
  );
  assert.equal(steps.length, 3);
  assert.match(steps[0], /Skills/);
  assert.match(steps[2], /Power BI and dbt.*Data Analyst \(86%\)/);
});

test('nextSteps: skips locked matches and has a fallback when all is well', () => {
  const locked = dashboard([check('contact_email', true)], [role('a', 'X', ['Y'])], { recommendationsLocked: true });
  assert.equal(nextSteps(locked).length, 1);
  assert.match(nextSteps(locked)[0], /Every check passes/);
});

test('paragraphs splits on blank lines, else on lines', () => {
  assert.deepEqual(paragraphs('One.\n\nTwo.'), ['One.', 'Two.']);
  assert.deepEqual(paragraphs('One.\nTwo.'), ['One.', 'Two.']);
  assert.deepEqual(paragraphs('  '), []);
  assert.deepEqual(paragraphs(null), []);
});

test('jdVerdict bands', () => {
  assert.equal(jdVerdict(0.82).label, 'Strong match');
  assert.equal(jdVerdict(0.5).label, 'Partial match');
  assert.equal(jdVerdict(0.1).label, 'Weak match');
});

test('findNewMatches: nothing is new on the first visit', () => {
  const { fresh, remember } = findNewMatches([role('a', 'A')], null);
  assert.deepEqual(fresh, []);
  assert.deepEqual(remember, ['a']);
});

test('findNewMatches: roles not seen before are new', () => {
  const { fresh } = findNewMatches([role('a', 'A'), role('b', 'B')], ['a']);
  assert.deepEqual(fresh.map((r) => r.role.id), ['b']);
});

test('atsChange compares with the previous version, not a reload of the same one', () => {
  const first = atsChange(null, 'r1', 63);
  assert.equal(first.delta, null);
  const second = atsChange(first.record, 'r2', 71);
  assert.equal(second.delta, 8);
  const reload = atsChange(second.record, 'r2', 71);
  assert.equal(reload.delta, 8);
});

test('describeChange wording', () => {
  assert.equal(describeChange(null), '');
  assert.equal(describeChange(0), 'Same as your previous version.');
  assert.equal(describeChange(7), 'Up 7 points since your previous version.');
  assert.equal(describeChange(-1), 'Down 1 point since your previous version.');
});

test('initials from an email', () => {
  assert.equal(initials('priya.nair@example.com'), 'PN');
  assert.equal(initials('sam@example.com'), 'SA');
  assert.equal(initials(undefined), '?');
});
