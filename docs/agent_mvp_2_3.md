# Alpha Radar Agent MVP 2.3 — 运行健康、用户隔离与导出增强版

## 1. MVP 2.3 概述

### MVP 2.2 → 2.3 变更清单

| 变更 | 说明 |
|------|------|
| 新增 Runtime Health API | `GET /api/agent/runtime/health` 暴露当前运行时后端选择（LLM / Hermes / Mock），不泄露密钥 |
| 新增 Follow-up LLM 生产配置 | `OPENAI_API_KEY` 配置后 Follow-up 使用 LLM 生成回答，失败回退确定性模板 |
| 新增 Chart-level 导出增强 | `GET /api/agent/runs/{run_id}/export/print` — 基于 `markdown-it-py` 的打印优化 HTML，支持表格/代码块/图表占位符 |
| 新增 MCP Server 工具执行硬化 | `read_only` 策略拒绝非只读工具，自动 DB session 注入，JSON-RPC 2.0 错误码规范化 |
| 新增用户隔离 | `X-Alpha-User-Id` 请求头标识用户，Run/Skill 数据隔离，无认证系统 |
| 新增运行历史列表 | `GET /api/agent/runs` 分页列出当前用户可见的运行，支持 status 过滤 |
| 修复存量测试 | 3 个 pre-existing test failures 未修复（与 Agent 功能无关） |

### 架构图（更新）

```
用户请求 → X-Alpha-User-Id 隔离层
         → Router (task type 识别)
         → Orchestrator (工具调用 + 上下文收集)
         → Runtime Adapter (Provider 选择: LLN > Hermes > Mock)
         → AgentEventBus (asyncio.Queue 实时推送 + agent_events 持久化)
         → Guardrails (合规替换 + 免责声明)
         → Artifact (产物持久化 + 证据链)
         → Export (Markdown / HTML / Print HTML / 浏览器 PDF)
```

## 2. API 列表

### 已有 API（MVP 2.0/2.1/2.2，未修改）

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| POST | `/api/agent/runs` | 202 | 创建投研任务（异步） |
| GET | `/api/agent/runs/{run_id}` | 200 | 查询任务状态和最新产物 |
| GET | `/api/agent/runs/{run_id}/steps` | 200 | 获取执行步骤 |
| GET | `/api/agent/runs/{run_id}/artifacts` | 200 | 获取产物列表 |
| GET | `/api/agent/runs/{run_id}/events` | 200 | SSE 事件流（EventBus 实时推送 + 增量回放） |
| POST | `/api/agent/runs/{run_id}/followups` | 201 | 多轮追问 |
| GET | `/api/agent/runs/{run_id}/messages` | 200 | 追问历史 |
| GET | `/api/agent/runs/{run_id}/export/markdown` | 200 | 下载 Markdown 报告（Content-Disposition） |
| GET | `/api/agent/runs/{run_id}/export/html` | 200 | 下载安全 HTML 报告（无脚本） |
| GET | `/api/agent/tools` | 200 | 工具清单 ToolSpec[] |
| GET | `/api/agent/tools/mcp-manifest` | 200 | MCP-ready JSON manifest |
| POST | `/api/agent/skills` | 200 | 保存 Skill |
| GET | `/api/agent/skills` | 200 | 列出 Skills（含系统 + 自定义） |
| GET | `/api/agent/skills/{skill_id}` | 200 | 获取单个 Skill |
| POST | `/mcp/` | 200 | MCP JSON-RPC 2.0 HTTP 端点 |

### 新增 API（MVP 2.3）

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/agent/runtime/health` | 200 | 运行时健康检查（返回 provider、各组件状态、警告） |
| GET | `/api/agent/runs` | 200 | 运行历史列表（按 user_id 过滤，支持 status 查询，limit 1-100） |
| GET | `/api/agent/runs/{run_id}/export/print` | 200 | 打印优化 HTML（基于 markdown-it-py，Ctrl+P 另存 PDF） |

## 3. Runtime 配置说明

### Provider 选择链

`AgentOrchestrator` 启动时按以下优先级选择 Runtime Adapter：

```
LLM (RealRuntimeAdapter) → Hermes (HermesRuntimeAdapter) → Mock (MockRuntimeAdapter)
```

判断逻辑（`AgentOrchestrator.__init__`）：

```python
if settings.openai_api_key:
    self.runtime_adapter = RealRuntimeAdapter()
