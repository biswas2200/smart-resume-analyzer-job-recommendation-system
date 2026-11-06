package com.resumeanalyser.job;

import org.springframework.stereotype.Component;
import java.util.List;
import java.util.regex.Pattern;

/** Whether a posting is in our city: any of its locations names it ("Bengaluru-VTP, India", "Bangalore"). */
@Component
public class LocationMatcher {

    private final Pattern cityPattern;
    private final Pattern countryPattern;

    public LocationMatcher(JobsProperties properties) {
        this.cityPattern = pattern(properties.cityNames());
        this.countryPattern = pattern(properties.countryNames());
    }

    public boolean matches(List<String> locations) {
        return locations.stream().anyMatch(location -> cityPattern.matcher(location).find());
    }

    /** In our city or anywhere in our country ("Pune, India"). */
    public boolean inCountry(List<String> locations) {
        return matches(locations) || locations.stream().anyMatch(location -> countryPattern.matcher(location).find());
    }

    /** Whole words only, so "Bangalore" matches but a street called "Bangaloreans Road" doesn't. */
    static Pattern pattern(List<String> cityNames) {
        String alternatives = String.join("|", cityNames.stream().map(Pattern::quote).toList());
        return Pattern.compile("(?i)(?<![\\p{L}])(" + alternatives + ")(?![\\p{L}])");
    }
}
