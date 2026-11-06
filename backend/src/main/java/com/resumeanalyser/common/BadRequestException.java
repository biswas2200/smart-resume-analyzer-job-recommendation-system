package com.resumeanalyser.common;

/**
 * A request value that passes the body's annotations but still makes no
 * sense, such as a "website" that isn't a web address. Answered with 400 by
 * {@link GlobalExceptionHandler}; the message says what was wrong.
 */
public class BadRequestException extends RuntimeException {

    /** @param message safe to show the user */
    public BadRequestException(String message) {
        super(message);
    }
}