else:
    self.runtime_adapter = MockRuntimeAdapter()
```

### 环境变量

| 变量 | 用途 |
|------|------|
| `OPENAI_API_KEY` | 启用 LLM 运行时（RealRuntimeAdapter + Follow-up LLM） |
| `HERMES_ENDPOINT` | 配置 Hermes 侧车端点（当前仅占位，`HermesRuntimeAdapter` 在无 endpoint 时委托给 RealRuntimeAdapter） |

### Fallback 行为

- **RealRuntimeAdapter**: LLM 调用失败时自动回退到 `MockRuntimeAdapter`，并在 `warnings` 中添加错误信息
- **Follow-up**: LLM 生成失败或无 API key 时回退确定性模板，包含 fallback 提示
- **Streaming**: `stream_run()` 失败时按段落模拟 token delta 输出

### Health Check 用法

`GET /api/agent/runtime/health` 返回：

```json
{
  "runtime_provider": "llm | hermes | mock",
  "llm_configured": true | false,
  "hermes_configured": true | false,
  "streaming_supported": true | false,
  "followup_llm_enabled": true | false,
  "fallback_enabled": true,
  "warnings": ["..."],
  "secrets": null // 有意不含 key 值
}
```

- 不泄露 `openai_api_key` 或 `hermes_endpoint` 的值
- 仅返回配置状态（bool），用于前端显示运行时模式

## 4. MCP Server 说明

Alpha Radar Agent 实现了一个轻量级 MCP（Model Context Protocol）Server，兼容 JSON-RPC 2.0，**不依赖外部 MCP SDK**。

### 传输方式

#### HTTP 模式（FastAPI Router）

端点：`POST /mcp/`

注册于 `app.main`：

```python
app.include_router(mcp_router)  # 路径前缀 /mcp
```

请求示例：

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_stock_basic", "arguments": {"symbol_or_name": "000001"}}}
```

#### stdio 模式（CLI）

```bash
cd backend
python scripts/run_mcp_server.py
# 逐行读取 stdin JSON-RPC 请求，写入 stdout
```

### 支持的 Method

| Method | 说明 |
|--------|------|
| `tools/list` | 返回 19 个工具的 name + description + inputSchema |
| `tools/call` | 按名称执行工具，返回结果 |
| `initialize` | 返回协议版本、server info、capabilities |

### Session 处理

- **DB 工具**: 自动检测函数签名，第一个参数名为 `session` 的工具调用时自动注入 `SessionLocal()` 实例
- **非 DB 工具**: 直接调用（如 `generate_report_outline`, `format_research_report`）
- session_factory 可注入，默认为 `SessionLocal`

### read_only 策略

`_call_tool` 中强制检查 `spec.read_only`：

```python
if not spec.read_only:
    return error(-32603, "Tool X is not read-only — execution rejected")
```

所有 19 个注册工具均为只读。

### JSON-RPC 2.0 错误码

| 错误码 | 含义 |
|--------|------|
| -32700 | Parse error（JSON 解析失败） |
| -32600 | Invalid Request（非 dict 请求体） |
| -32601 | Method not found（非 `tools/list`/`tools/call`/`initialize`） |
| -32602 | Invalid params（缺少 name / 未知工具） |
| -32603 | Internal error（工具执行失败 / 非只读工具被调用） |

## 5. 用户隔离说明

### 身份标识

- 前端通过 `X-Alpha-User-Id` 请求头传递用户标识
- 无头时默认值: `"anonymous"`
- 非认证系统，无 JWT、无登录、无权限等级

### 实现方式

`api.py` 中的依赖注入：

```python
def get_current_user_id(x_alpha_user_id: str | None = Header(default=None)) -> str:
    return x_alpha_user_id or "anonymous"
```

### 隔离策略

| 场景 | 行为 |
|------|------|
| Run 列表 (`GET /runs`) | 返回 `user_id == 当前用户 OR user_id IS NULL` 的记录 |
| Run 详情 (`GET /runs/{id}`) | 访问他人 run → 404（不暴露存在性） |
| Run 创建 | `AgentRunRequest.user_id` 字段可设置，通常在 `AgentOrchestrator.create_run_record` 中赋值 |
| Skill 查询 | `GET /skills` 返回全部（含系统 + 自定义） |
| 系统 Skill | `is_system=True` 对所有用户可见 |
| 遗留数据 | `user_id = null` 的记录对全部用户可见 |

