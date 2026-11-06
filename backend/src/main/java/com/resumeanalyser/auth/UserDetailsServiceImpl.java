package com.resumeanalyser.auth;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

/**
 * Bridges the {@link User} account entity into Spring Security's authentication
 * mechanism. Spring Security calls {@link #loadUserByUsername} whenever it needs
 * to know who a set of credentials (login form) or a token (JWT filter) belongs to.
 * Because this always reads the account fresh from the database, a role change
 * (e.g. promoting someone to ADMIN) takes effect on their very next
 * request -- not only after they log in again.
 */
@Service
public class UserDetailsServiceImpl implements UserDetailsService {

    private final UserRepository userRepository;

    public UserDetailsServiceImpl(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    /**
     * Looks up an account by email and adapts it into the shape Spring Security understands.
     *
     * @param email the login email being authenticated (Spring Security's "username" concept)
     * @return a Spring Security user with the account's password hash and role-based authority
     * @throws UsernameNotFoundException if no account has that email
     */
    @Override
    public UserDetails loadUserByUsername(String email) throws UsernameNotFoundException {
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new UsernameNotFoundException("No user with email " + email));

        return org.springframework.security.core.userdetails.User
                .withUsername(user.getEmail())
                .password(user.getPasswordHash())
                .authorities("ROLE_" + user.getRole().name())
                .build();
    }
}
