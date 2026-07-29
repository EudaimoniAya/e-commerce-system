## ADDED Requirements

### Requirement: User summary for cross-domain read

user 域 SHALL 提供跨域只读 DTO `UserSummary`，字段 SHALL 为 `id`（UUID 字符串）与 `nickname`；SHALL NOT 包含 `email` 或 `password_hash`。`UserService` SHALL 提供 `get_user_summary(user_id)`：用户存在且 `is_active=true` 时返回 `UserSummary`；用户不存在时 SHALL 抛出 **404**；`is_active=false` 时 SHALL 抛出 **422**。

#### Scenario: 有效用户返回摘要

- **WHEN** ordering 或其他域调用 `get_user_summary` 且用户存在且 `is_active=true`
- **THEN** SHALL 返回 `UserSummary` 含 `id` 与 `nickname`
- **AND** SHALL NOT 包含 email

#### Scenario: 用户不存在返回 404

- **WHEN** 调用 `get_user_summary` 且 `user_id` 不存在
- **THEN** SHALL 抛出 HTTP 404

#### Scenario: 用户禁用返回 422

- **WHEN** 调用 `get_user_summary` 且用户 `is_active=false`
- **THEN** SHALL 抛出 HTTP 422
