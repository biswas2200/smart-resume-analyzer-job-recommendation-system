package com.resumeanalyser.resume;

import io.minio.GetObjectArgs;
import io.minio.GetObjectResponse;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import okhttp3.Headers;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link ResumeStorageService}, the object-storage-backed
 * (MinIO/S3-compatible) implementation of resume file storage: bytes in,
 * bytes back out, under a key scoped to the uploading user and version, and
 * the one-time bucket bootstrap it does on startup.
 */
@ExtendWith(MockitoExtension.class)
class ResumeStorageServiceTest {

    private static final String BUCKET = "resumes";

    @Mock
    private MinioClient minioClient;

    private ResumeStorageService storageService;

    @BeforeEach
    void setUp() {
        storageService = new ResumeStorageService(minioClient, BUCKET);
    }

    @Test
    void store_writesTheFileUnderAKeyScopedToTheUserAndVersion() throws Exception {
        UUID userId = UUID.randomUUID();

        String key = storageService.store(userId, 2, "resume.pdf", "hello".getBytes());

        assertThat(key).isEqualTo(userId + "/2-resume.pdf");
        ArgumentCaptor<PutObjectArgs> captor = ArgumentCaptor.forClass(PutObjectArgs.class);
        verify(minioClient).putObject(captor.capture());
        assertThat(captor.getValue().bucket()).isEqualTo(BUCKET);
        assertThat(captor.getValue().object()).isEqualTo(key);
    }

    @Test
    void store_fallsBackToAGenericFilename_whenNoneWasGiven() {
        UUID userId = UUID.randomUUID();

        String key = storageService.store(userId, 1, null, "hi".getBytes());

        assertThat(key).isEqualTo(userId + "/1-resume");
    }

    @Test
    void store_wrapsAMinioFailureInAnObjectStorageException() throws Exception {
        when(minioClient.putObject(any())).thenThrow(new IOException("network down"));
        UUID userId = UUID.randomUUID();
        byte[] bytes = "x".getBytes();

        assertThatThrownBy(() -> storageService.store(userId, 1, "r.pdf", bytes))
                .isInstanceOf(ObjectStorageException.class)
                .hasCauseInstanceOf(IOException.class);
    }

    @Test
    void read_returnsTheStoredBytes() throws Exception {
        byte[] expected = "resume-bytes".getBytes();
        GetObjectResponse response = new GetObjectResponse(
                new Headers.Builder().build(), BUCKET, "us-east-1", "some/key",
                new ByteArrayInputStream(expected));
        when(minioClient.getObject(any(GetObjectArgs.class))).thenReturn(response);

        byte[] actual = storageService.read("some/key");

        assertThat(actual).isEqualTo(expected);
    }

    @Test
    void read_wrapsAMinioFailureInAnObjectStorageException() throws Exception {
        when(minioClient.getObject(any(GetObjectArgs.class))).thenThrow(new IOException("not found"));

        assertThatThrownBy(() -> storageService.read("missing/key"))
                .isInstanceOf(ObjectStorageException.class)
                .hasCauseInstanceOf(IOException.class);
    }

    @Test
    void ensureBucketExists_createsTheBucket_whenItDoesNotExistYet() throws Exception {
        when(minioClient.bucketExists(any())).thenReturn(false);

        storageService.ensureBucketExists();

        verify(minioClient).makeBucket(any(MakeBucketArgs.class));
    }

    @Test
    void ensureBucketExists_doesNothing_whenTheBucketAlreadyExists() throws Exception {
        when(minioClient.bucketExists(any())).thenReturn(true);

        storageService.ensureBucketExists();

        verify(minioClient, never()).makeBucket(any());
    }
}
