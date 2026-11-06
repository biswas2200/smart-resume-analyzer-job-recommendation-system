package com.resumeanalyser.common;

import java.time.Instant;
import java.util.List;

/**
 * The single, uniform error-response shape returned by every failed API call
 * in this app -- used by both {@link GlobalExceptionHandler} and each module's
 * own scoped exception handler (e.g. {@code AuthExceptionHandler}), so a
 * client only ever has to parse one error format.
 *
 * @param timestamp   when the error occurred
 * @param status      the HTTP status code, duplicated here (in addition to the actual HTTP status)
 *                     so the status is visible even if the body is logged/inspected on its own
 * @param message     a human-readable summary of what went wrong -- always safe to show a stranger;
 *                     never the raw exception message for an unexpected failure (see {@code traceId})
 * @param fieldErrors per-field validation failures (e.g. "email: must be a well-formed email address");
 *                     null when the error isn't about individual request fields
 * @param traceId     a random id correlating this response with the full stack trace in the
 *                     server logs, so support can debug an unexpected failure from a user's
 *                     support request without the client ever seeing internal detail; null for
 *                     expected/handled errors (validation, not-found, bad credentials, ...)
 *                     where the message is already self-explanatory and there's nothing to look up
 */
public record ApiError(
        Instant timestamp,
        int status,
        String message,
        List<String> fieldErrors,
        String traceId
) {

    /**
     * Builds an error with no field-level detail and no trace id -- for expected,
     * self-explanatory failures (e.g. wrong credentials, a duplicate email).
     *
     * @param status  the HTTP status code
     * @param message the error message
     * @return a new ApiError, timestamped now
     */
    public static ApiError of(int status, String message) {
        return new ApiError(Instant.now(), status, message, null, null);
    }

    /**
     * Builds an error that also lists which request fields failed validation.
     *
     * @param status      the HTTP status code
     * @param message     the overall error message
     * @param fieldErrors the individual field validation failures
     * @return a new ApiError, timestamped now
     */
    public static ApiError of(int status, String message, List<String> fieldErrors) {
        return new ApiError(Instant.now(), status, message, fieldErrors, null);
    }

    /**
     * Builds an error for an unexpected failure, carrying a trace id the client can
     * quote back to support instead of any internal detail about what actually broke.
     *
     * @param status  the HTTP status code
     * @param message a generic, safe-to-show message (must not include {@code cause}'s own message)
     * @param traceId the id also written to the server log line for this failure
     * @return a new ApiError, timestamped now
     */
    public static ApiError ofUnexpected(int status, String message, String traceId) {
        return new ApiError(Instant.now(), status, message, null, traceId);
    }
}
