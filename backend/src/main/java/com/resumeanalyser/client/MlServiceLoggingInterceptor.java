package com.resumeanalyser.client;

import com.resumeanalyser.common.logging.RequestIdFilter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.ClientHttpRequestExecution;
import org.springframework.http.client.ClientHttpRequestInterceptor;
import org.springframework.http.client.ClientHttpResponse;
import java.io.IOException;

/**
 * Logs every call to the ML service (path, status, duration) and passes the
 * current request id on as {@code X-Request-Id}, so the ML service's log
 * lines for the call carry the same id as the backend's. The query string is
 * left out of the log line on purpose; bodies (resume files, job
 * descriptions) are never logged.
 */
public class MlServiceLoggingInterceptor implements ClientHttpRequestInterceptor {

    private static final Logger log = LoggerFactory.getLogger(MlServiceLoggingInterceptor.class);

    @Override
    public ClientHttpResponse intercept(HttpRequest request, byte[] body, ClientHttpRequestExecution execution)
            throws IOException {
        String requestId = MDC.get(RequestIdFilter.MDC_KEY);
        if (requestId != null) {
            request.getHeaders().set(RequestIdFilter.HEADER, requestId);
        }
        String call = request.getMethod() + " " + request.getURI().getPath();
        long start = System.currentTimeMillis();
        try {
            ClientHttpResponse response = execution.execute(request, body);
            long elapsed = System.currentTimeMillis() - start;
            int status = response.getStatusCode().value();
            if (status >= 400) {
                log.warn("ML service {} -> {} in {}ms", call, status, elapsed);
            } else {
                log.info("ML service {} -> {} in {}ms", call, status, elapsed);
            }
            return response;
        } catch (IOException e) {
            log.error("ML service {} unreachable after {}ms: {}", call, System.currentTimeMillis() - start, e.toString());
            throw e;
        }
    }
}
