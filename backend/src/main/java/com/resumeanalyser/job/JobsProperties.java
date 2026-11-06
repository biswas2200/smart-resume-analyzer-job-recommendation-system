package com.resumeanalyser.job;

import org.springframework.boot.context.properties.ConfigurationProperties;
import java.time.Duration;
import java.util.List;

/**
 * Job collection settings ({@code app.jobs.*} in application.yml).
 *
 * @param city         the city we collect jobs for (stored on each company), e.g. "Bengaluru"
 * @param cityNames    lower-case spellings a posting's location may use for that city
 * @param countryNames lower-case names of the country; a feed found by guessing its name must
 *                     have a job here, or it is taken to be another company's board
 * @param userAgent    sent with every outside request, so feed owners can see who is asking
 * @param requestDelay pause between outside requests, to stay polite to the feeds
 * @param pageDelay    pause between page reads on a website (the startup map), slower than the feeds
 * @param timeout      per-request connect and read timeout
 */
@ConfigurationProperties(prefix = "app.jobs")
public record JobsProperties(
        String city,
        List<String> cityNames,
        List<String> countryNames,
        String userAgent,
        Duration requestDelay,
        Duration pageDelay,
        Duration timeout
) {}
