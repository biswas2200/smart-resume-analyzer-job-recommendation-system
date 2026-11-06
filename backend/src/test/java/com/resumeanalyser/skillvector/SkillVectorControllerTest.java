package com.resumeanalyser.skillvector;

import com.resumeanalyser.auth.JwtAuthenticationFilter;
import com.resumeanalyser.feedback.FeedbackService;
import com.resumeanalyser.recommendation.Role;
import com.resumeanalyser.recommendation.RoleRepository;
import com.resumeanalyser.skillvector.mapper.SkillVectorMapper;
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

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Web-layer tests for {@link SkillVectorController}, focused on the RBAC gate:
 * listing a role's current vectors is open to any authenticated user, but
 * triggering a recompute is restricted to ADMIN via {@code @PreAuthorize}.
 */
@WebMvcTest(
        controllers = SkillVectorController.class,
        // @WebMvcTest auto-registers any Filter bean it finds (per Spring Boot's
        // documented slice scope) directly into MockMvc's filter chain, outside
        // Spring Security's own chain. The real JwtAuthenticationFilter needs
        // JwtService, which this slice doesn't provide -- and mocking the filter
        // instead is worse: a mocked void doFilter() does nothing, silently
        // swallowing every request before it reaches the controller. Excluding
        // it here is the correct fix; auth for these tests comes entirely from
        // @WithMockUser, not the JWT filter.
        excludeFilters = @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = JwtAuthenticationFilter.class)
)
@Import({SkillVectorControllerTest.MethodSecurityConfig.class, SkillVectorMapper.class})
class SkillVectorControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private SkillVectorService skillVectorService;

    @MockBean
    private FeedbackService feedbackService;

    @MockBean
    private RoleRepository roleRepository;

    private final UUID roleId = UUID.randomUUID();

    @Test
    @WithMockUser(roles = "USER")
    void list_isAllowedForAnyAuthenticatedRole() throws Exception {
        Role role = roleOf(roleId);
        when(roleRepository.findById(roleId)).thenReturn(Optional.of(role));
        when(skillVectorService.getAllCurrent(role)).thenReturn(List.of());

        mockMvc.perform(get("/roles/{roleId}/skill-vectors", roleId))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void list_returnsNotFound_whenTheRoleDoesNotExist() throws Exception {
        when(roleRepository.findById(roleId)).thenReturn(Optional.empty());

        mockMvc.perform(get("/roles/{roleId}/skill-vectors", roleId))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(roles = "USER")
    void recompute_isForbidden_forANonAdminRole() throws Exception {
        mockMvc.perform(post("/roles/{roleId}/skill-vectors/recompute", roleId).with(csrf()))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void recompute_isAllowed_forTheAdminRole() throws Exception {
        Role role = roleOf(roleId);
        when(roleRepository.findById(roleId)).thenReturn(Optional.of(role));
        when(feedbackService.recomputeSkillVectors(role)).thenReturn(List.of());

        mockMvc.perform(post("/roles/{roleId}/skill-vectors/recompute", roleId).with(csrf()))
                .andExpect(status().isOk());
    }

    private Role roleOf(UUID id) {
        Role role = new Role();
        role.setId(id);
        role.setTitle("Backend Software Engineer");
        return role;
    }

    /** Enables {@code @PreAuthorize} evaluation inside this web-layer-only test slice. */
    @TestConfiguration
    @EnableMethodSecurity
    static class MethodSecurityConfig {}
}
