package com.resumeanalyser.common.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Gives every HTTP request an id and writes one access-log line for it.
 * <p>
 * The id is taken from an incoming {@code X-Request-Id} header when it looks
 * safe, otherwise generated. It goes into the logging MDC as
 * {@code requestId} (so every log line written while serving the request
 * carries it, see {@code logging.pattern.level} in application.yml), back to
 * the client as a response header, and on to the ML service
 * ({@link com.resumeanalyser.client.MlServiceLoggingInterceptor}), so one
 * upload can be followed through both services' logs.
 * <p>
 * Runs before Spring Security, so rejected (401/403) requests are logged too.
 * Only the method, path, status and duration are logged: never headers,
 * query strings or bodies, which can carry tokens, passwords or resume text.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-Id";
    public static final String MDC_KEY = "requestId";

    private static final Logger log = LoggerFactory.getLogger(RequestIdFilter.class);
    // A caller-supplied id is echoed into logs, so only short, plain ids are accepted.
    private static final Pattern SAFE_ID = Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String requestId = requestIdFrom(request.getHeader(HEADER));
        MDC.put(MDC_KEY, requestId);
        response.setHeader(HEADER, requestId);
        long start = System.currentTimeMillis();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long elapsed = System.currentTimeMillis() - start;
            int status = response.getStatus();
            if (status >= 500) {
                log.error("{} {} -> {} in {}ms", request.getMethod(), request.getRequestURI(), status, elapsed);
            } else if (status >= 400) {
                log.warn("{} {} -> {} in {}ms", request.getMethod(), request.getRequestURI(), status, elapsed);
            } else {
                log.info("{} {} -> {} in {}ms", request.getMethod(), request.getRequestURI(), status, elapsed);
            }
            MDC.clear();
        }
    }

    static String requestIdFrom(String header) {
        if (header != null && SAFE_ID.matcher(header).matches()) {
            return header;
        }
        return UUID.randomUUID().toString();
    }
}
