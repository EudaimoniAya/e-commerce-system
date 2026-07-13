# infra-database

## Purpose

异步 MySQL 连接基础设施：环境配置、SQLAlchemy 2 AsyncSession、Alembic 迁移管线、双库约定与 integration 测试惯例。

## Requirements

### Requirement: Application configuration from environment

系统 SHALL 通过 `pydantic-settings` 从环境变量加载配置，至少包含 `DATABASE_URL`（asyncmy 连接串）与 `APP_ENV`。配置不得硬编码于业务代码。Settings SHALL 另支持 JWT 相关字段（见 `infra-auth` capability），与本 requirement 的配置加载机制一致。

#### Scenario: 缺少 DATABASE_URL 时应用启动或测试失败

- **WHEN** 未设置 `DATABASE_URL` 且代码路径需要数据库连接
- **THEN** 系统 SHALL 以明确错误失败（启动失败或测试 setup 失败），而非静默使用默认值连接错误主机

#### Scenario: DATABASE_URL 指向指定 MySQL 库

- **WHEN** `DATABASE_URL` 设置为有效的 `mysql+asyncmy://` 连接串
- **THEN** 系统 SHALL 使用该 URL 创建 async SQLAlchemy engine

### Requirement: Async database session dependency

系统 SHALL 提供 FastAPI 可注入的 async 数据库 Session 依赖（`get_db`），基于 SQLAlchemy 2 `AsyncSession`；请求结束时 SHALL 正确关闭 session。

#### Scenario: 依赖注入返回可用 AsyncSession

- **WHEN** 集成测试通过 `get_db` 获取 session 并执行 `SELECT 1`
- **THEN** 查询 SHALL 成功返回且无未关闭连接泄漏

### Requirement: Declarative base for ORM models

系统 SHALL 提供共享的 SQLAlchemy `DeclarativeBase`（或等价 `Base`），供 infra 与后续业务域 ORM 模型继承。`Base.metadata` SHALL 配置 `naming_convention`，统一索引、唯一、外键、主键、检查约束的命名规则。

#### Scenario: Base 可被模型模块导入

- **WHEN** infra 验证模型或 user 域 `User` 模型继承 `Base`
- **THEN** Alembic autogenerate 或 migration 脚本 SHALL 能引用该 metadata

#### Scenario: naming_convention 生效

- **WHEN** migration 创建带唯一约束的 `users.email`
- **THEN** 数据库中的唯一约束名 SHALL 符合 `uq_%(table_name)s_%(column_0_name)s` 模式（即 `uq_users_email`）

### Requirement: Alembic migration pipeline

系统 SHALL 集成 Alembic 作为 schema 的唯一真相来源；SHALL 提供可执行的 `alembic upgrade head`，且首条 migration SHALL 创建 infra 验证表 `_infra_migration_smoke`（非业务域表）。

#### Scenario: upgrade head 创建 smoke 表

- **WHEN** 对空 MySQL 库执行 `alembic upgrade head`
- **THEN** 数据库 SHALL 存在表 `_infra_migration_smoke`
- **AND** SHALL 存在 Alembic 版本记录

#### Scenario: smoke 表支持基本 CRUD

- **WHEN** 集成测试在 transaction 内向 `_infra_migration_smoke` 插入一行并查询
- **THEN** 插入与查询 SHALL 成功
- **AND** 测试 rollback 后该行 SHALL 不可被后续测试读到（零副作用）

### Requirement: Dual database naming convention

系统 SHALL 支持至少两个逻辑库名：`ecommerce_dev`（本地开发）与 `ecommerce_test`（测试）；二者 SHALL 使用相同 MySQL 大版本与 charset 配置（utf8mb4）。

#### Scenario: 测试配置使用 test 库

- **WHEN** pytest integration 测试运行
- **THEN** `DATABASE_URL` SHALL 指向 `ecommerce_test`（或等价测试库名），而非 `ecommerce_dev`

### Requirement: Integration test marker

系统 SHALL 在 pytest 中注册 `@pytest.mark.integration` marker，用于标识依赖 MySQL 的测试；文档或 pyproject SHALL 说明 marker 含义。

#### Scenario: integration 测试被正确标记

- **WHEN** 查看需 MySQL 的测试模块
- **THEN** 这些测试 SHALL 带有 `integration` marker

### Requirement: CI runs migrations before tests

CI pipeline SHALL 在运行 pytest 之前对测试库执行 `alembic upgrade head`。

#### Scenario: CI job 迁移后运行测试

- **WHEN** GitHub Actions CI job 执行
- **THEN** SHALL 在 mysql service 就绪后创建/使用测试库并执行 `alembic upgrade head`
- **AND** 随后 SHALL 执行 `task ci`（ruff + pytest）且 integration 测试通过

### Requirement: Alembic registers business domain models

Alembic `env.py` SHALL 导入已实现的业务域 ORM 模块，使 `target_metadata` 包含业务表定义。当前 SHALL 导入 `app.user.models`。

#### Scenario: upgrade head 创建 users 表

- **WHEN** 在已有 `_infra_migration_smoke` 的库上执行 `alembic upgrade head`（含 user-auth migration）
- **THEN** 数据库 SHALL 存在 `users` 表
- **AND** Alembic 版本记录 SHALL 更新
