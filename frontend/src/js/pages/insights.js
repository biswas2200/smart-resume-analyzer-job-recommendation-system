// What the dashboard says about an analysis: how each ATS check reads and how to fix it, the
// score band, the next steps, new matches since the last visit and the score change since the
// previous version. Pure functions of the `GET /recommendations/dashboard` body (and of what
// this browser remembers), so tests/insights.test.js runs them under Node.

import { asPercent, isLocked } from './dashboard-rules.js';

/**
 * The ML service's ATS checks (ml-service/app/services/ats_score.py): a readable name, the
 * points each is worth there, and what to do when it fails. Keep the weights in step with
 * BASE_CHECK_WEIGHTS and KEYWORD_WEIGHT.
 */
export const CHECK_GUIDE = {
  contact_email: {
    label: 'Email address',
    weight: 15,
    fix: 'Put your email address in plain text at the top of the resume, not inside an image or a header graphic.',
  },
  contact_phone: {
    label: 'Phone number',
    weight: 10,
    fix: 'Add a phone number with the country code, for example +91 98450 12345, next to your email.',
  },
  section_experience: {
    label: 'Experience section',
    weight: 15,
    fix: 'Add a heading named "Experience" or "Work Experience" above your jobs, so screening software can find them.',
  },
  section_education: {
    label: 'Education section',
    weight: 15,
    fix: 'Add a heading named "Education" above your degrees and courses.',
  },
  section_skills: {
    label: 'Skills section',
    weight: 15,
    fix: 'Add a heading named "Skills" and list your tools and technologies under it, separated by commas.',
  },
  sufficient_length: {
    label: 'Length',
    weight: 10,
    fix: 'Your resume is under 150 words. Describe each role in 2 to 4 bullet points about what you achieved.',
  },
  no_hidden_text: {
    label: 'No hidden text',
    weight: 10,
    fix: 'Remove text a reader cannot see: white text, very small text or text placed off the page. Screening software treats it as keyword stuffing, and we ignored it.',
  },
  keyword_coverage: {
    label: 'Keywords for your target roles',
    weight: 20,
    fix: 'Work the missing skills from your top role matches into your experience bullets, wherever they are true.',
  },
};

/**
 * One ATS check as the dashboard shows it: `{ label, status, earned, weight, fix }`, where
 * status is `pass`, `partial` (keyword coverage between 0 and 50 %) or `fail`.
 */
export function describeCheck(check) {
  const guide = CHECK_GUIDE[check.name];
  const label = guide?.label ?? humanise(check.name);
  const weight = guide?.weight ?? null;

  let earned = weight === null ? null : check.passed ? weight : 0;
  let status = check.passed ? 'pass' : 'fail';
  const coverage = /^(\d+)\/(\d+)/.exec(check.detail ?? '');
  if (check.name === 'keyword_coverage' && coverage && Number(coverage[2]) > 0) {
    const share = Number(coverage[1]) / Number(coverage[2]);
    earned = Math.round(weight * share * 10) / 10;
    if (!check.passed && share > 0) {
      status = 'partial';
    }
  }
  return { label, status, earned, weight, fix: check.passed ? null : (guide?.fix ?? null) };
}

/** `{ passed, total, toGain }`: how many checks pass and the points the rest could add. */
export function checkSummary(checks) {
  let toGain = 0;
  for (const check of checks) {
    const { earned, weight } = describeCheck(check);
    if (weight !== null && earned !== null) {
      toGain += weight - earned;
    }
  }
  return {
    passed: checks.filter((check) => check.passed).length,
    total: checks.length,
    toGain: Math.round(toGain * 10) / 10,
  };
}

/** Score as a share of the maximum, 0 to 100. */
export function scorePercent(score, maxScore) {
  if (!(maxScore > 0)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((score / maxScore) * 100)));
}

/** `{ label, tone }` for a score; tone is good, ok, warn or bad (the CSS colour classes). */
export function scoreBand(score, maxScore) {
  const percent = scorePercent(score, maxScore);
  if (percent >= 80) {
    return { label: 'Strong', tone: 'good' };
  }
  if (percent >= 60) {
    return { label: 'Good', tone: 'ok' };
  }
  if (percent >= 40) {
    return { label: 'Needs work', tone: 'warn' };
  }
  return { label: 'Weak', tone: 'bad' };
}

