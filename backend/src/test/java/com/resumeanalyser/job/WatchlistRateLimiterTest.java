package com.resumeanalyser.job;

import com.resumeanalyser.common.TooManyRequestsException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** The per-user watchlist change limits: 3 a minute and 5 an hour here, on a clock the test moves. */
class WatchlistRateLimiterTest {

    private final MovableClock clock = new MovableClock(Instant.parse("2026-10-22T10:00:00Z"));
    private final UUID asha = UUID.randomUUID();
    private final UUID ravi = UUID.randomUUID();
    private WatchlistRateLimiter limiter;

    @BeforeEach
    void setUp() {
        limiter = new WatchlistRateLimiter(new WatchlistProperties(25, 3, 5), clock);
    }

    @Test
    void theFourthChangeInAMinute_isRefusedWithTheWait() {
        limiter.recordChange(asha);
        clock.advance(Duration.ofSeconds(10));
        limiter.recordChange(asha);
        limiter.recordChange(asha);

        assertThatThrownBy(() -> limiter.recordChange(asha))
                .isInstanceOfSatisfying(TooManyRequestsException.class,
                        e -> assertThat(e.getRetryAfter()).isEqualTo(Duration.ofSeconds(50)))
                .hasMessageContaining("Try again in 50 seconds");
    }

    @Test
    void waitingTheRetryTime_isEnough() {
        limiter.recordChange(asha);
        limiter.recordChange(asha);
        limiter.recordChange(asha);
        assertThatThrownBy(() -> limiter.recordChange(asha)).isInstanceOf(TooManyRequestsException.class);

        clock.advance(Duration.ofMinutes(1).plusMillis(1));

        assertThatCode(() -> limiter.recordChange(asha)).doesNotThrowAnyException();
    }

    @Test
    void theHourlyLimit_holdsEvenWhenEachMinuteIsQuiet() {
        for (int i = 0; i < 5; i++) {
            limiter.recordChange(asha);
            clock.advance(Duration.ofMinutes(5));
        }

        assertThatThrownBy(() -> limiter.recordChange(asha))
                .isInstanceOfSatisfying(TooManyRequestsException.class,
                        e -> assertThat(e.getRetryAfter()).isEqualTo(Duration.ofMinutes(35)));
    }

    @Test
    void eachUserHasTheirOwnAllowance() {
        limiter.recordChange(asha);
        limiter.recordChange(asha);
        limiter.recordChange(asha);

        assertThatCode(() -> limiter.recordChange(ravi)).doesNotThrowAnyException();
    }

    @Test
    void idleUsersAreForgotten() {
        limiter.recordChange(asha);
        limiter.recordChange(asha);
        limiter.recordChange(asha);
        clock.advance(Duration.ofHours(2));

        limiter.forgetIdleUsers();

        assertThatCode(() -> {
            limiter.recordChange(asha);
            limiter.recordChange(asha);
            limiter.recordChange(asha);
        }).doesNotThrowAnyException();
    }

    private static final class MovableClock extends Clock {
        private Instant now;

        MovableClock(Instant start) {
            this.now = start;
        }

        void advance(Duration by) {
            now = now.plus(by);
        }

        @Override
        public Instant instant() {
            return now;
        }

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }
    }
}
