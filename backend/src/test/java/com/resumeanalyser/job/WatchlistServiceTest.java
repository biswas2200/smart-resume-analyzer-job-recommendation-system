package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.common.BadRequestException;
import com.resumeanalyser.common.LimitReachedException;
import com.resumeanalyser.common.ResourceNotFoundException;
import com.resumeanalyser.common.TooManyRequestsException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class WatchlistServiceTest {

    private static final Instant NOW = Instant.parse("2026-10-22T10:00:00Z");

    @Mock private WatchedCompanyRepository watched;
    @Mock private CompanyRepository companies;
    @Mock private JobPostingRepository postings;
    @Mock private WatchlistRateLimiter rateLimiter;
    @Mock private CompanyService companyService;

    private WatchlistService service;
    private final User user = new User();
    private Company company;

    @BeforeEach
    void setUp() {
        service = new WatchlistService(watched, companies, postings, new WatchlistProperties(2, 10, 60),
                rateLimiter, companyService, Clock.fixed(NOW, ZoneOffset.UTC));
        company = new Company();
        company.setId(UUID.randomUUID());
        company.setName("Groww");
        company.setDomain("groww.in");
        company.setStatus(CompanyStatus.ACTIVE);
    }

    @Test
    void watchingACompany_addsItWithItsJobCounts() {
        when(companies.findById(company.getId())).thenReturn(Optional.of(company));
        when(watched.findByUserAndCompany(user, company)).thenReturn(Optional.empty());
        when(watched.save(any(WatchedCompany.class))).thenAnswer(inv -> inv.getArgument(0));
        when(postings.countByCompanyAndActiveTrue(company)).thenReturn(12L);
        when(postings.countByCompanyAndActiveTrueAndFirstSeenAtAfter(company, NOW.minus(WatchlistService.NEW_FOR)))
                .thenReturn(3L);

        var dto = service.watch(user, company.getId());

        assertThat(dto.name()).isEqualTo("Groww");
        assertThat(dto.openJobs()).isEqualTo(12);
        assertThat(dto.newJobs()).isEqualTo(3);
        assertThat(dto.addedAt()).isEqualTo(NOW);
    }

    @Test
    void watchingAgain_keepsTheFirstEntry() {
        WatchedCompany existing = entry(Instant.parse("2026-10-01T00:00:00Z"));
        when(companies.findById(company.getId())).thenReturn(Optional.of(company));
        when(watched.findByUserAndCompany(user, company)).thenReturn(Optional.of(existing));

        var dto = service.watch(user, company.getId());

        assertThat(dto.addedAt()).isEqualTo(Instant.parse("2026-10-01T00:00:00Z"));
        verify(watched, never()).save(any());
    }

    @Test
    void watchingAMissingCompany_isNotFound() {
        UUID missing = UUID.randomUUID();
        when(companies.findById(missing)).thenReturn(Optional.empty());
        assertThatThrownBy(() -> service.watch(user, missing)).isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void watchingANewCompanyAtTheCap_isRefused() {
        when(companies.findById(company.getId())).thenReturn(Optional.of(company));
        when(watched.findByUserAndCompany(user, company)).thenReturn(Optional.empty());
        when(watched.countByUser(user)).thenReturn(2L);

        assertThatThrownBy(() -> service.watch(user, company.getId()))
                .isInstanceOf(LimitReachedException.class)
                .hasMessageContaining("up to 2 companies");
        verify(watched, never()).save(any());
    }

    @Test
    void watchingACompanyAlreadyWatched_isFineAtTheCap() {
        when(companies.findById(company.getId())).thenReturn(Optional.of(company));
        when(watched.findByUserAndCompany(user, company)).thenReturn(Optional.of(entry(NOW)));

        assertThat(service.watch(user, company.getId()).name()).isEqualTo("Groww");
        verify(watched, never()).countByUser(any());
    }

    @Test
    void changingTooQuickly_stopsBeforeTouchingTheDatabase() {
        doThrow(new TooManyRequestsException("slow down", Duration.ofSeconds(30)))
                .when(rateLimiter).recordChange(user.getId());

        assertThatThrownBy(() -> service.watch(user, company.getId())).isInstanceOf(TooManyRequestsException.class);
        assertThatThrownBy(() -> service.unwatch(user, company.getId())).isInstanceOf(TooManyRequestsException.class);
        verifyNoInteractions(companies, watched);
    }

    @Test
    void limits_reportTheCapAndHowManyAreWatched() {
        when(watched.countByUser(user)).thenReturn(1L);

        var limits = service.limits(user);

        assertThat(limits.maxCompanies()).isEqualTo(2);
        assertThat(limits.watching()).isEqualTo(1);
        assertThat(limits.changesPerMinute()).isEqualTo(10);
        assertThat(limits.changesPerHour()).isEqualTo(60);
    }

    @Test
    void list_returnsTheUsersCompaniesInOrder() {
        when(watched.findByUserOrderByAddedAtDesc(user)).thenReturn(List.of(entry(NOW)));

        assertThat(service.list(user)).extracting("domain").containsExactly("groww.in");
    }

    @Test
    void unwatching_deletesOnlyThatUsersEntry() {
        WatchedCompany existing = entry(NOW);
        when(companies.findById(company.getId())).thenReturn(Optional.of(company));
        when(watched.findByUserAndCompany(user, company)).thenReturn(Optional.of(existing));

        service.unwatch(user, company.getId());

        verify(watched).delete(existing);
    }

    @Test
    void search_marksCompaniesAlreadyWatched() {
        Company other = new Company();
        other.setId(UUID.randomUUID());
        other.setName("Groww Pay");
        when(watched.findByUserOrderByAddedAtDesc(user)).thenReturn(List.of(entry(NOW)));
        when(companies.findTop20ByNameContainingIgnoreCaseOrderByNameAsc("grow")).thenReturn(List.of(company, other));

        var options = service.search(user, "  grow ");

        assertThat(options).extracting("name", "watched")
                .containsExactly(tuple("Groww", true),
                        tuple("Groww Pay", false));
    }

    @Test
    void watchingANewCompanyByWebsite_addsItAsAUserCompanyAndWatchesIt() {
        when(companies.findByDomain("groww.in")).thenReturn(Optional.empty());
        when(watched.countByUser(user)).thenReturn(0L);
        when(companyService.add("Groww", "https://groww.in", null, CompanySource.USER)).thenReturn(company);
        when(watched.findByUserAndCompany(user, company)).thenReturn(Optional.empty());
        when(watched.save(any(WatchedCompany.class))).thenAnswer(inv -> inv.getArgument(0));

        var dto = service.watchNew(user, "Groww", "https://groww.in", null);

        assertThat(dto.domain()).isEqualTo("groww.in");
        verify(rateLimiter).recordChange(user.getId());
        verify(watched).save(any(WatchedCompany.class));
    }

    @Test
    void watchingANewCompanyAtTheCap_isRefusedBeforeAnyJobBoardCall() {
        when(companies.findByDomain("acme.com")).thenReturn(Optional.empty());
        when(watched.countByUser(user)).thenReturn(2L);

        assertThatThrownBy(() -> service.watchNew(user, "Acme", "acme.com", null))
                .isInstanceOf(LimitReachedException.class);
        verifyNoInteractions(companyService);
        verify(watched, never()).save(any());
    }

    @Test
    void watchingByWebsiteACompanyAlreadyWatched_isFineAtTheCap() {
        when(companies.findByDomain("groww.in")).thenReturn(Optional.of(company));
        when(watched.findByUserAndCompany(user, company)).thenReturn(Optional.of(entry(NOW)));
        when(companyService.add("Groww", "www.groww.in", null, CompanySource.USER)).thenReturn(company);

        assertThat(service.watchNew(user, "Groww", "www.groww.in", null).name()).isEqualTo("Groww");
        verify(watched, never()).countByUser(any());
        verify(watched, never()).save(any());
    }

    @Test
    void watchingByWebsite_needsAWebAddress() {
        assertThatThrownBy(() -> service.watchNew(user, "Acme", "not a website", null))
                .isInstanceOf(BadRequestException.class);
        verifyNoInteractions(companyService, watched);
    }

    @Test
    void watchingByWebsiteTooQuickly_stopsBeforeAnything() {
        doThrow(new TooManyRequestsException("slow down", Duration.ofSeconds(30)))
                .when(rateLimiter).recordChange(user.getId());

        assertThatThrownBy(() -> service.watchNew(user, "Acme", "acme.com", null))
                .isInstanceOf(TooManyRequestsException.class);
        verifyNoInteractions(companies, watched, companyService);
    }

    @Test
    void search_withABlankQuery_findsNothing() {
        assertThat(service.search(user, "  ")).isEmpty();
        verifyNoInteractions(companies);
    }

    private WatchedCompany entry(Instant addedAt) {
        WatchedCompany entry = new WatchedCompany();
        entry.setUser(user);
        entry.setCompany(company);
        entry.setAddedAt(addedAt);
        return entry;
    }
}
