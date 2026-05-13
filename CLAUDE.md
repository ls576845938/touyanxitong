# CLAUDE.md — Alpha Radar 项目规范

## 项目概述

Alpha Radar 是一个 AI 驱动的投研系统，用于产业趋势分析和十倍股早期特征发现。

- 后端: Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL
- 前端: Next.js 14, React, TypeScript, Tailwind CSS
- 测试: pytest (后端), tsc --noEmit + npm run build (前端)
- 包管理: pip (后端 .venv), npm (前端)

## 核心原则

1. 系统定位为"投研判断与复盘系统"，不是"交易决策系统"
2. 不输出买入/卖出/满仓/梭哈等投资建议
3. 所有报告附风险免责声明
4. 数据质量 FAIL 时不扩大市场范围，不输出确定性结论
5. 不接券商交易接口

## 项目结构

```
alpha-radar/
├── backend/
│   ├── app/
│   │   ├── agent/          # Agent 系统 (orchestrator, tools, runtimes)
│   │   ├── api/            # FastAPI 路由 (market, stocks, industry, research, etc.)
│   │   ├── db/             # 数据库模型和 session 管理
│   │   ├── engines/        # 引擎层 (scoring, thesis, trend, risk, etc.)
│   │   ├── llm/            # LLM Provider
│   │   ├── pipeline/       # 每日数据管道
│   │   └── risk/           # 风险预算仓位计划 (MVP 3.2)
│   ├── scripts/            # 运维脚本
│   └── tests/              # 测试
├── frontend/
│   └── src/
│       ├── app/            # Next.js 页面
│       ├── components/     # React 组件
│       └── lib/            # API 客户端和工具
└── docs/                   # 文档
```

## 数据库

- PostgreSQL 16 (生产), SQLite (测试)
- 36+ 模型, SCHEMA_VERSION=24
- 迁移系统: `backend/app/db/session.py` → `SCHEMA_MIGRATIONS`

## 关键约束

- 不修改 scoring_engine 权重 (除非 review 数据验证后)
- 不删除 Golden Cases 测试
- 不降低 guardrails 约束
- 前端不发买卖建议
- Agent tools read_only 优先

## Slash Commands

本项目支持以下 Claude Code 命令：

| 命令 | 用途 |
|---|---|
| `/simplify` | 低风险简化代码、文档和结构 |
| `/debug` | 系统化排查 bug，先定位根因再最小修复 |
| `/batch` | 批量处理小任务，分批执行，可回滚 |
| `/loop` | 最多 5 轮的计划→执行→测试→审查→修复闭环 |
| `/claude-api` | 接入 Claude / Anthropic API |

详见 `docs/commands/command-index.md`。

## 默认规则

1. 所有命令执行前先读项目结构
2. 优先小步修改
3. 必须输出报告
4. 涉及核心业务逻辑、资金、交易、数据库、鉴权的修改必须先暂停确认
5. 不允许为了通过测试而删除测试
6. 不允许绕过错误
7. 不允许无计划大规模重构
8. 不允许泄露 API Key 或敏感配置

## 常用命令

```bash
# 后端测试
cd backend && python -m pytest app/tests/ -q

# 前端检查
cd frontend && npx tsc --noEmit && npm run build

# Agent Eval
cd backend && python scripts/run_agent_eval.py

# 启动项目
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 &
cd frontend && npm run start -- --hostname 0.0.0.0 --port 3000 &
```
