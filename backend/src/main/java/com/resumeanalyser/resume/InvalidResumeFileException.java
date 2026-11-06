package com.resumeanalyser.resume;

/**
 * Thrown when an uploaded file fails this module's own validation (empty file,
 * over the 5 MB limit per FR-1.3) -- before it's ever sent to the ML service.
 */
public class InvalidResumeFileException extends RuntimeException {

    public InvalidResumeFileException(String message) {
        super(message);
    }
}
