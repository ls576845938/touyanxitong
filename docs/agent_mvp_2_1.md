# Alpha Radar Agent MVP 2.1 - 产品验收增强版

## 架构概述

```
用户输入 → Router (task type 识别)
         → Orchestrator (工具调用 + 上下文收集)
         → Runtime Adapter (Mock / Real / Hermes/OpenClaw 预留)
         → Guardrails (合规替换 + 免责声明)
         → Artifact (产物持久化 + 证据链)
```

- **orchestrator.py**: 任务编排核心，含 task type 自动识别、上下文收集、工具调用、步骤记录
- **runtime/**: 运行适配器。`MockRuntimeAdapter` 为默认实现；`RealRuntimeAdapter` 在配置 `openai_api_key` 时启用；`HermesRuntimeAdapter` / `OpenClawRuntimeAdapter` 为预留占位（`NotImplementedError`）
- **tools/**: 19 个标准化数据工具（market / industry / scoring / evidence / report），通过 `ToolSpec` 定义 input/output schema
- **guardrails.py**: 禁用词替换 + `RISK_DISCLAIMER` 自动追加
- **skills/**: 系统 Skill 模板（5 类投研场景）+ 用户自定义 Skill 持久化

## API 列表

### 已有 API (MVP 2.0)
- `POST /api/agent/runs` - 创建投研任务（返回 202）
- `GET /api/agent/runs/{run_id}` - 查询任务状态和最新产物
- `GET /api/agent/runs/{run_id}/steps` - 获取执行步骤
- `GET /api/agent/runs/{run_id}/artifacts` - 获取产物列表
- `POST /api/agent/skills` - 保存 Skill
- `GET /api/agent/skills` - 列出 Skills（含系统 + 自定义）

### 新增 API (MVP 2.1)
- `GET /api/agent/runs/{run_id}/events` - SSE 事件流（新增）
- `GET /api/agent/tools` - 工具清单（`ToolSpec[]`，新增）
- `GET /api/agent/tools/mcp-manifest` - MCP-ready JSON manifest（新增）
- `POST /api/agent/runs/{run_id}/followups` - 多轮追问（新增）
- `GET /api/agent/runs/{run_id}/messages` - 追问历史（新增）

## SSE 事件格式

接口：`GET /api/agent/runs/{run_id}/events`
返回 `text/event-stream`，每条 `data: {...}\n\n`

- `run_created` — `{status}` — 首次连接回放
- `run_started` — `{}` — pending → running
- `step_started` / `step_completed` — `{id, step_name, agent_role, status, input/output}` — 步骤事件
- `tool_call_started` / `tool_call_completed` — `{id, tool_name, input/output, latency_ms, success}` — 工具调用
- `artifact_created` — `{id, artifact_type, title}` — 新产物
- `run_completed` / `run_failed` — `{status, error_message, completed_at}` — 终止状态
- `heartbeat` — `{}` — 每 10 秒
- `error` — `{detail}` — run 不存在

说明：SSE 为 poll-to-SSE bridge，轮询间隔 1.5 秒。已完成 run 重放所有事件后立即关闭；运行中 run 持续推送直到完成或客户端断开。

## ToolSpec / MCP-ready 格式

共注册 **19 个工具**（market 4 + industry 4 + scoring 4 + evidence 4 + report 3），每个工具由 `ToolSpec` 描述：`name`, `category`, `description`, `input_schema`, `output_schema`, `read_only`, `risk_level`, `timeout_ms`, `examples`, `unavailable_behavior`。

### MCP Manifest (`GET /api/agent/tools/mcp-manifest`)

```json
{
  "protocol": "mcp",
  "version": "1.0",
  "serverInfo": {
    "name": "alpha-radar-agent",
    "version": "2.1.0"
  },
  "tools": [
    {
      "name": "get_stock_basic",
      "description": "查询股票基础信息...",
      "inputSchema": { "type": "object", "properties": {...} }
    },
    ...
  ]
}
```

该 manifest 遵循 MCP 协议工具发现格式，可被外部 Agent 框架（Hermes、OpenClaw 等）直接消费。

## Follow-up 使用方式

### 发起追问
```
POST /api/agent/runs/{run_id}/followups
{
  "message": "请展开分析风险因素",
  "mode": "expand_risk",        // 支持 auto / explain / expand_risk / evidence_drilldown / compare / generate_checklist
  "save_as_artifact": false     // 是否将追问回答保存为产物
}
```

### 追问模式
| mode | 用途 |
|---|---|
| `auto` | 自动识别 |
| `explain` | 解释说明 |
| `expand_risk` | 风险因素展开 |
| `evidence_drilldown` | 证据深入分析 |
| `compare` | 对比分析 |
| `generate_checklist` | 生成跟踪检查清单 |

### 保存为 Artifact
当 `save_as_artifact: true` 时，追问回答会作为 `artifact_type = "followup_note"` 的产物写入，可通过 `GET /api/agent/runs/{run_id}/artifacts` 查询。

### 追问历史
```
GET /api/agent/runs/{run_id}/messages
```
返回按时间排序的追问记录，含 `message_id`, `mode`, `message`, `answer_md`, `evidence_refs`。

### 实现说明
MVP 2.1 追问基于 mock 模板生成（无真实 AI 调用），回答经过 guardrails 合规检查和免责声明追加。追问仅限已完成的报告中展开。

## Guardrails 规则

### 禁用词替换（13 条）
- `买入`→`纳入观察池` `卖出`→`移出观察并复核风险` `满仓`→`提高关注度但控制风险暴露` `梭哈`→`避免单一方向过度暴露`
- `稳赚`→`存在不确定性` `必涨`→`仍需进一步确认` `无风险`→`风险尚未充分暴露` `抄底`→`等待趋势确认`
- `逃顶`→`观察风险释放情况` `重仓`→`控制仓位风险` `加杠杆`→`谨慎评估风险暴露`
- `翻倍确定性`→`具备一定增长潜力但需验证` `保证收益`→`收益预期需独立评估`

### 正则替换
- `建议加仓` → `建议跟踪观察`
- `建议减仓` → `建议复核风险暴露`
- `目标价:? 数字` → `估值情景需独立复核`

### 免责声明机制
所有输出末尾自动追加：
```
本报告仅用于投研分析和信息整理，不构成任何投资建议。市场有风险，决策需独立判断。
```
Claim 级别的 `risk_disclaimer` 放于 content_json 顶层。

## 本地运行

### 后端启动
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 前端启动
```bash
cd frontend
npm run dev
```

### 运行测试
```bash
cd backend
pytest app/tests/test_agent.py -q
python scripts/run_agent_eval.py
```

### 前端检查
```bash
cd frontend
npm run typecheck
npm run build
```

## 5 类投研场景

| Task Type | 触发关键词 | 工作流 |
|---|---|---|
| `stock_deep_research` | 股票名称/代码 | 基础信息 → 趋势 → 行业映射 → 评分 → 证据链 |
| `industry_chain_radar` | 产业链、行业、节点 | 行业映射 → 产业链节点 → 热力图 → 关联股票 |
| `trend_pool_scan` | 筛选、股票池、动量 | 动量排名 → 评分排行 → 覆盖状态 |
| `tenbagger_candidate` | 十倍股、早期特征 | 评分排行 → 动量排名 → 覆盖状态 |
| `daily_market_brief` | 日报、简报、复盘 | 最新日报 → 行业热度 → 动量排名 |

## Hermes / OpenClaw 后续接入建议

### Hermes
- 通过 MCP/HTTP tools sidecar 接入
- 使用 `GET /api/agent/tools/mcp-manifest` 提供的 ToolSpec 清单发现和调用 Alpha Radar 数据工具
- **当前状态**：`hermes_adapter.py` 为 `NotImplementedError` 占位，未安装 Hermes 依赖

### OpenClaw
- 可作为 Gateway / 多端入口，转发请求到 Alpha Radar Agent API
- 通过 manifest 中的 tool 定义进行路由
- **当前状态**：`openclaw_adapter.py` 为 `NotImplementedError` 占位，未安装 OpenClaw 依赖

## 已实现功能
- [x] 5 类投研场景自动识别
- [x] 异步后台任务执行（BackgroundTasks）
- [x] 合规检查与 guardrails（禁用词替换 + 免责声明）
- [x] 只读工具调用审计（AgentToolCall 表持久化）
- [x] 报告动态图表（`:::chart{"type":"candle"}:::` 语法）
- [x] SSE 事件流（MVP 2.1 新增）
- [x] MCP-ready 工具标准化（MVP 2.1 新增）
- [x] 多轮追问（MVP 2.1 新增，mock 模板生成）

## 预留功能（后续版本）
- [ ] 真正的 token-level streaming（当前为 poll-to-SSE bridge）
- [ ] 报告导出 PDF
- [ ] 完整 MCP Server 启动（当前仅提供 /mcp-manifest 端点）
- [ ] Hermes sidecar 接入
- [ ] OpenClaw Gateway 接入
- [ ] 多用户隔离与权限
