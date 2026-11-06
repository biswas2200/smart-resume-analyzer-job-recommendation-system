package com.resumeanalyser.job;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.auth.JwtAuthenticationFilter;
import com.resumeanalyser.common.BadRequestException;
import com.resumeanalyser.common.LimitReachedException;
import com.resumeanalyser.common.TooManyRequestsException;
import com.resumeanalyser.job.dto.WatchlistLimitsDto;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Web-layer tests for {@link WatchlistController}: every call needs a signed-in
 * user and acts on that user's own watchlist. The JWT filter is excluded as in
 * {@code SkillVectorControllerTest}; auth comes from {@code @WithMockUser}.
 */
@WebMvcTest(
        controllers = WatchlistController.class,
        excludeFilters = @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = JwtAuthenticationFilter.class)
)
class WatchlistControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private WatchlistService watchlistService;

    @MockBean
    private UserRepository userRepository;

    @Test
    void list_needsASignedInUser() throws Exception {
        mockMvc.perform(get("/watchlist")).andExpect(status().isUnauthorized());
        verifyNoInteractions(watchlistService);
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void list_readsTheSignedInUsersWatchlist() throws Exception {
        User asha = new User();
        when(userRepository.findByEmail("asha@example.com")).thenReturn(Optional.of(asha));
        when(watchlistService.list(asha)).thenReturn(List.of());

        mockMvc.perform(get("/watchlist")).andExpect(status().isOk());

        verify(watchlistService).list(asha);
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void unwatch_answersNoContent() throws Exception {
        User asha = new User();
        UUID companyId = UUID.randomUUID();
        when(userRepository.findByEmail("asha@example.com")).thenReturn(Optional.of(asha));

        mockMvc.perform(delete("/watchlist/{id}", companyId).with(csrf())).andExpect(status().isNoContent());

        verify(watchlistService).unwatch(asha, companyId);
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void watch_withAMalformedId_isABadRequest() throws Exception {
        mockMvc.perform(put("/watchlist/{id}", "not-a-uuid").with(csrf())).andExpect(status().isBadRequest());
        verifyNoInteractions(watchlistService);
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void changingTooQuickly_answers429WithRetryAfter() throws Exception {
        User asha = new User();
        UUID companyId = UUID.randomUUID();
        when(userRepository.findByEmail("asha@example.com")).thenReturn(Optional.of(asha));
        when(watchlistService.watch(asha, companyId))
                .thenThrow(new TooManyRequestsException("Try again in 42 seconds.", Duration.ofSeconds(42)));

        mockMvc.perform(put("/watchlist/{id}", companyId).with(csrf()))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().string("Retry-After", "42"))
                .andExpect(jsonPath("$.message").value("Try again in 42 seconds."));
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void watchingPastTheCap_answers409WithTheReason() throws Exception {
        User asha = new User();
        UUID companyId = UUID.randomUUID();
        when(userRepository.findByEmail("asha@example.com")).thenReturn(Optional.of(asha));
        when(watchlistService.watch(asha, companyId))
                .thenThrow(new LimitReachedException("You can watch up to 25 companies."));

        mockMvc.perform(put("/watchlist/{id}", companyId).with(csrf()))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.message").value("You can watch up to 25 companies."));
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void limits_reportsTheSignedInUsersUse() throws Exception {
        User asha = new User();
        when(userRepository.findByEmail("asha@example.com")).thenReturn(Optional.of(asha));
        when(watchlistService.limits(asha)).thenReturn(new WatchlistLimitsDto(25, 3, 10, 60));

        mockMvc.perform(get("/watchlist/limits"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.maxCompanies").value(25))
                .andExpect(jsonPath("$.watching").value(3));
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void watchNew_addsByWebsiteAndAnswersCreated() throws Exception {
        User asha = new User();
        when(userRepository.findByEmail("asha@example.com")).thenReturn(Optional.of(asha));

        mockMvc.perform(post("/watchlist/companies").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Acme\",\"website\":\"acme.com\",\"careersUrl\":\"https://jobs.lever.co/acme\"}"))
                .andExpect(status().isCreated());

        verify(watchlistService).watchNew(asha, "Acme", "acme.com", "https://jobs.lever.co/acme");
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void watchNew_needsANameAndAWebsite() throws Exception {
        mockMvc.perform(post("/watchlist/companies").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"website\":\"\"}"))
                .andExpect(status().isBadRequest());
        verifyNoInteractions(watchlistService);
    }

    @Test
    @WithMockUser(username = "asha@example.com")
    void watchNew_withANonWebsite_answers400WithTheReason() throws Exception {
        User asha = new User();
        when(userRepository.findByEmail("asha@example.com")).thenReturn(Optional.of(asha));
        when(watchlistService.watchNew(asha, "Acme", "acme", null))
                .thenThrow(new BadRequestException("That doesn't look like a website address, e.g. acme.com"));

        mockMvc.perform(post("/watchlist/companies").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Acme\",\"website\":\"acme\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.message").value("That doesn't look like a website address, e.g. acme.com"));
    }
}
