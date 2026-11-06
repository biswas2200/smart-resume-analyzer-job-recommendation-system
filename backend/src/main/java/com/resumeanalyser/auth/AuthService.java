package com.resumeanalyser.auth;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.account.UserRole;
import com.resumeanalyser.account.dto.UserDto;
import com.resumeanalyser.auth.dto.AuthResponse;
import com.resumeanalyser.auth.dto.LoginRequest;
import com.resumeanalyser.auth.dto.RegisterRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;
import java.util.Locale;

/**
 * Business logic behind the two public auth endpoints: creating a new account
 * and logging into an existing one. Both end the same way -- a signed JWT handed
 * back to the caller -- so that shared step lives in {@link #issueToken}.
 */
@Service
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuthenticationManager authenticationManager;
    private final JwtService jwtService;
    private final UserDetailsService userDetailsService;
    private final List<String> adminEmails;

    public AuthService(
            UserRepository userRepository,
            PasswordEncoder passwordEncoder,
            AuthenticationManager authenticationManager,
            JwtService jwtService,
            UserDetailsService userDetailsService,
            @Value("${app.admin.emails:}") List<String> adminEmails
    ) {
        this.userRepository = userRepository;
        this.passwordEncoder = passwordEncoder;
        this.authenticationManager = authenticationManager;
        this.jwtService = jwtService;
        this.userDetailsService = userDetailsService;
        this.adminEmails = adminEmails.stream()
                .map(e -> e.trim().toLowerCase(Locale.ROOT))
                .filter(e -> !e.isEmpty())
                .toList();
    }

    /**
     * Creates a new account and immediately logs it in (returns a usable token,
     * so the caller doesn't have to make a second request to log in right after registering).
     *
     * @param request the new user's email and chosen plaintext password
     * @return a token for the newly created account
     * @throws EmailAlreadyInUseException if the email is already registered
     */
    @Transactional
    public AuthResponse register(RegisterRequest request) {
        if (userRepository.existsByEmail(request.email())) {
            throw new EmailAlreadyInUseException(request.email());
        }

        User user = new User();
        user.setEmail(request.email());
        user.setPasswordHash(passwordEncoder.encode(request.password()));
        user = userRepository.save(promoteIfBootstrapAdmin(user));

        return issueToken(user);
    }

    /**
     * The signed-in account, as the client should see it -- read fresh from
     * the database (not from the token) so a role change made by an admin is
     * visible on the very next request.
     */
    public UserDto me(String email) {
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new IllegalStateException("Authenticated user vanished: " + email));
        return toDto(user);
    }

    /**
     * Bootstrap for the first administrator: an account whose email is listed
     * in {@code app.admin.emails} ({@code APP_ADMIN_EMAILS}) becomes ADMIN on
     * register and on login, so no manual database edit is ever needed to
     * get an admin who can then promote others via {@code /admin/users}.
     */
    User promoteIfBootstrapAdmin(User user) {
        if (user.getRole() != UserRole.ADMIN
                && adminEmails.contains(user.getEmail().trim().toLowerCase(Locale.ROOT))) {
            user.setRole(UserRole.ADMIN);
        }
        return user;
    }

    /**
     * Verifies a login attempt's credentials and, if they check out, issues a fresh token.
     *
     * @param request the email/password being submitted
     * @return a token for the authenticated account
     * @throws org.springframework.security.authentication.BadCredentialsException if the email or password is wrong
     */
    public AuthResponse login(LoginRequest request) {
        Authentication authentication = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(request.email(), request.password()));

        UserDetails principal = (UserDetails) authentication.getPrincipal();
        User user = userRepository.findByEmail(principal.getUsername())
                .orElseThrow(() -> new IllegalStateException("Authenticated user vanished: " + principal.getUsername()));
        User promoted = promoteIfBootstrapAdmin(user);
        if (promoted.getRole() != user.getRole()) {
            user = userRepository.save(promoted);
        }

        return issueToken(user);
    }

    /**
     * Builds the JWT + user-info response shared by both register and login.
     * <p>
     * Delegates the User-to-UserDetails adaptation to {@link UserDetailsService}
     * rather than re-deriving it here, so there's exactly one place (its
     * implementation) that decides what a user's Spring Security authorities look
     * like -- keeping this in sync with {@link JwtAuthenticationFilter}, which
     * authenticates every later request the same way.
     *
     * @param user the account to issue a token for
     * @return the token, its expiry, and a public-safe view of the account
     */
    private AuthResponse issueToken(User user) {
        UserDetails userDetails = userDetailsService.loadUserByUsername(user.getEmail());

        String token = jwtService.generateToken(userDetails);

        return AuthResponse.bearer(token, jwtService.extractExpiration(token), toDto(user));
    }

    /** The client's view of an account. */
    UserDto toDto(User user) {
        return new UserDto(user.getId(), user.getEmail(), user.getRole(), user.getCreatedAt());
    }
}
