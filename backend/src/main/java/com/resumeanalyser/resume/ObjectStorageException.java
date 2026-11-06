package com.resumeanalyser.resume;

/**
 * Wraps any failure talking to the underlying object store (MinIO/S3) --
 * network errors, a missing object, a rejected request -- behind one
 * unchecked type, so callers don't need to know the storage SDK's checked
 * exception hierarchy.
 */
public class ObjectStorageException extends RuntimeException {

    public ObjectStorageException(String message, Throwable cause) {
        super(message, cause);
    }
}