### 非安全系统

- 不验证身份真实性
- 前端可设置任意 `X-Alpha-User-Id`
- 仅为基本数据隔离，非访问控制

## 6. 导出说明

### Markdown 下载

`GET /api/agent/runs/{run_id}/export/markdown`

- 类型: `text/markdown`
- 内容: `# 标题` + `content_md` + 免责声明
- 文件名: `alpha-radar-report-{run_id}.md`
- 内容已在 artifact 中经过 guardrails 清洗，不再重复清洗

### HTML 安全导出（MVP 2.2）

`GET /api/agent/runs/{run_id}/export/html`

- 类型: `text/html`
- 无 `<script>` 标签，无事件处理器（安全）
- 手写 HTML 转换，支持 h1/h2/h3、ul/li、hr、p
- `:::chart` 标签替换为 `<div class="chart-placeholder">`
- 包含 `@media print` 样式

### Print HTML（MVP 2.3 新增）

`GET /api/agent/runs/{run_id}/export/print`

- 基于 `markdown-it-py` 渲染（支持表格、代码块、引用等完整 Markdown 语法）
- `:::chart` 标签替换为内容丰富的占位符（含图表名称、标的、数据描述）
- 完整的打印优化 CSS（A4 页面尺寸、字体、颜色保持）
- 包含报告标题、生成时间、摘要、参考来源表格、免责声明
- 无脚本 HTML，完全自包含
- 浏览器中打开 → Ctrl+P / Cmd+P → 另存为 PDF

### Chart 占位符处理

`export_utils.py` 中 `_replace_chart_tags()` 支持的图表类型：

| 类型 | 占位符内容 |
|------|-----------|
| `candle` | K线图（含标的名 + 代码） |
| `industry_heat` | 行业热度图（含周期） |
| `industry_sankey` | 产业链桑基图 |
| `trend_pool` | 趋势股票池 |
| `tenbagger` | 十倍股评估 |
| `market_brief` | 市场简报 |

每个占位符包含：图标、标题、描述文案、元数据表格（标的代码、数据来源等）。

### 后端 PDF

**未实现**。项目无 PDF 生成依赖。使用浏览器原生打印功能（Ctrl+P → 另存为 PDF）替代，打印质量更高且零维护。

## 7. Guardrails 规则（不变）

### 禁用词替换（13 条）

| 原词 | 替换为 |
|------|--------|
| 买入 | 纳入观察池 |
| 卖出 | 移出观察并复核风险 |
| 满仓 | 提高关注度但控制风险暴露 |
| 梭哈 | 避免单一方向过度暴露 |
| 稳赚 | 存在不确定性 |
| 必涨 | 仍需进一步确认 |
| 无风险 | 风险尚未充分暴露 |
| 抄底 | 等待趋势确认 |
| 逃顶 | 观察风险释放情况 |
| 重仓 | 控制仓位风险 |
| 加杠杆 | 谨慎评估风险暴露 |
| 翻倍确定性 | 具备一定增长潜力但需验证 |
| 保证收益 | 收益预期需独立评估 |

### 正则替换（3 条）

| 模式 | 替换为 |
|------|--------|
| `建议加仓` | `建议跟踪观察` |
| `建议减仓` | `建议复核风险暴露` |
| `目标价[:：]?数字` | `估值情景需独立复核` |

### 免责声明

```
本报告仅用于投研分析和信息整理，不构成任何投资建议。市场有风险，决策需独立判断。
```

## 8. 本地运行命令

### 后端启动

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 前端启动

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/frontend
npm run dev
```

### Runtime Health 检查

```bash
curl http://localhost:8000/api/agent/runtime/health
```

### 创建投研任务

```bash
curl -X POST http://localhost:8000/api/agent/runs \
  -H "Content-Type: application/json" \
  -H "X-Alpha-User-Id: test-user" \
  -d '{"user_prompt": "帮我分析中际旭创"}'
```

### 查询运行列表

```bash
curl http://localhost:8000/api/agent/runs \
  -H "X-Alpha-User-Id: test-user"
