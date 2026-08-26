# ai-support-agent

## MODIFIED Requirements

### Requirement: LLM client protocol with mock and DeepSeek

系统 SHALL 提供 `LLMClient` 协议（`generate(messages) -> str`）、`FakeLLMClient`（可编程输出的产品侧假实现）与 `DeepSeekClient`（OpenAI 兼容 HTTP）。`LLM_PROVIDER=mock` 时 SHALL 使用 `FakeLLMClient`；`deepseek` 时 SHALL 使用 DeepSeekClient。pytest / CI SHALL 使用 `FakeLLMClient`，SHALL NOT 发起真实 DeepSeek HTTP。SHALL NOT 保留名为 `MockLLMClient` 的产品类。配置键与取值 `mock` SHALL NOT 因本 requirement 而改名。

#### Scenario: FakeLLMClient 返回编程输出

- **WHEN** 注入 FakeLLMClient 并设定固定字符串
- **THEN** `generate` SHALL 返回该字符串且不访问网络

#### Scenario: CI 不调用 DeepSeek

- **WHEN** CI 或默认 pytest 加载 LLM 配置
- **THEN** `LLM_PROVIDER` SHALL 为 `mock`
