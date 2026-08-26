# user-auth

## MODIFIED Requirements

### Requirement: SMS OTP send endpoint

系统 SHALL 提供 `POST /auth/sms/send`，接受 JSON 请求体 `{ "phone": "<原始输入>" }`；SHALL 规范化手机号、生成 6 位数字 OTP、写入 Redis（key `sms:otp:{normalized_phone}`，TTL 默认 300 秒），并通过 `FakeSmsProvider` 发送（dev/test/CI 不调用真实网关）。SHALL NOT 保留名为 `MockSmsProvider` 的产品类。本 requirement SHALL NOT 引入短信 provider 配置或真实网关。

#### Scenario: 发送成功返回统一成功响应

- **WHEN** 客户端提交可规范化为合法 11 位大陆手机号的 `phone` 且未触发限流
- **THEN** 响应状态码 SHALL 为 200
- **AND** Redis SHALL 存在对应 OTP key
- **AND** 响应 SHALL NOT 因该手机号是否已注册而差异（防用户枚举）

#### Scenario: 手机号格式非法返回 422

- **WHEN** 客户端提交的 `phone` 无法规范化为 `^1[3-9]\d{9}$`
- **THEN** 响应状态码 SHALL 为 422
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON

#### Scenario: 发送冷却期内重复发送返回 429

- **WHEN** 同一规范化手机号在冷却期（默认 60 秒）内再次请求 send
- **THEN** 响应状态码 SHALL 为 429
- **AND** 响应 SHALL 符合 `infra-api-errors` 统一 error JSON

#### Scenario: 日发送次数超限返回 429

- **WHEN** 同一规范化手机号当日 send 次数已达上限（默认 10 次）
- **THEN** 响应状态码 SHALL 为 429
