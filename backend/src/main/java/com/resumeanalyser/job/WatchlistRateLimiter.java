package com.resumeanalyser.job;

import com.resumeanalyser.common.TooManyRequestsException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Caps how often one user may change their watchlist: at most
 * {@code changesPerMinute} and {@code changesPerHour} watch / stop-watching
 * requests, counted over sliding windows. A rejected request is not counted,
 * so waiting the {@code Retry-After} time always works.
 * <p>
 * The counts live in this instance's memory: they reset on restart, and each
 * instance counts on its own if the backend is ever scaled out. That is
 * enough to stop a loop from one account; a shared store (e.g. Redis) would
 * be the next step for several instances.
 */
@Component
public class WatchlistRateLimiter {

    private static final Duration MINUTE = Duration.ofMinutes(1);
    private static final Duration HOUR = Duration.ofHours(1);

    private final WatchlistProperties properties;
    private final Clock clock;
    /** Each user's accepted changes in the last hour, oldest first. */
    private final Map<UUID, Deque<Instant>> changes = new ConcurrentHashMap<>();

    public WatchlistRateLimiter(WatchlistProperties properties, Clock clock) {
        this.properties = properties;
        this.clock = clock;
    }

    /**
     * Counts one watchlist change for {@code userId}.
     *
     * @throws TooManyRequestsException if it would go over either limit
     */
    public void recordChange(UUID userId) {
        Instant now = clock.instant();
        Deque<Instant> log = changes.computeIfAbsent(userId, id -> new ArrayDeque<>());
        synchronized (log) {
            dropOlderThan(log, now.minus(HOUR));
            Duration wait = waitBeforeNext(log, now);
            if (wait != null) {
                long seconds = Math.max(1, (wait.toMillis() + 999) / 1000);
                throw new TooManyRequestsException(
                        "You're changing your watchlist too quickly. Try again in " + seconds
                                + (seconds == 1 ? " second." : " seconds."),
                        Duration.ofSeconds(seconds));
            }
            log.addLast(now);
        }
    }

    /** Forgets users with no change in the last hour, so the map doesn't grow forever. */
    @Scheduled(fixedDelayString = "PT10M")
    void forgetIdleUsers() {
        Instant hourAgo = clock.instant().minus(HOUR);
        changes.entrySet().removeIf(entry -> {
            synchronized (entry.getValue()) {
                dropOlderThan(entry.getValue(), hourAgo);
                return entry.getValue().isEmpty();
            }
        });
    }

    /** How long until one more change fits both windows, or null if it fits now. */
    private Duration waitBeforeNext(Deque<Instant> log, Instant now) {
        if (log.size() >= properties.changesPerHour()) {
            return Duration.between(now, log.peekFirst().plus(HOUR));
        }
        Instant minuteAgo = now.minus(MINUTE);
        int inLastMinute = 0;
        Instant oldestInMinute = null;
        for (Iterator<Instant> it = log.descendingIterator(); it.hasNext(); ) {
            Instant at = it.next();
            if (!at.isAfter(minuteAgo)) {
                break;
            }
            inLastMinute++;
            oldestInMinute = at;
        }
        if (inLastMinute >= properties.changesPerMinute()) {
            return Duration.between(now, oldestInMinute.plus(MINUTE));
        }
        return null;
    }

    private static void dropOlderThan(Deque<Instant> log, Instant cutoff) {
        while (!log.isEmpty() && !log.peekFirst().isAfter(cutoff)) {
            log.removeFirst();
        }
    }
}
