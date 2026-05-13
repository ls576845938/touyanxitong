# Alpha Radar — Claude Code Command Index

## 命令总览

| 命令 | 用途 | 改代码 | 风险 | 示例 |
|---|---|---|---|---|
| `/simplify` | 简化代码/文档/结构 | 可能 | 中 | `/simplify src/app/dashboard` |
| `/debug` | 系统化排查 bug | 可能 | 中 | `/debug 页面白屏` |
| `/batch` | 批量处理小任务 | 是 | 中高 | `/batch 补充 loading 状态` |
| `/loop` | 多轮闭环迭代 | 是 | 中高 | `/loop 修复失败的测试` |
| `/claude-api` | 接入 Claude API | 是 | 中 | `/claude-api 封装 anthropic client` |

## 推荐使用顺序

### 日常开发

1. `/debug` — 遇到 bug 先用，定位根因再修
2. `/simplify` — 代码写完后清理冗余
3. `/loop` — 需要反复迭代时用

### 批量工作

4. `/batch` — 批量 lint/测试/文档整理

### 集成工作

5. `/claude-api` — 需要接入 LLM 时用

## 哪些命令需要谨慎

- **`/batch`**: 批量操作面广，必须先审核 Batch Plan
- **`/loop`**: 多轮修改可能累积风险，每轮必须审查
- **`/claude-api`**: 涉及外部 API Key 和计费

## 哪些命令不会修改代码

所有命令都可能修改代码，但 `/simplify` 和 `/debug` 在大多数情况下只做最小改动。

## 当前项目适配说明

- Alpha Radar 是 Python (FastAPI) + TypeScript (Next.js) 项目
- 已有 LLM Provider (`backend/app/llm/provider.py`) — `/claude-api` 可以作为扩展
- 测试框架: pytest (后端), Jest/tsc (前端)
- 包管理: pip (后端), npm (前端)

## 文件结构

```
.claude/commands/
├── simplify.md
├── debug.md
├── batch.md
├── loop.md
└── claude-api.md

docs/commands/
├── command-index.md    (this file)
├── simplify.md
├── debug.md
├── batch.md
├── loop.md
└── claude-api.md

CLAUDE.md               (slash commands section added)
```
