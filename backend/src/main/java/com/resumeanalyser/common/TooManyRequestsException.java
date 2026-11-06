package com.resumeanalyser.common;

import java.time.Duration;

/**
 * A user made too many requests of one kind in a short time. Answered with
 * 429 Too Many Requests and a {@code Retry-After} header by
 * {@link GlobalExceptionHandler}.
 */
public class TooManyRequestsException extends RuntimeException {

    private final Duration retryAfter;

    /**
     * @param message    safe to show the user
     * @param retryAfter how long until the next request would be accepted
     */
    public TooManyRequestsException(String message, Duration retryAfter) {
        super(message);
        this.retryAfter = retryAfter;
    }

    public Duration getRetryAfter() {
        return retryAfter;
    }
}
