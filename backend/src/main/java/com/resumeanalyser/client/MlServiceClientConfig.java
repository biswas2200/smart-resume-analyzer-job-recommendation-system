package com.resumeanalyser.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.client.RestClient;
import java.net.http.HttpClient;

/**
 * Builds the {@link RestClient} {@link MlServiceClient} uses to call the ML
 * service, pointed at {@code app.ml-service.base-url} (the FastAPI app in
 * {@code ml-service/app/main.py}).
 */
@Configuration
public class MlServiceClientConfig {

    @Bean
    public RestClient mlServiceRestClient(@Value("${app.ml-service.base-url}") String baseUrl, ObjectMapper objectMapper) {
        // Without an explicit version, the JDK HttpClient RestClient uses by
        // default prefers HTTP/2 and attempts a cleartext (h2c) upgrade on
        // every request -- uvicorn (HTTP/1.1-only) doesn't understand that
        // upgrade attempt and can mishandle the accompanying chunked
        // multipart body as a result, corrupting resume file uploads. Pinning
        // HTTP/1.1 here avoids the upgrade attempt entirely.
        HttpClient httpClient = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        return RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(new JdkClientHttpRequestFactory(httpClient))
                .requestInterceptor(new MlServiceLoggingInterceptor())
                // Explicitly wired to the app-wide, Spring Boot-managed
                // ObjectMapper (fail-on-unknown-properties disabled by its
                // default autoconfiguration) rather than the plain
                // `new ObjectMapper()` RestClient.builder() would otherwise
                // fall back to (Jackson's own default DOES fail on an
                // unrecognized field). Without this, any field the ML
                // service's response gains that AnalyzeResponseDto doesn't
                // yet mirror -- e.g. engine_fingerprint, explanation_source --
                // would break every resume upload with a deserialization error.
                .messageConverters(converters -> {
                    converters.removeIf(MappingJackson2HttpMessageConverter.class::isInstance);
                    converters.add(0, new MappingJackson2HttpMessageConverter(objectMapper));
                })
                .build();
    }
}
