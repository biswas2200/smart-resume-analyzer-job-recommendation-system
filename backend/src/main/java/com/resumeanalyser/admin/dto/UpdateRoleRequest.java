package com.resumeanalyser.admin.dto;

import com.resumeanalyser.account.UserRole;
import jakarta.validation.constraints.NotNull;

/**
 * Body of {@code PATCH /admin/users/{id}/role}: the access level to give the
 * account (USER / ADMIN).
 */
public record UpdateRoleRequest(@NotNull UserRole role) {}
