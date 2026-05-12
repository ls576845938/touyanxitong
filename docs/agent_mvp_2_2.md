# Alpha Radar Agent MVP 2.2 - 真流式与导出增强版

## 架构概述

```
用户输入 → Router (task type 识别)
         → Orchestrator (工具调用 + 上下文收集)
         → Runtime Adapter (stream_run 支持 token-level delta)
         → AgentEventBus (asyncio.Queue 实时推送 + agent_events 持久化)
         → Guardrails (合规替换 + 免责声明)
         → Artifact (产物持久化 + 证据链)
         → Export (Markdown / HTML 下载)
```

- **events.py**: `AgentEventBus` 单例，per-run `asyncio.Queue` 发布/订阅；`publish_event()` 同时写入 `agent_events` 表并推送到内存订阅者
- **orchestrator.py**: `publish_event()` 调用贯穿所有步骤和工具调用；运行时支持 `token_delta` 事件
- **runtime/**: `RuntimeAdapter` 新增 `stream_run()` 抽象；Mock 按段落模拟 token delta；Real 调用 OpenAI streaming API
- **api.py**: SSE 从轮询改为 EventBus 实时推送 + 事件回放；新增导出端点和 LLM-first 追问
- **specs.py**: 工具输入/输出使用 Pydantic `model_json_schema()` 生成标准 JSON Schema

## MVP 2.1 → 2.2 变更清单

| 变更 | 说明 |
|------|------|
| SSE 从 poll-to-SSE bridge 改为 EventBus 实时推送 | `_event_stream()` 使用 `subscribe()`/`unsubscribe()`，heartbeat 10 秒 |
| 新增 `seq` 字段和 `since_seq` 参数 | `AgentEvent.seq` 单调递增，支持断线重连后的增量回放 |
| 新增 `token_delta` 事件 | 运行时逐 token 推送，客户端实现打字机效果 |
| 新增 `followup_started/followup_token_delta/followup_completed` 事件 | 追问流式事件 |
| 新增报告导出端点 | Markdown 下载 (`/export/markdown`) 和 HTML 下载 (`/export/html`) |
| Follow-up 改为 LLM-first | 配置 `openai_api_key` 时优先调用 LLM，附带上线文（工具调用 + 历史追问），失败回退确定性模板 |
| ToolSpec JSON Schema | 使用 Pydantic `model_json_schema()` 替代手写 dict |
| Symbol Extraction 加固 | `len(stock.name) >= 2` 过滤短词，避免误识别 AI/A 等 |
| MCP manifest 版本升级 | `server_info.version` → `"2.2"` |
| 新增 `stream_run()` | `RuntimeAdapter` 新增异步 streaming 接口 |

## API 列表

### 已有 API (MVP 2.0/2.1)
- `POST /api/agent/runs` — 创建投研任务（返回 202）
- `GET /api/agent/runs/{run_id}` — 查询任务状态和最新产物
- `GET /api/agent/runs/{run_id}/steps` — 获取执行步骤
- `GET /api/agent/runs/{run_id}/artifacts` — 获取产物列表
- `GET /api/agent/runs/{run_id}/events` — SSE 事件流（2.2 增强为 EventBus 推送）
- `GET /api/agent/runs/{run_id}/messages` — 追问历史
- `POST /api/agent/runs/{run_id}/followups` — 多轮追问（2.2 增强为 LLM-first）
- `POST /api/agent/skills` — 保存 Skill
- `GET /api/agent/skills` — 列出 Skills（含系统 + 自定义）
- `GET /api/agent/tools` — 工具清单 (`ToolSpec[]`)
- `GET /api/agent/tools/mcp-manifest` — MCP-ready JSON manifest

### 新增 API (MVP 2.2)
- `GET /api/agent/runs/{run_id}/export/markdown` — 下载 Markdown 格式报告（Content-Disposition attachment）
- `GET /api/agent/runs/{run_id}/export/html` — 下载无脚本安全 HTML 页面（可浏览器打印 PDF）

## EventBus 架构

`AgentEventBus` 轻量级进程内事件总线：

- **订阅**: `subscribe(run_id)` 返回 `(asyncio.Queue, loop)`，客户端 `queue.get()` 等待事件
- **发布**: `publish_event(session, run_id, event_type, payload)` 同时写入 `agent_events` 表（`session.flush()`）并推送到内存订阅者
- **序列号**: `bus.next_seq(run_id)` 单调递增，持久化到 `AgentEvent.seq`
- **清理**: `unsubscribe(run_id, queue)` 移除订阅者，无订阅者时清理计数器
- **线程安全**: `asyncio.run_coroutine_threadsafe()` 跨线程投递，可被后台线程调用
- **事件持久化**: `AgentEvent` 表包含 `run_id, seq, event_type, payload_json, created_at`，支持回放

## SSE 事件格式 (v2.2)

接口：`GET /api/agent/runs/{run_id}/events?since_seq=N`

`since_seq=0`（默认）回放全部事件；指定 `since_seq` 只返回 `seq > N` 的事件。

所有事件增加 `seq` 字段：

```json
{
  "event": "tool_call_completed",
  "run_id": 42,
  "timestamp": "2026-05-12T10:00:00+00:00",
  "payload": { "tool_name": "get_stock_basic", "success": true },
  "seq": 15
}
```

### 事件类型（2.2 新增粗体标记）

| 事件 | 说明 |
|------|------|
| `run_created` | 任务创建（回放首个事件） |
| `run_started` | pending → running |
| `step_started` / `step_completed` | 步骤开始/完成 |
| `tool_call_started` / `tool_call_completed` | 工具调用开始/完成（含 `latency_ms`） |
| **`token_delta`** | 运行时 token 增量（`payload.delta`） |
| `artifact_created` | 新产物 |
| **`followup_started`** | 追问开始 |
| **`followup_token_delta`** | 追问 token 增量 |
| **`followup_completed`** | 追问完成 |
| `run_completed` / `run_failed` | 终止状态 |
| `heartbeat` | 每 10 秒 |
| `error` | run 不存在 |

## Token-level Streaming

### MockRuntimeAdapter

`stream_run()` 按段落拆分 `content_md`，逐段调用 `on_event("token_delta", {"delta": paragraph + "\n\n"})`。

### RealRuntimeAdapter

`stream_run()` 调用 `OpenAIProvider.generate_research_report_stream()`，使用 `httpx.AsyncClient` 的 `stream=True` 模式逐 chunk 解析 SSE line，每收到一个 content token 调用 `on_event("token_delta", {"delta": token})`。

### Fallback 策略

如果 LLM streaming 调用失败，`RealRuntimeAdapter.stream_run()` 回退到 `MockRuntimeAdapter.run()` 获取完整内容，然后按段落模拟 token delta 输出。

## 报告导出

### Markdown 导出

`GET /api/agent/runs/{run_id}/export/markdown` 返回 `text/markdown` 内容。组合报告标题（`# `）+ `content_md` + 免责声明。内容已在 artifact 中经过 guardrails 清洗，不再重复清洗。

### HTML 导出

`GET /api/agent/runs/{run_id}/export/html` 返回无脚本安全 HTML。包含：
- 报告标题和正文（Markdown → 基本 HTML：h1/h2/h3、ul/li、hr、p，`:::chart` 标签替换为占位符）
- 参考来源（前 10 条）
- 免责声明
- 打印样式（`@media print`）
- 所有文本经过 HTML 转义，无脚本执行

### 浏览器打印 PDF

HTML 页面包含 `@media print` 样式规则，用户可直接使用浏览器 "打印 → 另存为 PDF" 生成 PDF。**后端不实现 PDF 生成**（项目无 PDF 依赖，浏览器原生打印质量更高且零维护）。

## Follow-up 增强

### LLM-first 策略

`_generate_followup_answer()` 在新版中的流程：

1. **读取上下文**：从数据库读取最新 artifact（content_md + 证据引用）、最近 10 条工具调用记录、最近 5 条历史追问
2. **LLM 生成**：如果配置了 `openai_api_key`，构建 system prompt（含回答规则约束）+ user message（含报告摘要、工具调用摘要、历史追问），调用 `OpenAIProvider.generate_followup_answer()`
3. **流式支持**：当传入 `on_event` 回调时，触发 `followup_started` → `followup_token_delta`（逐 token）→ `followup_completed` 事件
4. **Fallback**：LLM 调用失败或无 API key 时回退到 MVP 2.1 的确定性模板
5. **Guardrails**：结果经过 `sanitize_financial_output()` 清洗并追加免责声明

### 追问模式（不变）

`auto` / `explain` / `expand_risk` / `evidence_drilldown` / `compare` / `generate_checklist`

## ToolSpec JSON Schema

MVP 2.2 将所有工具的 input/output schema 从手写 dict 迁移到 Pydantic 模型：

```python
class GetStockBasicInput(BaseModel):
    symbol_or_name: str = Field(description="股票代码（如 000001）或股票名称")

input_schema = GetStockBasicInput.model_json_schema()
```

每个工具定义 `Input` / `Output` Pydantic 模型，`ToolSpec` 存储 `model_json_schema()` 结果。共 **19 个工具**（market 4 + industry 4 + scoring 4 + evidence 4 + report 3）。

MCP manifest 版本更新为 `"2.2"`，`tools` 数组使用 `spec.to_dict()` 输出完整字段（不仅是 MCP 最低要求），方便外部框架消费。

## Symbol Extraction 加固

`_extract_symbols()` 增加长度过滤 `len(stock.name) >= 2`，防止单字符名称（如 "A"、"B"）被误识别。6 位数字代码使用 `re.findall(r"(?<!\d)(\d{6})(?!\d)", prompt)`，不受该过滤影响。

## Guardrails 规则（不变）

### 禁用词替换（13 条）
买入/满仓/梭哈/重仓/加杠杆 → 中性观察表述；稳赚/必涨/无风险/翻倍确定性/保证收益 → 不确定性表述；卖出/逃顶 → 风险复核表述

### 正则替换（3 条）
- `建议加仓` → `建议跟踪观察`
- `建议减仓` → `建议复核风险暴露`
- `目标价[:：]?数字` → `估值情景需独立复核`

### 免责声明
```
本报告仅用于投研分析和信息整理，不构成任何投资建议。市场有风险，决策需独立判断。
```

## 本地运行

### 后端启动
```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 前端启动
```bash
cd frontend
npm run dev
```

### 运行测试
```bash
cd backend
.venv/bin/python -m pytest app/tests/test_agent.py app/tests/test_agent_events.py app/tests/test_agent_export.py -q
.venv/bin/python scripts/run_agent_eval.py
.venv/bin/python -m pytest -q
```

### 前端检查
```bash
cd frontend
npx tsc --noEmit && npm run lint && npm run build
```

## 5 类投研场景（不变）

| Task Type | 触发关键词 | 工作流 |
|---|---|---|
| `stock_deep_research` | 股票名称/代码 | 基础信息 → 趋势 → 行业映射 → 评分 → 证据链 |
| `industry_chain_radar` | 产业链、行业、节点 | 行业映射 → 产业链节点 → 热力图 → 关联股票 |
| `trend_pool_scan` | 筛选、股票池、动量 | 动量排名 → 评分排行 → 覆盖状态 |
| `tenbagger_candidate` | 十倍股、早期特征 | 评分排行 → 动量排名 → 覆盖状态 |
| `daily_market_brief` | 日报、简报、复盘 | 最新日报 → 行业热度 → 动量排名 |

## Hermes / OpenClaw 预留（不变）

- **Hermes**: 通过 MCP/HTTP tools sidecar 接入，使用 `GET /api/agent/tools/mcp-manifest` 工具清单发现和调用数据工具
- **OpenClaw**: Gateway 入口转发到 Alpha Radar Agent API
- **当前状态**: `hermes_adapter.py` / `openclaw_adapter.py` 均为 `NotImplementedError` 占位，未安装依赖

## 已实现功能
- [x] 5 类投研场景
- [x] 异步任务执行
- [x] SSE 事件流（2.1 poll-to-SSE → 2.2 EventBus 实时推送）
- [x] MCP-ready 工具清单（2.1 引入，2.2 JSON Schema 增强）
- [x] 多轮追问（2.1 引入，2.2 增强为 LLM-first + streaming）
- [x] EventBus 真正事件推送（2.2 新增）
- [x] Token-level streaming（2.2 新增，Mock + Real）
- [x] 报告导出 Markdown / HTML（2.2 新增）
- [x] 浏览器打印 PDF（2.2 新增，依赖浏览器原生功能）
- [x] ToolSpec JSON Schema（2.2 新增，Pydantic model_json_schema）
- [x] Symbol Extraction 加固（2.2 新增，短词过滤）
- [x] 事件持久化与 seq 回放（2.2 新增，agent_events 表 + since_seq）

## 已知限制
- 后端 PDF 生成未实现（项目无 PDF 依赖，建议浏览器打印 PDF）
- MCP Server 未真正启动（仅提供 manifest JSON 端点）
- Hermes / OpenClaw 仍是 `NotImplementedError` 占位
- 多用户隔离与权限仍是预留
- 全量 pytest 有 3 个 pre-existing failures（与 Agent 功能无关）
- RealRuntime streaming 依赖 OpenAI stream API，若 LLM 不支持 streaming 则 fallback 到 chunked output
