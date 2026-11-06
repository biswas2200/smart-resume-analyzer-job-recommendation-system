package com.resumeanalyser.common;

/**
 * A request would take a user past a fixed allowance, such as the most
 * companies one may watch. Answered with 409 Conflict by
 * {@link GlobalExceptionHandler}; the message says what to do instead.
 */
public class LimitReachedException extends RuntimeException {

    /** @param message safe to show the user */
    public LimitReachedException(String message) {
        super(message);
    }
}
