package com.resumeanalyser.account;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Clock;

/** Supplies the clock services read the current time from -- a bean so tests can pin it to a fixed instant. */
@Configuration
public class ClockConfig {

    @Bean
    public Clock clock() {
        return Clock.systemUTC();
    }
}
