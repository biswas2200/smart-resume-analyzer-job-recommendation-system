package com.resumeanalyser.auth;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.account.UserRole;
import com.resumeanalyser.auth.dto.RegisterRequest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unit tests for {@link AuthService}'s bootstrap-admin rule: an account whose
 * email is listed in {@code app.admin.emails} is promoted to ADMIN at
 * registration, so the first administrator never needs a database edit.
 */
@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

    @Mock
    private UserRepository userRepository;
    @Mock
    private PasswordEncoder passwordEncoder;
    @Mock
    private AuthenticationManager authenticationManager;
    @Mock
    private JwtService jwtService;
    @Mock
    private UserDetailsService userDetailsService;

    private AuthService serviceWithAdmins(String... emails) {
        return new AuthService(userRepository, passwordEncoder, authenticationManager, jwtService,
                userDetailsService, List.of(emails));
    }

    private void stubRegistration() {
        when(userRepository.existsByEmail(anyString())).thenReturn(false);
        when(passwordEncoder.encode(anyString())).thenReturn("hash");
        when(userRepository.save(any(User.class))).thenAnswer(inv -> {
            User u = inv.getArgument(0);
            u.setId(UUID.randomUUID());
            return u;
        });
        when(userDetailsService.loadUserByUsername(anyString())).thenReturn(mock(UserDetails.class));
        when(jwtService.generateToken(any())).thenReturn("token");
        when(jwtService.extractExpiration("token")).thenReturn(Instant.now());
    }

    @Test
    void register_promotesABootstrapAdminEmail_caseInsensitively() {
        stubRegistration();
        AuthService service = serviceWithAdmins(" Owner@Example.com ");

        var response = service.register(new RegisterRequest("owner@example.com", "password123"));

        ArgumentCaptor<User> saved = ArgumentCaptor.forClass(User.class);
        verify(userRepository).save(saved.capture());
        assertThat(saved.getValue().getRole()).isEqualTo(UserRole.ADMIN);
        assertThat(response.user().role()).isEqualTo(UserRole.ADMIN);
    }

    @Test
    void register_leavesEveryoneElseAsAPlainUser() {
        stubRegistration();
        AuthService service = serviceWithAdmins("owner@example.com");

        var response = service.register(new RegisterRequest("someone@example.com", "password123"));

        assertThat(response.user().role()).isEqualTo(UserRole.USER);
    }

    @Test
    void register_withNoBootstrapList_neverPromotes() {
        stubRegistration();
        AuthService service = serviceWithAdmins();

        var response = service.register(new RegisterRequest("owner@example.com", "password123"));

        assertThat(response.user().role()).isEqualTo(UserRole.USER);
    }
}
