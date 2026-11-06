package com.resumeanalyser.auth;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;
import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;

/**
 * Creates and verifies the JWT access tokens issued at login/registration.
 * Tokens are signed with HMAC-SHA256 using a secret loaded from configuration
 * (see {@code app.jwt.secret} / {@code JWT_SECRET}) and carry the user's email
 * as the subject claim.
 */
@Service
public class JwtService {

    private final SecretKey signingKey;
    private final long expirationMs;

    /**
     * @param secret       the raw signing secret, injected from {@code app.jwt.secret}
     *                     (env {@code JWT_SECRET}); must be long enough for HMAC-SHA256
     * @param expirationMs how long, in milliseconds, a freshly issued token stays valid
     *                     (from {@code app.jwt.expiration-ms} / env {@code JWT_EXPIRATION_MS})
     */
    public JwtService(
            @Value("${app.jwt.secret}") String secret,
            @Value("${app.jwt.expiration-ms}") long expirationMs
    ) {
        this.signingKey = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expirationMs = expirationMs;
    }

    /**
     * Issues a new signed JWT for the given user, valid for {@code expirationMs} from now.
     *
     * @param userDetails the authenticated user to issue a token for; only the username (email) is used
     * @return a compact, signed JWT string
     */
    public String generateToken(UserDetails userDetails) {
        Instant now = Instant.now();
        return Jwts.builder()
                .subject(userDetails.getUsername())
                // jjwt has no Instant overload here, only Date
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plusMillis(expirationMs)))
                .signWith(signingKey)
                .compact();
    }

    /**
     * Reads the expiry timestamp out of a token, without checking whether it has already passed.
     *
     * @param token a previously issued JWT
     * @return the instant at which the token expires
     */
    public Instant extractExpiration(String token) {
        return parseClaims(token).getExpiration().toInstant();
    }

    /**
     * Reads the subject (the account's email) out of a token, without checking its validity.
     *
     * @param token a previously issued JWT
     * @return the email the token was issued for
     */
    public String extractEmail(String token) {
        return parseClaims(token).getSubject();
    }

    /**
     * Checks that a token's signature is valid, its subject matches the given user, and it hasn't expired.
     *
     * @param token       the JWT presented by the client
     * @param userDetails the user the token is expected to belong to
     * @return true if the token is genuine, matches this user, and is still within its expiry
     */
    public boolean isTokenValid(String token, UserDetails userDetails) {
        try {
            Claims claims = parseClaims(token);
            return claims.getSubject().equals(userDetails.getUsername())
                    && claims.getExpiration().toInstant().isAfter(Instant.now());
        } catch (JwtException e) {
            return false;
        }
    }

    /**
     * Verifies the token's signature and decodes its claims.
     * Throws {@link JwtException} (or a subclass) if the token is malformed, expired,
     * or signed with a different key.
     *
     * @param token the JWT to parse
     * @return the decoded claims (subject, issued-at, expiration, ...)
     */
    private Claims parseClaims(String token) {
        return Jwts.parser()
                .verifyWith(signingKey)
                .build()
                .parseSignedClaims(token)
                .getPayload();
    }
}
