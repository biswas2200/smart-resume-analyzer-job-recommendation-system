package com.resumeanalyser.common;

/**
 * An outside service this request needs (e.g. GitHub) is not set up or did
 * not answer properly. Answered with 503 by {@link GlobalExceptionHandler};
 * the message says what failed, never a credential.
 */
public class ExternalServiceException extends RuntimeException {

    /** @param message safe to show an administrator */
    public ExternalServiceException(String message) {
        super(message);
    }
}
