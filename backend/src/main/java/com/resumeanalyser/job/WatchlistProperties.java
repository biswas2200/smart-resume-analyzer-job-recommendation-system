package com.resumeanalyser.job;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Limits on the company watchlist ({@code app.watchlist.*} in application.yml),
 * the same for every user. They keep one account from filling the
 * table or hammering the server by watching and un-watching in a loop.
 *
 * @param maxCompanies     how many companies one user may watch at a time
 * @param changesPerMinute watch / stop-watching requests one user may make per minute
 * @param changesPerHour   the same, per hour
 */
@ConfigurationProperties(prefix = "app.watchlist")
public record WatchlistProperties(int maxCompanies, int changesPerMinute, int changesPerHour) {}