/** "78" rather than "78.0"; scores arrive as doubles. */
export function formatScore(value) {
  return String(Math.round(value * 10) / 10);
}

/**
 * Up to three concrete things to do next: the fixes for the costliest failed checks, then the
 * skills that would strengthen the best role match.
 */
export function nextSteps(dashboard) {
  const steps = dashboard.atsScore.checks
    .map(describeCheck)
    .filter((check) => check.fix)
    .sort((a, b) => (b.weight ?? 0) - (b.earned ?? 0) - ((a.weight ?? 0) - (a.earned ?? 0)))
    .slice(0, 2)
    .map((check) => check.fix);

  const best = isLocked(dashboard) ? null : dashboard.recommendations[0];
  if (best && best.missingSkills.length > 0) {
    const skills = best.missingSkills.slice(0, 2).join(' and ');
    steps.push(`Learn ${skills} to strengthen your best match, ${best.role.title} (${asPercent(best.matchScore)}%).`);
  }
  if (steps.length === 0) {
    steps.push('Every check passes. Paste a job description into JD match to see how close you are to a specific role.');
  }
  return steps.slice(0, 3);
}

/** The coaching text as paragraphs: split on blank lines, or on lines if there are none. */
export function paragraphs(text) {
  const trimmed = (text ?? '').trim();
  if (!trimmed) {
    return [];
  }
  const separator = /\n\s*\n/.test(trimmed) ? /\n\s*\n/ : /\n/;
  return trimmed
    .split(separator)
    .map((part) => part.trim())
    .filter(Boolean);
}

/** A JD match at or above this score counts as strong. */
export const STRONG_MATCH = 0.7;

/** `{ label, tone }` over a JD match result. */
export function jdVerdict(score) {
  if (score >= STRONG_MATCH) {
    return { label: 'Strong match', tone: 'good' };
  }
  return score >= 0.4 ? { label: 'Partial match', tone: 'warn' } : { label: 'Weak match', tone: 'bad' };
}

/**
 * Splits the recommended roles into the ones this browser has not shown before. `seenRoleIds`
 * is null on the first visit, when nothing counts as new. Returns the new recommendations and
 * the ids to remember from now on.
 */
export function findNewMatches(recommendations, seenRoleIds) {
  const ids = recommendations.map((recommendation) => recommendation.role.id);
  if (!Array.isArray(seenRoleIds)) {
    return { fresh: [], remember: ids };
  }
  const seen = new Set(seenRoleIds);
  const fresh = recommendations.filter((recommendation) => !seen.has(recommendation.role.id));
  const remember = [...seenRoleIds.filter((id) => !ids.includes(id)), ...ids].slice(-200);
  return { fresh, remember };
}

/**
 * The ATS change since the previous resume version, from what this browser remembers
 * (`{ resumeId, score, previous }`). Returns the delta (null when there is nothing to compare)
 * and the record to remember.
 */
export function atsChange(remembered, resumeId, score) {
  if (!remembered || typeof remembered.score !== 'number') {
    return { delta: null, record: { resumeId, score, previous: null } };
  }
  if (remembered.resumeId === resumeId) {
    const previous = typeof remembered.previous === 'number' ? remembered.previous : null;
    return { delta: previous === null ? null : score - previous, record: { resumeId, score, previous } };
  }
  return { delta: score - remembered.score, record: { resumeId, score, previous: remembered.score } };
}

/** "Up 7 points since your previous version." */
export function describeChange(delta) {
  if (delta === null) {
    return '';
  }
  if (delta === 0) {
    return 'Same as your previous version.';
  }
  const points = Math.abs(delta) === 1 ? 'point' : 'points';
  return `${delta > 0 ? 'Up' : 'Down'} ${formatScore(Math.abs(delta))} ${points} since your previous version.`;
}

/** Two letters for the avatar, from the email's local part: "priya.nair@…" → "PN". */
export function initials(email) {
  const local = (email ?? '').split('@')[0];
  const parts = local.split(/[._\-+]+/).filter(Boolean);
  const letters = parts.length >= 2 ? parts[0][0] + parts[1][0] : local.slice(0, 2);
  return (letters || '?').toUpperCase();
}

/** "12 Oct" from an ISO timestamp. */
export function shortDate(iso) {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function humanise(name) {
  const text = String(name ?? '').replaceAll('_', ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}
