package com.resumeanalyser.common;

import com.resumeanalyser.common.logging.RequestIdFilter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import java.util.List;
import java.util.UUID;

/**
 * Catches exceptions that aren't specific to any one module -- request-body
 * validation failures and "resource not found" -- plus a last-resort fallback
 * for anything unexpected, so the client always gets clean JSON instead of a
 * raw stack trace. Applies app-wide (no {@code basePackages} restriction).
 * Module-specific exceptions (e.g. auth's {@code EmailAlreadyInUseException})
 * are handled by that module's own scoped handler instead, never here.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /**
     * Handles a request body that failed its {@code @Valid} constraints
     * (e.g. a missing required field, a malformed email).
     *
     * @param e Spring's exception, carrying the list of individual field failures
     * @return a 400 Bad Request response listing every field that failed and why
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> handleValidation(MethodArgumentNotValidException e) {
        List<String> fieldErrors = e.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .toList();

        return ResponseEntity.badRequest()
                .body(ApiError.of(HttpStatus.BAD_REQUEST.value(), "Validation failed", fieldErrors));
    }

    /**
     * Handles a request for a record that doesn't exist.
     *
     * @param e the exception, whose message describes what wasn't found
     * @return a 404 Not Found response
     */
    /**
     * Handles a request body that couldn't be read at all -- malformed JSON,
     * or a value that isn't one of an enum's constants (e.g. an unknown role
     * name sent to {@code PATCH /admin/users/{id}/role}). That is the caller's
     * mistake, so it's a 400 like a validation failure, not a 500.
     */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> handleUnreadableBody(HttpMessageNotReadableException e) {
        return ResponseEntity.badRequest()
                .body(ApiError.of(HttpStatus.BAD_REQUEST.value(), "Request body is malformed or has an invalid value"));
    }

    /**
     * Handles a path or query value of the wrong type, e.g. {@code PUT /watchlist/not-a-uuid}.
     * That is the caller's mistake, so it's a 400, not a 500.
     */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> handleTypeMismatch(MethodArgumentTypeMismatchException e) {
        return ResponseEntity.badRequest()
                .body(ApiError.of(HttpStatus.BAD_REQUEST.value(), "Invalid value for '" + e.getName() + "'"));
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(ResourceNotFoundException e) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ApiError.of(HttpStatus.NOT_FOUND.value(), e.getMessage()));
    }

    /**
     * Handles a user making too many requests of one kind too quickly (e.g. watchlist
     * changes): 429, with {@code Retry-After} in whole seconds so a client knows when to retry.
     */
    @ExceptionHandler(TooManyRequestsException.class)
    public ResponseEntity<ApiError> handleTooManyRequests(TooManyRequestsException e) {
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .header(HttpHeaders.RETRY_AFTER, String.valueOf(e.getRetryAfter().toSeconds()))
                .body(ApiError.of(HttpStatus.TOO_MANY_REQUESTS.value(), e.getMessage()));
    }

    /** Handles a request value that makes no sense (e.g. a website that isn't a web address): 400. */
    @ExceptionHandler(BadRequestException.class)
    public ResponseEntity<ApiError> handleBadRequest(BadRequestException e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiError.of(HttpStatus.BAD_REQUEST.value(), e.getMessage()));
    }

    /** Handles a request that would take a user past a fixed allowance (e.g. the watchlist cap): 409. */
    @ExceptionHandler(LimitReachedException.class)
    public ResponseEntity<ApiError> handleLimitReached(LimitReachedException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiError.of(HttpStatus.CONFLICT.value(), e.getMessage()));
    }

    /** Handles a request that conflicts with the current state (e.g. a report already reviewed): 409. */
    @ExceptionHandler(ConflictException.class)
    public ResponseEntity<ApiError> handleConflict(ConflictException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiError.of(HttpStatus.CONFLICT.value(), e.getMessage()));
    }

    /** Handles an outside service that isn't set up or failed: 503. */
    @ExceptionHandler(ExternalServiceException.class)
    public ResponseEntity<ApiError> handleExternalService(ExternalServiceException e) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(ApiError.of(HttpStatus.SERVICE_UNAVAILABLE.value(), e.getMessage()));
    }

    /**
     * Handles a request rejected by a {@code @PreAuthorize} check (see
     * {@code SecurityConfig}'s {@code @EnableMethodSecurity}) -- the caller is
     * authenticated, just not allowed to perform this specific action. Without
     * this handler, such a rejection would otherwise fall through to
     * {@link #handleUnexpected} and incorrectly report a 500.
     *
     * @param e the exception Spring Security throws when a method-security check fails
     * @return a 403 Forbidden response
     */
    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ApiError> handleAccessDenied(AccessDeniedException e) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(ApiError.of(HttpStatus.FORBIDDEN.value(), "You do not have permission to perform this action"));
    }

    /**
     * Last-resort catch-all for any exception no more specific handler dealt with --
     * i.e. an actual bug, not an expected failure like bad credentials or a
     * duplicate email. Deliberately returns a generic message instead of
     * {@code e.getMessage()}, so internal error details (stack traces, SQL, file
     * paths) never reach the client. What the client gets instead is a random
     * trace id, logged here alongside the real stack trace -- so a user quoting
     * that id when asking for help is enough to find exactly what broke in the logs,
     * without ever exposing that detail over the API itself.
     *
     * @param e the unhandled exception; logged here in full (this is the one place
     *          in the app that logs a complete stack trace for it -- {@code LoggingAspect}
     *          only logs the exception's class and message, not its trace)
     * @return a 500 Internal Server Error response with a generic message and a trace id
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> handleUnexpected(Exception e) {
        // The request id doubles as the trace id, so the one id a user quotes
        // finds every log line for their request, not just this one.
        String requestId = MDC.get(RequestIdFilter.MDC_KEY);
        String traceId = requestId != null ? requestId : UUID.randomUUID().toString();
        log.error("Unhandled exception, traceId={}", traceId, e);

        return ResponseEntity.internalServerError()
                .body(ApiError.ofUnexpected(
                        HttpStatus.INTERNAL_SERVER_ERROR.value(),
                        "An unexpected error occurred. If this persists, please report it with trace id " + traceId,
                        traceId));
    }
}
