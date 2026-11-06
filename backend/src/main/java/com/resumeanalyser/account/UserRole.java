package com.resumeanalyser.account;

/**
 * The access levels an account can have, used for role-based access control (RBAC).
 * Named UserRole rather than "Role" so it can't be confused with
 * {@link com.resumeanalyser.recommendation.Role}, which represents a job role
 * (e.g. "Backend Software Engineer") and is a completely different concept.
 */
public enum UserRole {

    /** Default role for every newly registered account. */
    USER,

    /** Full administrative access. */
    ADMIN
}
