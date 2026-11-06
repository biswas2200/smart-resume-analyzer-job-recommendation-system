package com.resumeanalyser.job.dto;

/**
 * The watchlist limits that apply to every user, and how much of the cap
 * this user has used, so the page can say "3 of 25" before a request fails.
 */
public record WatchlistLimitsDto(int maxCompanies, long watching, int changesPerMinute, int changesPerHour) {}
