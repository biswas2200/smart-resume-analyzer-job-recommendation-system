package com.resumeanalyser.job;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class LocationAndDomainsTest {

    private final LocationMatcher bengaluru = new LocationMatcher(new JobsProperties(
            "Bengaluru", List.of("bengaluru", "bangalore"), List.of("india"), "test", Duration.ZERO, Duration.ZERO, Duration.ofSeconds(1)));

    @Test
    void matchesEitherSpelling_inAnyOfThePostingsLocations() {
        assertThat(bengaluru.matches(List.of("Bengaluru-VTP, India"))).isTrue();
        assertThat(bengaluru.matches(List.of("Hyderabad", "bangalore"))).isTrue();
        assertThat(bengaluru.matches(List.of("BANGALORE, KA"))).isTrue();
    }

    @Test
    void ignoresOtherCities_andTheCityNameInsideALongerWord() {
        assertThat(bengaluru.matches(List.of("Mumbai", "Remote - India"))).isFalse();
        assertThat(bengaluru.matches(List.of("Bangaloreans Road, Chennai"))).isFalse();
        assertThat(bengaluru.matches(List.of())).isFalse();
    }

    @Test
    void normalize_keepsTheHostWithoutWww() {
        assertThat(Domains.normalize("https://www.Groww.in/about")).isEqualTo("groww.in");
        assertThat(Domains.normalize("cred.club")).isEqualTo("cred.club");
        assertThat(Domains.normalize("http://careers.flipkart.com")).isEqualTo("careers.flipkart.com");
        assertThat(Domains.normalize("not a site")).isNull();
        assertThat(Domains.normalize("")).isNull();
    }

    @Test
    void brandLabel_skipsCountrySecondLevels() {
        assertThat(Domains.brandLabel("groww.in")).isEqualTo("groww");
        assertThat(Domains.brandLabel("tatamotors.co.in")).isEqualTo("tatamotors");
        assertThat(Domains.brandLabel("careers.flipkart.com")).isEqualTo("flipkart");
    }
}
