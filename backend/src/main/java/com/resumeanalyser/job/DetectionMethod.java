package com.resumeanalyser.job;

/** How a company's job feed was found, strongest evidence first. */
public enum DetectionMethod {
    /** The careers link itself points at the hiring tool (e.g. jobs.lever.co/acme). */
    CAREERS_URL,
    /** The feed exists under the website's name (groww.in -> groww). */
    DOMAIN_SLUG,
    /** The feed exists under a slug made from the company name; worth a check. */
    NAME_SLUG
}
