## MODIFIED Requirements

### Requirement: Application configuration from environment

系统 SHALL 通过 `pydantic-settings` 从环境变量加载配置，至少包含 `DATABASE_URL`（asyncmy 连接串）与 `APP_ENV`。配置不得硬编码于业务代码。本 change 扩展：Settings SHALL 另支持 JWT 相关字段（见 `infra-auth` capability），与本 requirement 的配置加载机制一致。

#### Scenario: 缺少 DATABASE_URL 时应用启动或测试失败

- **WHEN** 未设置 `DATABASE_URL` 且代码路径需要数据库连接
- **THEN** 系统 SHALL 以明确错误失败（启动失败或测试 setup 失败），而非静默使用默认值连接错误主机

#### Scenario: DATABASE_URL 指向指定 MySQL 库

- **WHEN** `DATABASE_URL` 设置为有效的 `mysql+asyncmy://` 连接串
- **THEN** 系统 SHALL 使用该 URL 创建 async SQLAlchemy engine

### Requirement: Declarative base for ORM models

系统 SHALL 提供共享的 SQLAlchemy `DeclarativeBase`（或等价 `Base`），供 infra 与后续业务域 ORM 模型继承。`Base.metadata` SHALL 配置 `naming_convention`，统一索引、唯一、外键、主键、检查约束的命名规则。

#### Scenario: Base 可被模型模块导入

- **WHEN** infra 验证模型或 user 域 `User` 模型继承 `Base`
- **THEN** Alembic autogenerate 或 migration 脚本 SHALL 能引用该 metadata

#### Scenario: naming_convention 生效

- **WHEN** migration 创建带唯一约束的 `users.email`
- **THEN** 数据库中的唯一约束名 SHALL 符合 `uq_%(table_name)s_%(column_0_name)s` 模式（即 `uq_users_email`）

## ADDED Requirements

### Requirement: Alembic registers business domain models

Alembic `env.py` SHALL 导入已实现的业务域 ORM 模块，使 `target_metadata` 包含业务表定义。本 change SHALL 导入 `app.user.models`。

#### Scenario: upgrade head 创建 users 表

- **WHEN** 在已有 `_infra_migration_smoke` 的库上执行 `alembic upgrade head`（含 user-auth migration）
- **THEN** 数据库 SHALL 存在 `users` 表
- **AND** Alembic 版本记录 SHALL 更新
