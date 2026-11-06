package com.resumeanalyser.job;

import org.springframework.stereotype.Component;

/** A fixed pause before each outside request, so a full run never hammers a feed or a website. */
@Component
public class Throttle {

    private final long delayMillis;
    private final long pageDelayMillis;

    public Throttle(JobsProperties properties) {
        this.delayMillis = properties.requestDelay().toMillis();
        this.pageDelayMillis = properties.pageDelay().toMillis();
    }

    /** Before a job-feed request. */
    public void pause() {
        sleep(delayMillis);
    }

    /** Before reading a page of a website (slower: websites are not built for bulk reads). */
    public void pausePage() {
        sleep(pageDelayMillis);
    }

    private static void sleep(long millis) {
        if (millis <= 0) {
            return;
        }
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
