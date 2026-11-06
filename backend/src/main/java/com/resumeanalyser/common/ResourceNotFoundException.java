package com.resumeanalyser.common;

/**
 * Thrown by any module when a requested record (by id, typically) doesn't exist.
 * Shared across modules rather than each module defining its own "not found"
 * exception, since {@link GlobalExceptionHandler} needs exactly one type to catch
 * and turn into a 404 response.
 */
public class ResourceNotFoundException extends RuntimeException {

    /**
     * @param message a human-readable description of what wasn't found (e.g. "Role not found: {id}")
     */
    public ResourceNotFoundException(String message) {
        super(message);
    }
}
