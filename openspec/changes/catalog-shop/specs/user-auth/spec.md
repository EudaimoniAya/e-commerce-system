## ADDED Requirements

### Requirement: Platform administrator flag on users

系统 SHALL 在 `users` 表提供 `is_admin` 列（BOOLEAN，NOT NULL，默认 false），用于标识平台管理员身份；本 change SHALL 通过 migration seed 至少一名 `is_admin=true` 的用户。

#### Scenario: 用户表包含 is_admin 列

- **WHEN** 查询 `users` 表结构或 ORM 模型
- **THEN** SHALL 包含列 `is_admin`（BOOLEAN，默认 false）

#### Scenario: Seed 管理员存在

- **WHEN** 执行 migration `003` 至 head 后查询 `users` 表
- **THEN** SHALL 存在 `email` 为 `114514yyut@qq.com` 且 `is_admin` 为 true 的用户记录
- **AND** 该用户 `password_hash` SHALL 为 pwdlib 哈希（非明文存储）

## MODIFIED Requirements

### Requirement: Users table with UUID primary key

系统 SHALL 在 **user 域** 拥有 `users` 表；主键 SHALL 为 UUID v4（应用层生成，非自增整数）。

#### Scenario: 用户记录包含必需字段

- **WHEN** 查询 `users` 表结构或 ORM 模型
- **THEN** SHALL 包含列：`id`（UUID）、`email`（唯一）、`password_hash`、`nickname`、`is_active`（默认 true）、`is_admin`（默认 false）、`created_at`、`updated_at`
- **AND** `email` SHALL 有唯一约束
