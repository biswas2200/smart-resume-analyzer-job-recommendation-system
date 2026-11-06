package com.resumeanalyser.resume;

import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.util.UUID;

/**
 * Writes uploaded resume files to object storage (MinIO locally, S3-compatible
 * anywhere else) under a key unique to the uploading user and version, and
 * reads them back for re-analysis. {@link Resume#getFileRef()} only ever
 * stores the key this class hands back, never the file bytes themselves.
 */
@Service
public class ResumeStorageService {

    private final MinioClient minioClient;
    private final String bucket;

    public ResumeStorageService(MinioClient minioClient, @Value("${app.storage.bucket}") String bucket) {
        this.minioClient = minioClient;
        this.bucket = bucket;
    }

    /** Creates the resume bucket on startup if it doesn't already exist. */
    @PostConstruct
    void ensureBucketExists() {
        try {
            boolean exists = minioClient.bucketExists(BucketExistsArgs.builder().bucket(bucket).build());
            if (!exists) {
                minioClient.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
            }
        } catch (Exception e) {
            throw new ObjectStorageException("Failed to ensure the resume bucket exists: " + bucket, e);
        }
    }

    /**
     * Saves an uploaded resume's bytes under a key unique to this user and version.
     *
     * @param userId   the uploading account's id
     * @param version  this upload's version number (see {@link Resume#getVersion()})
     * @param filename the original filename, kept as a suffix for readability
     * @param bytes    the file's raw contents
     * @return the object key the bytes were written to, stored as {@link Resume#getFileRef()}
     */
    public String store(UUID userId, int version, String filename, byte[] bytes) {
        String safeFilename = filename == null || filename.isBlank() ? "resume" : filename;
        String objectKey = userId + "/" + version + "-" + safeFilename;
        try {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(objectKey)
                    .stream(new ByteArrayInputStream(bytes), bytes.length, -1)
                    .build());
            return objectKey;
        } catch (Exception e) {
            throw new ObjectStorageException("Failed to store resume file: " + objectKey, e);
        }
    }

    /**
     * Reads back the bytes of a previously stored resume file.
     *
     * @param fileRef the object key returned by a previous {@link #store} call
     * @return the file's raw contents
     */
    public byte[] read(String fileRef) {
        try (InputStream is = minioClient.getObject(GetObjectArgs.builder()
                .bucket(bucket)
                .object(fileRef)
                .build())) {
            return is.readAllBytes();
        } catch (Exception e) {
            throw new ObjectStorageException("Failed to read stored resume file: " + fileRef, e);
        }
    }
}
