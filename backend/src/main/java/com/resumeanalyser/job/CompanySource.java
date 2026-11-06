package com.resumeanalyser.job;

/** Where a company in our list came from. */
public enum CompanySource {
    WIKIDATA,
    /** The Bangalore Startup Map's public company pages (credited in the app). */
    STARTUP_MAP,
    /** Added by a user to their watchlist. */
    USER,
    ADMIN
}
