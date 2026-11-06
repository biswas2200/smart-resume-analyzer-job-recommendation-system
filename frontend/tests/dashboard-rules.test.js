import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  asPercent,
  canMatchJd,
  canUnlock,
  demandChipLabel,
  demandFor,
  demandHeading,
  isLlmExplanation,
} from '../src/js/pages/dashboard-rules.js';

const locked = (overrides) => ({
  resumeId: 'r1',
  recommendationsLocked: true,
  lockReason: 'ai_budget_exhausted',
  ...overrides,
});

test('canUnlock: nothing to unlock when not locked or no resume', () => {
  assert.equal(canUnlock(locked({ recommendationsLocked: false })), false);
  assert.equal(canUnlock(locked({ resumeId: undefined })), false);
});

test('canUnlock: a locked result can be re-run, except in the Community Edition', () => {
  assert.equal(canUnlock(locked({ lockReason: 'ai_budget_exhausted' })), true);
  assert.equal(canUnlock(locked({ lockReason: null })), true, 'a result locked under an older reason');
  assert.equal(canUnlock(locked({ lockReason: 'community_edition' })), false);
});

test('isLlmExplanation treats a missing source as the template', () => {
  assert.equal(isLlmExplanation({ explanationSource: 'llm' }), true);
  assert.equal(isLlmExplanation({ explanationSource: 'template' }), false);
  assert.equal(isLlmExplanation({}), false);
});

test('canMatchJd needs only an analysed resume', () => {
  assert.equal(canMatchJd({ resumeId: 'r1' }), true);
  assert.equal(canMatchJd({}), false);
});

test('asPercent rounds a score to a whole percent', () => {
  assert.equal(asPercent(0.876), 88);
});

test('demandFor: the role measured by title, or null when there is nothing to show', () => {
  const inDemand = {
    roles: [
      { role: 'Backend Engineer', jobCount: 14, skills: [{ skill: 'Java', share: 0.62, have: true }] },
      { role: 'DevOps Engineer', jobCount: 0, computedAt: null, skills: [] },
      { role: 'Data Engineer', jobCount: 3, skills: [] },
    ],
  };
  assert.equal(demandFor(inDemand, 'Backend Engineer').jobCount, 14);
  assert.equal(demandFor(inDemand, 'DevOps Engineer'), null, 'too few jobs to say');
  assert.equal(demandFor(inDemand, 'Data Engineer'), null, 'no skills');
  assert.equal(demandFor(inDemand, 'Product Manager'), null, 'not measured');
  assert.equal(demandFor({ roles: [] }, 'Backend Engineer'), null);
  assert.equal(demandFor(undefined, 'Backend Engineer'), null);
});

test('demandChipLabel and demandHeading read plainly', () => {
  assert.equal(demandChipLabel({ skill: 'Python', share: 0.624 }), 'Python · 62%');
  assert.equal(demandChipLabel({ skill: 'Go' }), 'Go · 0%');
  assert.equal(demandHeading(14), 'What 14 open jobs for this role ask for');
  assert.equal(demandHeading(1), 'What 1 open job for this role asks for');
});
