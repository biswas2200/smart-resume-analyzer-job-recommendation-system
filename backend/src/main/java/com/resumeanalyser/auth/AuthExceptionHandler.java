package com.resumeanalyser.auth;

import com.resumeanalyser.common.ApiError;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Turns exceptions specific to the auth module into clean JSON error responses.
 * Scoped to only this package ({@code basePackages}), so it never intercepts
 * exceptions from other modules -- those fall through to
 * {@link com.resumeanalyser.common.GlobalExceptionHandler} instead.
 * {@code @Order(HIGHEST_PRECEDENCE)} makes sure this always wins over that
 * unscoped catch-all -- without it, Spring breaks ties between equally
 * unordered {@code @RestControllerAdvice} beans by class name, so whether a
 * module's own handler actually fires depends on whether its class name
 * happens to sort before "GlobalExceptionHandler" alphabetically. That's how
 * this one worked by accident while {@code ResumeExceptionHandler} didn't.
 */
@RestControllerAdvice(basePackages = "com.resumeanalyser.auth")
@Order(Ordered.HIGHEST_PRECEDENCE)
public class AuthExceptionHandler {

    /**
     * Handles a registration attempt with an email that's already taken.
     *
     * @param e the thrown exception, whose message is reused as the response message
     * @return a 409 Conflict response
     */
    @ExceptionHandler(EmailAlreadyInUseException.class)
    public ResponseEntity<ApiError> handleEmailAlreadyInUse(EmailAlreadyInUseException e) {
        return errorResponse(HttpStatus.CONFLICT, e.getMessage());
    }

    /**
     * Handles a failed login attempt (wrong email or wrong password).
     * The response message is deliberately generic -- it never reveals which
     * of the two was wrong, so an attacker can't use it to enumerate valid emails.
     *
     * @param e the exception Spring Security throws for any failed credential check
     * @return a 401 Unauthorized response
     */
    @ExceptionHandler(BadCredentialsException.class)
    public ResponseEntity<ApiError> handleBadCredentials(BadCredentialsException e) {
        return errorResponse(HttpStatus.UNAUTHORIZED, "Invalid email or password");
    }

    /**
     * Builds the shared error response shape for both handlers above.
     *
     * @param status  the HTTP status to respond with
     * @param message the human-readable error message
     * @return a ready-to-return error response
     */
    private ResponseEntity<ApiError> errorResponse(HttpStatus status, String message) {
        return ResponseEntity.status(status).body(ApiError.of(status.value(), message));
    }
}
