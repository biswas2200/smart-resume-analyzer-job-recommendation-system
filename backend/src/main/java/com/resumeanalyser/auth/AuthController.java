package com.resumeanalyser.auth;

import com.resumeanalyser.account.dto.UserDto;
import com.resumeanalyser.auth.dto.AuthResponse;
import com.resumeanalyser.auth.dto.LoginRequest;
import com.resumeanalyser.auth.dto.RegisterRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The two public, unauthenticated entry points into the app -- creating an
 * account and logging into one, both permitted through {@link SecurityConfig}
 * without a token -- plus {@code GET /auth/me}, which does require one and
 * tells the client who it is (and, after an admin promotion, what role).
 */
@RestController
@RequestMapping("/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    /**
     * Creates a new account.
     * <p>
     * The failure case is declared below rather than handled inline here: when
     * the email is already taken, {@link AuthService#register} throws, this
     * method never reaches its {@code return}, and {@link AuthExceptionHandler}
     * turns the exception into the 409 response instead.
     *
     * @param request the new account's email and password, validated by the {@code @Valid} constraints on {@link RegisterRequest}
     * @return 201 Created with a token for the new account
     * @throws EmailAlreadyInUseException if the email is already registered -- becomes a 409 Conflict, see {@link AuthExceptionHandler}
     */
    @PostMapping("/register")
    public ResponseEntity<AuthResponse> register(@Valid @RequestBody RegisterRequest request)
            throws EmailAlreadyInUseException {
        return ResponseEntity.status(HttpStatus.CREATED).body(authService.register(request));
    }

    /**
     * Logs into an existing account.
     * <p>
     * The failure case is declared below rather than handled inline here: when
     * the credentials don't check out, {@link AuthService#login} throws, this
     * method never reaches its {@code return}, and {@link AuthExceptionHandler}
     * turns the exception into the 401 response instead.
     *
     * @param request the login email and password
     * @return 200 OK with a fresh token
     * @throws BadCredentialsException if the email or password is wrong -- becomes a 401 Unauthorized, see {@link AuthExceptionHandler}
     */
    @PostMapping("/login")
    public ResponseEntity<AuthResponse> login(@Valid @RequestBody LoginRequest request)
            throws BadCredentialsException {
        return ResponseEntity.ok(authService.login(request));
    }

    /**
     * The signed-in account's current identity and role, read fresh from the
     * database -- the value the frontend should trust for role-dependent UI,
     * since the role inside a JWT issued before an upgrade is stale.
     */
    @GetMapping("/me")
    public UserDto me(Authentication authentication) {
        return authService.me(authentication.getName());
    }
}
