## ADDED Requirements

### Requirement: Admin authorization dependency

user 域 SHALL 在 `app/user/deps.py` 提供 `require_admin` FastAPI 依赖：解析 JWT 得到 `user_id` 并查库；当用户 `is_admin` 不为 true 时 SHALL 返回 **403**；无 token 或 token 无效 SHALL 返回 **401**；用户不存在 SHALL 返回 **401**。

#### Scenario: 管理员通过鉴权

- **WHEN** 已认证且 `is_admin=true` 的用户请求依赖 `require_admin` 的端点
- **THEN** 依赖 SHALL 返回该用户 ID（或继续处理请求）

#### Scenario: 非管理员返回 403

- **WHEN** 已认证但 `is_admin=false` 的用户请求依赖 `require_admin` 的端点
- **THEN** 响应状态码 SHALL 为 403

#### Scenario: 未认证返回 401

- **WHEN** 客户端未携带有效 Bearer token 请求依赖 `require_admin` 的端点
- **THEN** 响应状态码 SHALL 为 401
