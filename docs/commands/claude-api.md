# /claude-api — 接入 Claude API

## 用途

在项目中接入 Claude / Anthropic API 或兼容 LLM Provider。

## 适用场景

- 项目需要调用 Claude API 做文本生成
- 封装 LLM Provider 做模型切换
- 接入 OpenRouter / Anthropic 兼容接口
- 把 Claude 作为功能模块底层模型

## 示例

```
/claude-api 接入 Anthropic SDK，封装 claudeClient
/claude-api 替换当前的 mock LLM provider 为真实 API
/claude-api 添加 claude-3-opus 支持
```

## 执行流程

1. 判断项目技术栈
2. 检查是否已有 AI client
3. 设计最小可用封装
4. 支持环境变量配置
5. 实现 client / sendMessage / retry / error handling / mock
6. 生成文档和示例

## 安全限制

- 不硬编码 API Key
- 不打印敏感值到日志
- 测试默认使用 mock
- 不提交真实 Key

## 风险等级

中等 — 涉及外部 API 调用，需要处理好错误和计费。

## 当前项目状态

Alpha Radar 已有 `backend/app/llm/provider.py`（OpenAI Provider），`/claude-api` 可以：
- 新增 Anthropic Provider 作为替代
- 封装统一 LLM 接口支持多模型切换
- 或仅生成调用示例文档
