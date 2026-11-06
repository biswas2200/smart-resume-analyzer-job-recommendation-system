package com.resumeanalyser.skillvector;

import com.resumeanalyser.auth.JwtAuthenticationFilter;
import com.resumeanalyser.skillvector.dto.WeightsSnapshotDto;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Import;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.Map;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Web-layer tests for {@link SkillVectorSnapshotController}, focused on the
 * RBAC gate: exporting the weights snapshot is restricted to ADMIN
 * (FR-12.5), matching {@link SkillVectorControllerTest}'s recompute gate.
 */
@WebMvcTest(
        controllers = SkillVectorSnapshotController.class,
        // See SkillVectorControllerTest for why the real JwtAuthenticationFilter
        // is excluded here rather than mocked: auth for these tests comes
        // entirely from @WithMockUser.
        excludeFilters = @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = JwtAuthenticationFilter.class)
)
@Import(SkillVectorSnapshotControllerTest.MethodSecurityConfig.class)
class SkillVectorSnapshotControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private SkillVectorSnapshotService snapshotService;

    @Test
    @WithMockUser(roles = "USER")
    void snapshot_isForbidden_forANonAdminRole() throws Exception {
        mockMvc.perform(get("/roles/skill-vectors/snapshot"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void snapshot_isAllowed_forTheAdminRole() throws Exception {
        Instant now = Instant.now();
        when(snapshotService.exportSnapshot())
                .thenReturn(new WeightsSnapshotDto(now.toString(), now, "abc123", Map.of()));

        mockMvc.perform(get("/roles/skill-vectors/snapshot"))
                .andExpect(status().isOk());
    }

    /** Enables {@code @PreAuthorize} evaluation inside this web-layer-only test slice. */
    @TestConfiguration
    @EnableMethodSecurity
    static class MethodSecurityConfig {}
}
