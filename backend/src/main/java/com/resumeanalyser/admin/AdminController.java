package com.resumeanalyser.admin;

import com.resumeanalyser.account.dto.UserDto;
import com.resumeanalyser.admin.dto.UpdateRoleRequest;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

/**
 * Administrator-only account management. Every endpoint is gated twice:
 * {@code /admin/**} requires ROLE_ADMIN in {@code SecurityConfig}, and each
 * method repeats it with {@code @PreAuthorize} so the rule is visible where
 * the endpoint is declared.
 */
@RestController
@RequestMapping("/admin")
@PreAuthorize("hasRole('ADMIN')")
public class AdminController {

    private final AdminService adminService;

    public AdminController(AdminService adminService) {
        this.adminService = adminService;
    }

    /** Finds an account by email -- the first step of changing its role. */
    @GetMapping("/users")
    public UserDto findUser(@RequestParam String email) {
        return adminService.findByEmail(email);
    }

    /**
     * Changes an account's access level (USER / ADMIN). The
     * change is effective on the account's next request ({@code GET /auth/me}
     * reads the role from the database, not the token).
     */
    @PatchMapping("/users/{id}/role")
    public UserDto updateRole(@PathVariable UUID id, @Valid @RequestBody UpdateRoleRequest request) {
        return adminService.updateRole(id, request.role());
    }
}
