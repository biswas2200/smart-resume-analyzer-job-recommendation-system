package com.resumeanalyser.job;

import java.net.URI;
import java.util.Locale;
import java.util.Set;

/** Website addresses to the domain key companies are stored under. */
final class Domains {

    /** Second-level labels that sit under a country code, as in "co.in" or "com.au". */
    private static final Set<String> COUNTRY_SECOND_LEVELS = Set.of("co", "com", "net", "org", "ac", "gov", "edu");

    private Domains() {}

    /** "https://www.Groww.in/about" -> "groww.in"; null if it isn't a web address. */
    static String normalize(String website) {
        if (website == null || website.isBlank()) {
            return null;
        }
        String withScheme = website.contains("://") ? website.trim() : "https://" + website.trim();
        try {
            String host = URI.create(withScheme).getHost();
            if (host == null || !host.contains(".")) {
                return null;
            }
            host = host.toLowerCase(Locale.ROOT);
            return host.startsWith("www.") ? host.substring(4) : host;
        } catch (IllegalArgumentException e) {
            return null;
        }
    }

    /** The brand part of a domain: "groww.in" -> "groww", "tatamotors.co.in" -> "tatamotors". */
    static String brandLabel(String domain) {
        String[] parts = domain.split("\\.");
        int n = parts.length;
        if (n >= 3 && parts[n - 1].length() == 2 && COUNTRY_SECOND_LEVELS.contains(parts[n - 2])) {
            return parts[n - 3];
        }
        return n >= 2 ? parts[n - 2] : parts[0];
    }
}
