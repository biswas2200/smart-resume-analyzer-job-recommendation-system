package com.resumeanalyser.common;

/**
 * A request conflicts with the current state of what it acts on, such as
 * changing something that is already in its final state. Answered with 409
 * Conflict by {@link GlobalExceptionHandler}.
 */
public class ConflictException extends RuntimeException {

    /** @param message safe to show the user */
    public ConflictException(String message) {
        super(message);
    }
}
