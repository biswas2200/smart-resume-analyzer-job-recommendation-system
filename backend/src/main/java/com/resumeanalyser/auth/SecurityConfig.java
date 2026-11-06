package com.resumeanalyser.auth;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import java.util.Arrays;
import java.util.List;

/**
 * Central Spring Security setup for the whole app: this is the one place that
 * decides *whether a request is authenticated at all* (stateless JWT, no
 * sessions, no CSRF -- see {@link #securityFilterChain}). It intentionally does
 * NOT decide *which role can access which endpoint* -- with
 * {@link EnableMethodSecurity} turned on, each module declares that on its own
 * endpoints with {@code @PreAuthorize(...)}, so this class doesn't grow a giant
 * list of every URL in the app.
 */
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;

    @Value("${app.cors.allowed-origins}")
    private String allowedOrigins;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
    }

    /**
     * Allows the frontend's own origin (a different port during local dev, since
     * this is a browser web client calling a separate API) to call this API at all --
     * without this, the browser's own CORS check would block every request
     * before it ever reaches Spring Security's auth checks below.
     *
     * @return a CORS configuration applied to every endpoint, allowing the
     *         configured origin(s) ({@code app.cors.allowed-origins}) to send
     *         any method/header, including the {@code Authorization} bearer token.
     *         The list is comma-separated, spaces around entries are ignored, and an
     *         entry may be a pattern such as {@code https://*.example.app} for preview deploys
     */
    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOriginPatterns(Arrays.stream(allowedOrigins.split(","))
                .map(String::trim)
                .filter(origin -> !origin.isEmpty())
                .toList());
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("*"));
        configuration.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    /**
     * The hashing algorithm used for every stored password (NFR-2.2: never store plaintext).
     *
     * @return a BCrypt-based password encoder
     */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    /**
     * Exposes Spring Security's authentication manager as a bean so {@link AuthService}
     * can use it directly to verify login credentials.
     *
     * @param config Spring Security's own authentication configuration
     * @return the application's authentication manager
     */
    @Bean
    public AuthenticationManager authenticationManager(AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }

    /**
     * Defines the HTTP security rules applied to every request:
     * no CSRF (this is a stateless bearer-token API, not cookie-based, so CSRF doesn't apply),
     * no server-side sessions, registration/login are public, everything else requires
     * a valid JWT (checked by {@link JwtAuthenticationFilter}, which runs before
     * Spring's own username/password filter). Swagger UI and the raw OpenAPI
     * document are also public -- otherwise the docs page itself couldn't load
     * before you'd logged in; individual "try it out" calls against protected
     * endpoints still need a token pasted into Swagger UI's Authorize button.
     *
     * @param http Spring Security's HTTP configuration builder
     * @return the assembled filter chain
     */
    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/auth/register", "/auth/login").permitAll()
                        .requestMatchers("/swagger-ui/**", "/swagger-ui.html", "/v3/api-docs/**").permitAll()
                        // Belt and braces with the controller's @PreAuthorize: the
                        // whole admin surface is ADMIN-only at the URL level too.
                        .requestMatchers("/admin/**").hasRole("ADMIN")
                        .anyRequest().authenticated())
                // No valid token (none, expired or forged) is 401, so the frontend
                // knows the session is over and sends the user to sign in again.
                // Spring's default for an anonymous request is 403, which reads as
                // "signed in but not allowed" -- that stays for a signed-in user
                // without the right role.
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
                .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
