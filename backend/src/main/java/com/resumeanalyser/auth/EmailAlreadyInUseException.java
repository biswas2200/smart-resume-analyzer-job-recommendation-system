package com.resumeanalyser.auth;

/**
 * Thrown during registration when the submitted email is already tied to an existing account.
 * Caught by {@link AuthExceptionHandler} and turned into an HTTP 409 Conflict response.
 */
public class EmailAlreadyInUseException extends RuntimeException {

    /**
     * @param email the email that was already registered, included in the error message
     */
    public EmailAlreadyInUseException(String email) {
        super("Email already in use: " + email);
    }
}
