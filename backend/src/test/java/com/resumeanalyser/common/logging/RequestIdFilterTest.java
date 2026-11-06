package com.resumeanalyser.common.logging;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import java.util.concurrent.atomic.AtomicReference;

class RequestIdFilterTest {

    private final RequestIdFilter filter = new RequestIdFilter();

    @Test
    void keepsASafeIncomingIdAndExposesItDuringTheRequest() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/resumes");
        request.addHeader(RequestIdFilter.HEADER, "abc-123");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> seen = new AtomicReference<>();

        filter.doFilter(request, response, new MockFilterChain() {
            @Override
            public void doFilter(jakarta.servlet.ServletRequest req, jakarta.servlet.ServletResponse res) {
                seen.set(MDC.get(RequestIdFilter.MDC_KEY));
            }
        });

        assertThat(seen.get()).isEqualTo("abc-123");
        assertThat(response.getHeader(RequestIdFilter.HEADER)).isEqualTo("abc-123");
        assertThat(MDC.get(RequestIdFilter.MDC_KEY)).isNull();
    }

    @Test
    void replacesAMissingOrUnsafeId() {
        assertThat(RequestIdFilter.requestIdFrom(null)).hasSize(36);
        assertThat(RequestIdFilter.requestIdFrom("bad id\nforged log line")).hasSize(36);
        assertThat(RequestIdFilter.requestIdFrom("x".repeat(65))).hasSize(36);
    }
}
