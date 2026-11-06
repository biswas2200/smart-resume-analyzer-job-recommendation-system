package com.resumeanalyser.resume;

import com.resumeanalyser.client.MlServiceException;
import com.resumeanalyser.common.ApiError;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * Turns exceptions specific to the resume module into clean JSON error responses.
 * Scoped to only this package, per the module-boundary convention (see
 * {@code com.resumeanalyser.auth.AuthExceptionHandler} for the original example).
 * {@code @Order(HIGHEST_PRECEDENCE)} makes sure this always wins over
 * {@code GlobalExceptionHandler}'s unscoped catch-all for exceptions this
 * class knows how to handle -- without it, Spring doesn't guarantee a more
 * specific/scoped {@code @RestControllerAdvice} is tried before a less
 * specific one, so a module's own exceptions could silently fall through to
 * the generic 500 handler depending on bean registration order.
 */
@RestControllerAdvice(basePackages = "com.resumeanalyser.resume")
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ResumeExceptionHandler {

    /**
     * Handles a file that failed this module's own validation (empty, too large).
     *
     * @param e the thrown exception, whose message is reused as the response message
     * @return a 400 Bad Request response
     */
    @ExceptionHandler(InvalidResumeFileException.class)
    public ResponseEntity<ApiError> handleInvalidFile(InvalidResumeFileException e) {
        return errorResponse(HttpStatus.BAD_REQUEST, e.getMessage());
    }

    /**
     * Handles a failure calling the ML service -- it rejected the file's
     * format (415), its LLM provider was unavailable for an analysis
     * (503, passed through so the client can say "try again later"), or it
     * was unreachable/errored (502, since that's this backend's fault for
     * depending on a service that's currently down, not the caller's).
     *
     * @param e the thrown exception
     * @return a 415, 503 or 502 response, depending on
     *         {@link MlServiceException#isUnsupportedFileType()} and
     *         {@link MlServiceException#isLlmUnavailable()}
     */
    @ExceptionHandler(MlServiceException.class)
    public ResponseEntity<ApiError> handleMlServiceFailure(MlServiceException e) {
        HttpStatus status = e.isUnsupportedFileType() ? HttpStatus.UNSUPPORTED_MEDIA_TYPE
                : e.isLlmUnavailable() ? HttpStatus.SERVICE_UNAVAILABLE
                : HttpStatus.BAD_GATEWAY;
        return errorResponse(status, e.getMessage());
    }

    /**
     * Handles a failure talking to the object store (MinIO/S3) -- same
     * reasoning as {@link #handleMlServiceFailure}: an external dependency
     * being down is this backend's problem, not the caller's, so it's a 502
     * rather than a 500 or 400.
     *
     * @param e the thrown exception
     * @return a 502 Bad Gateway response
     */
    @ExceptionHandler(ObjectStorageException.class)
    public ResponseEntity<ApiError> handleObjectStorageFailure(ObjectStorageException e) {
        return errorResponse(HttpStatus.BAD_GATEWAY, "The resume storage service is currently unavailable");
    }

    private ResponseEntity<ApiError> errorResponse(HttpStatus status, String message) {
        return ResponseEntity.status(status).body(ApiError.of(status.value(), message));
    }
}
