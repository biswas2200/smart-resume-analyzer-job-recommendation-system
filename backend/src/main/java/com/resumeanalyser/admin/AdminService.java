package com.resumeanalyser.admin;

import com.resumeanalyser.account.User;
import com.resumeanalyser.account.UserRepository;
import com.resumeanalyser.account.UserRole;
import com.resumeanalyser.account.dto.UserDto;
import com.resumeanalyser.common.ResourceNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

/**
 * Administrator tools: look an account up and set its role.
 */
@Service
public class AdminService {

    private final UserRepository userRepository;

    public AdminService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    /** Looks an account up by its login email, for the admin UI's "find user" step. */
    public UserDto findByEmail(String email) {
        return userRepository.findByEmail(email)
                .map(this::toDto)
                .orElseThrow(() -> new ResourceNotFoundException("No user with email " + email));
    }

    /**
     * Sets an account's access level.
     *
     * @throws ResourceNotFoundException if no account has that id
     */
    @Transactional
    public UserDto updateRole(UUID userId, UserRole role) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("No user with id " + userId));
        user.setRole(role);
        return toDto(userRepository.save(user));
    }

    private UserDto toDto(User user) {
        return new UserDto(user.getId(), user.getEmail(), user.getRole(), user.getCreatedAt());
    }
}