```

### SSE 事件流

```bash
curl -N http://localhost:8000/api/agent/runs/1/events
```

### 追问

```bash
curl -X POST http://localhost:8000/api/agent/runs/1/followups \
  -H "Content-Type: application/json" \
  -d '{"message": "解释一下风险", "mode": "explain"}'
```

### 导出

```bash
# Markdown
curl http://localhost:8000/api/agent/runs/1/export/markdown

# HTML（安全）
curl http://localhost:8000/api/agent/runs/1/export/html

# Print HTML
curl http://localhost:8000/api/agent/runs/1/export/print
```

### MCP tools/list

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### MCP tools/call

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_latest_daily_report","arguments":{}}}'
```

### MCP stdio 模式

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | .venv/bin/python scripts/run_mcp_server.py
```

## 9. 已知限制

- **后端 PDF 生成未实现** — 项目无 PDF 依赖，浏览器 Ctrl+P 打印 PDF 更优且零维护
- **用户隔离是基于请求头的** — `X-Alpha-User-Id` 可被客户端随意设置，非真实认证系统
- **OpenClaw 未连接** — `OpenClawRuntimeAdapter` 仍是 `NotImplementedError` 占位
- **Hermes 取决于 endpoint 配置** — 无 `HERMES_ENDPOINT` 时 HermesAdapter 委托给 RealRuntimeAdapter
- **MCP Server 仅支持 Read-Only 工具** — read_only 策略拒绝执行非只读工具
- **3 个 pre-existing test failures** — 与 Agent 功能无关的存量测试失败（未修复）
- **无实时的 WebSocket** — SSE 事件流使用 HTTP 长连接 + EventBus，非 WebSocket

## 10. 测试命令

### Agent 核心测试

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
.venv/bin/python -m pytest app/tests/test_agent.py -q
.venv/bin/python -m pytest app/tests/test_agent_runtime.py -q
.venv/bin/python -m pytest app/tests/test_agent_events.py -q
.venv/bin/python -m pytest app/tests/test_agent_export.py -q
```

### 端到端评估

```bash
.venv/bin/python scripts/run_agent_eval.py
```

### 全量测试

```bash
.venv/bin/python -m pytest -q
```

### 前端检查

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/frontend
npx tsc --noEmit
npm run lint
npm run build
```

## 5 类投研场景（不变）

| Task Type | 触发关键词 | 工作流 |
|-----------|-----------|--------|
| `stock_deep_research` | 股票名称/代码 | 基础信息 → 趋势 → 行业映射 → 评分 → 证据链 |
| `industry_chain_radar` | 产业链、行业、节点 | 行业映射 → 产业链节点 → 热力图 → 关联股票 |
| `trend_pool_scan` | 筛选、股票池、动量 | 动量排名 → 评分排行 → 覆盖状态 |
| `tenbagger_candidate` | 十倍股、早期特征 | 评分排行 → 动量排名 → 覆盖状态 |
| `daily_market_brief` | 日报、简报、复盘 | 最新日报 → 行业热度 → 动量排名 |

## SSE 事件类型（不变）

| 事件 | 说明 |
|------|------|
| `run_created` | 任务创建（回放首个事件） |
| `run_started` / `run_completed` / `run_failed` | 生命周期 |
| `step_started` / `step_completed` | 步骤开始/完成 |
| `tool_call_started` / `tool_call_completed` | 工具调用（含 latency_ms） |
| `token_delta` | 运行时 token 增量 |
| `artifact_created` | 新产物 |
| `followup_started` / `followup_token_delta` / `followup_completed` | 追问生命周期 |
| `heartbeat` | 每 10 秒（SSE 保活） |
| `error` | run 不存在 |

## 19 个工具（不变）

| 类别 | 工具 |
|------|------|
| Market (4) | `get_stock_basic`, `get_price_trend`, `get_momentum_rank`, `get_market_coverage_status` |
| Industry (4) | `get_industry_mapping`, `get_industry_chain`, `get_related_stocks_by_industry`, `get_industry_heatmap` |
| Scoring (4) | `get_stock_score`, `get_score_breakdown`, `get_top_scored_stocks`, `get_risk_flags` |
| Evidence (4) | `get_stock_evidence`, `get_industry_evidence`, `get_recent_catalysts`, `get_evidence_summary` |
| Report (3) | `get_latest_daily_report`, `generate_report_outline`, `format_research_report` |
