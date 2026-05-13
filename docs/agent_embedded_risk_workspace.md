# Alpha Radar MVP 3.3: Agent 嵌入式风险工作台

## 1. 模块定位

Agent 嵌入式风险工作台是将 /risk 独立工具页面的核心能力内嵌到 /agent 主工作流入口中，形成"对话分析 + 风险测算 + 仓位计划"的闭环体验。

### 页面职责对比

| 维度 | /agent（主工作流入口） | /risk（独立工具页面） |
|------|----------------------|---------------------|
| 定位 | Agent 对话 + Risk Workspace 面板 + 报告内 RiskCard | 独立完整的仓位计算器 + 组合暴露面板 |
| 用户场景 | 先分析后测算：输入投研问题，Agent 分析后联动风险预算 | 直接测算：独立打开工具页，输入参数计算仓位 |
| 交互方式 | 自然语言 + 面板切换 + 报告内交互卡片 | 表单填写 + 侧边栏面板 |
| 核心组件 | AgentChat + CollapsibleRiskWorkspace + RiskCard | CalculatorForm + ExposurePanel + DrawdownStatus |
| 数据流 | 问题 → 工具调用 → RiskCard → 保存计划 → Workspace 展示 | 表单输入 → API 调用 → 结果展示 |
| 保留状态 | 每次 Agent Run 独立，不跨 session | 组合选择器跨 page view 持久化 |

### 架构示意

```
/agent                     /risk
├── AgentChat              ├── PositionCalculator (完整表单)
│   ├── Command Box        ├── PortfolioSelector
│   ├── Report Viewer      ├── ExposurePanel (行业/主题)
│   └── FollowUp           ├── PositionPlansTable
├── RiskWorkspace (折叠)    └── DrawdownStatus
│   ├── PortfolioSnapshot
│   ├── Holdings
│   ├── ExposureSummary
│   ├── QuickPositionCalc
│   ├── RiskRules
│   └── PositionPlans
└── Report 内 RiskCard
```

**核心原则**：/agent 的 Risk Workspace 是 /risk 页面的功能子集，仅展示与当前对话上下文最相关的风险数据。完整的功能操作仍引导用户前往 /risk。

---

## 2. Agent Risk Workflow

Agent 在工作流中自动识别涉及风险预算的任务，执行以下流程：

```
自然语言问题
    │
    ▼
Agent Orchestrator 识别 task_type
    │  (auto / stock_deep_research / risk_budget / ...)
    ▼
调用 risk_tools 收集上下文
    │  calculate_position_size()
    │  check_portfolio_exposure()
    │  get_risk_rules()
    │  get_position_plans()
    │  explain_risk_budget()
    ▼
报告内嵌入 RiskCard
    │  Agent 产物中自动追加风险预算卡片
    ▼
用户操作
    ├── 存入 thesis（关联投研观点）
    ├── 存入 watchlist（加入观察池）
    └── 保存 position plan（draft 状态）
    ▼
Risk Workspace 面板实时展示
    │  用户可折叠展开，查看所有计划/暴露/规则
    ▼
用户独立决策是否执行
```

### 触发条件

Agent 在以下场景自动触发 risk workflow：

| 触发条件 | 行为 |
|---------|------|
| 用户问题包含"风险"、"仓位"、"预算"、"止损"等关键词 | Orchestrator 将 task_type 识别为 risk_budget |
| 报告中的 thesis 包含 entry_price + invalidation_price | 自动调用 `calculate_position_size()` 生成 RiskCard |
| 用户在 FollowUp 中选择"展开风险"模式 | 调用 `check_portfolio_exposure()` 和 `explain_risk_budget()` |

### RiskCard

RiskCard 是 Agent 报告产物中的一个结构化区块，格式示例：

```json
{
  "type": "risk_card",
  "symbol": "000858",
  "entry_price": 150.00,
  "invalidation_price": 135.00,
  "risk_per_share": 15.00,
  "max_loss_amount": 10000.00,
  "calculated_quantity": 600,
  "estimated_position_pct": 9.0,
  "effective_risk_pct": 1.0,
  "warnings": [],
  "disclaimer": "本模块仅用于风险预算测算..."
}
```

RiskCard 不包含"建议买入"类文字，所有输出经过 `sanitize_risk_output()` 合规过滤。

---

## 3. Risk Workspace 面板

### 面板结构

Risk Workspace 是 /agent 页面右侧追加的可折叠面板，包含以下模块：

#### 3.1 Portfolio Snapshot（组合快照）

展示当前默认组合的核心指标：

| 指标 | 数据来源 |
|------|---------|
| 账户总权益 | `risk_portfolios.total_equity` |
| 可用现金 | `risk_portfolios.cash` |
| 当前回撤 | `risk_portfolios.current_drawdown_pct` |
| 回撤乘数 | `GET /api/risk/drawdown-status` |
| 熔断等级 | `GET /api/risk/drawdown-status` |

#### 3.2 Holdings（持仓列表）

展示组合内所有持仓，数据来源 `risk_positions` 表：

| 字段 | 说明 |
|------|------|
| symbol | 标的代码 |
| name | 标的名 |
| quantity | 持仓数量 |
| avg_cost | 平均成本 |
| last_price | 最新价 |
| market_value | 持仓市值 |
| position_pct | 仓位占比 |
| industry | 行业（自动从 Stock 表同步） |
| theme_tags | 主题标签（自动从 Stock.concepts 同步） |

#### 3.3 Exposure Summary（暴露概览）

通过 `GET /api/risk/exposure` 获取，以简表形式展示：

- 单票暴露：当前仓位占比最高的前 5 只标的
- 行业暴露：行业分布，标记超出 `max_industry_exposure_pct` 的行
- 主题暴露：主题分布，标记超出 `max_theme_exposure_pct` 的行

超出限额的行标红色"超限"标签，点击跳转至 /risk 页面调整规则。

#### 3.4 Quick Position Calculator（快速仓位测算）

简化版仓位计算表单（对比 /risk 页面的完整表单）：

| 字段 | 必填 | 默认值 |
|------|------|--------|
| 标的代码 | 是 | 从当前对话上下文自动填充 |
| 入场参考价 | 是 | 从当前对话上下文自动填充 |
| 无效点价格 | 是 | 从当前对话上下文自动填充 |
| 单笔风险比例 | 否 | 1.0% |

调用 `POST /api/risk/position-size`，结果在面板内直接展示，不跳转。

#### 3.5 Risk Rules（风险规则）

当前组合生效的规则列表：

| 规则 | 说明 |
|------|------|
| max_risk_per_trade_pct | 单笔风险比例 |
| max_single_position_pct | 单票上限 |
| max_industry_exposure_pct | 行业暴露上限 |
| max_theme_exposure_pct | 主题暴露上限 |
| drawdown_rules_json | 回撤熔断规则 |

只读展示，修改需前往 /risk 页面。

#### 3.6 Position Plans（仓位计划）

展示 `status IN (draft, active)` 的仓位计划列表，支持：

- 按状态筛选（全部 / 草稿 / 生效）
- 查看计划详情（入场价、无效点、仓位比例、约束条件）
- draft → active 确认操作
- active → archived 归档操作
- 关联 thesis 和 watchlist 的快捷跳转

---

## 4. Runtime Health

/agent 页面通过 `GET /api/agent/runtime/health` 获取运行时状态，在页头以 `RuntimeHealthBadge` 组件展示。

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| runtime_provider | string | 当前活跃运行时: llm / hermes / mock |
| llm_configured | bool | 已配置 OpenAI API Key (`settings.openai_api_key`) |
| hermes_configured | bool | 已配置 Hermes Endpoint (`settings.hermes_endpoint`) |
| streaming_supported | bool | 是否支持流式输出（仅 llm 时支持） |
| followup_llm_enabled | bool | 追问是否使用 LLM（等于 llm_configured） |
| fallback_enabled | bool | 是否启用模板回退 |
| vision_configured | bool | 是否已配置多模态模型 |
| vision_provider | string / null | 多模态模型提供商: openai / hermes / null |
| supports_image_input | bool | 是否支持图片输入 |
| image_input_max_mb | float / null | 图片输入大小上限（MB） |
| warnings | string[] | 运行时状态警告 |

### LLM 配置判断

```python
llm_configured = bool(settings.openai_api_key)
```

当 `settings.openai_api_key` 非空字符串时判定为已配置。此时：

- 运行时使用 `RealRuntimeAdapter`
- 支持流式输出（`streaming_supported = True`）
- 追问使用 LLM 生成（`followup_llm_enabled = True`）
- Vision 能力可用（`vision_configured = True`）

### Vision 配置判断

```python
vision_configured = bool(settings.openai_api_key)  # gpt-4o 支持多模态
```

Vision 依赖 OpenAI gpt-4o 的多模态能力。未配置时：

- `vision_configured = False`
- `supports_image_input = False`
- `VisionPortfolioExtractor.available = False`
- warnings 追加："当前未配置多模态图片识别模型，截图解析不可用。"

### 为什么没有 Vision 配置时不能识别截图

Alpha Radar 不使用传统 OCR（如 Tesseract、PaddleOCR）。截图解析完全依赖 LLM Vision Adapter：

1. **架构设计**：不走 OCR → 规则解析管线，而是直接将图片送入多模态 LLM
2. **安全性**：不上传交易截图到不可信服务，仅通过配置的 LLM 端点处理
3. **准确性**：多模态 LLM 对结构化持仓信息的理解能力远超传统 OCR 模板匹配
4. **前提条件**：需要配置支持 Vision 的 LLM Provider（目前需要 `openai_api_key`，使用 gpt-4o）

---

## 5. Vision Import（预留）

### 定位

Vision Import 不是传统 OCR 方案，而是通过 LLM Vision Adapter 从交易平台截图提取持仓信息，作为组合数据的导入方式之一。

### 架构

```
用户上传截图
    │
    ▼
GET /api/agent/vision/extract-portfolio (预留)
    │
    ▼
LLM Vision Adapter (VisionPortfolioExtractor)
    │  不调用 Tesseract / PaddleOCR
    │  直接发送图片到多模态 LLM
    ▼
解析结果
    ├── broker_name: 券商/平台名称
    ├── account_equity: 账户总权益
    ├── cash: 可用现金
    ├── positions[]: 持仓列表
    │   ├── symbol: 标的代码
    │   ├── name: 标的名
    │   ├── quantity: 数量
    │   ├── market_value: 市值
    │   ├── cost: 成本
    │   └── weight_pct: 权重
    └── warnings: 解析警告
    ▼
用户确认界面
    │  NEEDS_USER_CONFIRMATION = True
    │  用户手动核对、修正解析结果
    ▼
确认无误后写入 risk_portfolios / risk_positions
```

### 安全约束

| 约束 | 说明 |
|------|------|
| 不上传不可信服务 | 截图仅通过已配置的 LLM Provider 处理 |
| 不存储截图 | 处理完成后立即丢弃，不落盘 |
| 不自动导入 | 解析结果必须用户确认后才会写入数据库 |
| 不写入日志 | 禁止将图片内容输出到日志文件 |

### MVP 3.3 状态

当前 MVP 3.3 仅预留接口和数据模型：

- `backend/app/agent/vision/__init__.py` — 模块初始化
- `backend/app/agent/vision/adapter.py` — `VisionPortfolioExtractor` 桩类
- `backend/app/agent/vision/schemas.py` — `ExtractedPosition`、`PortfolioImageExtractResponse` 模型
- `GET /api/agent/vision/extract-portfolio` — **路由未注册**，等待 Vision 模型配置后注册

完整实现需等待 Vision 模型配置完成后开发。

---

## 6. 合规边界

Agent 嵌入式风险工作台继承 Alpha Radar 全部合规约束。

### 系统定位

Alpha Radar 是投研辅助系统，不是投资顾问。风险预算模块定位为"风险预算测算和仓位计划记录系统"，不输出买卖建议。

### 禁止输出

- 建议买入 / 建议卖出
- 目标价
- 明日上涨 / 稳赚
- 必成十倍股 / 保证收益
- 仓位推荐（替换为"风险预算上限"）

### 行为边界

| 行为 | 允许 | 说明 |
|------|------|------|
| 风险预算测算 | 是 | 核心功能 |
| 仓位计划记录 | 是 | 用户独立决策的记录工具 |
| 组合暴露分析 | 是 | 展示客观数据 |
| 合规护栏 | 是 | 14 条禁用词替换 + 强制免责声明 |
| 交易建议 | 否 | 边界红线 |
| 接入券商 | 否 | 不接券商交易接口 |
| 自动下单 | 否 | 不下单、不执行交易 |
| 截图导入仓位 | 有条件 | 需用户确认，MVP 3.3 仅预留 |

### 免责声明

所有风险相关输出自动追加：

```
本模块仅用于风险预算测算和仓位计划记录，不构成任何投资建议、
买卖建议或收益承诺。市场有风险，决策需独立判断。
```

---

## 7. API 说明

### runtime/health 新增字段

`GET /api/agent/runtime/health` 在 MVP 3.3 中新增以下字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| vision_configured | bool | false | 是否已配置多模态模型 |
| vision_provider | string / null | null | 提供商: openai / hermes / null |
| supports_image_input | bool | false | 是否支持图片输入 |
| image_input_max_mb | float / null | null | 图片大小上限（MB，gpt-4o = 20.0） |

### /api/agent/vision/extract-portfolio（预留）

**路由未注册**，待 Vision 模型配置完成后注册。

预期接口定义：

| 项目 | 说明 |
|------|------|
| 方法 | POST |
| 路径 | `/api/agent/vision/extract-portfolio` |
| Content-Type | `multipart/form-data` |
| 请求字段 | `image` (file, required), `broker_hint` (string, optional) |
| 响应模型 | `PortfolioImageExtractResponse` |
| 安全 | 需要 vision_configured = true，否则返回 vision_unavailable |

### 已有 /api/risk/* 接口继续可用

Agent Risk Workspace 面板复用以下已有接口：

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/risk/portfolios` | 组合列表（面板组合选择器） |
| GET | `/api/risk/portfolios/{id}` | 组合详情（快照数据） |
| GET | `/api/risk/exposure` | 暴露概览 |
| GET | `/api/risk/rules` | 风险规则 |
| GET | `/api/risk/drawdown-status` | 回撤熔断状态 |
| POST | `/api/risk/position-size` | 快速仓位测算 |
| GET | `/api/risk/events` | 风险事件列表 |

不新增专门为 /agent 定制的独立端点，复用 /risk 模块已有接口。

---

## 8. 本地验收命令

### 环境准备

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate
```

### 后端测试

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend

# 风险模块全部测试
.venv/bin/python -m pytest app/tests/test_risk*.py -q -v

# Agent 模块测试
.venv/bin/python -m pytest app/tests/test_agent*.py -q -v

# 全量后端测试
.venv/bin/python -m pytest -q
```

### 前端构建检查

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/frontend

# TypeScript 类型检查
npx tsc --noEmit

# ESLint 检查
npm run lint

# 生产构建
npm run build
```

### 运行时健康检查

```bash
# 启动后端后验证 runtime health 端点
curl -s "http://localhost:8000/api/agent/runtime/health" | python -m json.tool

# 预期输出示例（Vision 字段）
# {
#   "runtime_provider": "mock",
#   "llm_configured": false,
#   "hermes_configured": false,
#   "streaming_supported": false,
#   "followup_llm_enabled": false,
#   "fallback_enabled": true,
#   "vision_configured": false,
#   "vision_provider": null,
#   "supports_image_input": false,
#   "image_input_max_mb": null,
#   "warnings": [
#     "No LLM or Hermes configured. Using deterministic mock runtime.",
#     "当前未配置多模态图片识别模型，截图解析不可用。"
#   ]
# }
```

---

## 9. 核心文件路径汇总

### 后端

| 文件 | 说明 |
|------|------|
| `backend/app/agent/api.py` | Agent API 路由，含 `GET /runtime/health`（vision 字段） |
| `backend/app/agent/schemas.py` | `AgentRuntimeHealth` Pydantic 模型（vision 字段定义） |
| `backend/app/agent/tools/risk_tools.py` | Agent 风险工具集（`calculate_position_size`、`check_portfolio_exposure`、`get_risk_rules`、`get_position_plans`、`explain_risk_budget`） |
| `backend/app/agent/vision/__init__.py` | Vision 模块初始化 |
| `backend/app/agent/vision/adapter.py` | `VisionPortfolioExtractor` 桩类 |
| `backend/app/agent/vision/schemas.py` | `ExtractedPosition`、`PortfolioImageExtractResponse` 数据模型 |
| `backend/app/risk/portfolio_api.py` | `/api/risk/*` 路由（复用） |
| `backend/app/risk/calculators.py` | 仓位大小计算引擎 |
| `backend/app/risk/exposure.py` | 组合暴露计算 |
| `backend/app/risk/drawdown.py` | 回撤熔断引擎 |
| `backend/app/risk/guardrails.py` | 合规护栏 + `sanitize_risk_output()` |
| `backend/app/db/models.py` | 6 个风险数据模型 |
| `backend/app/config.py` | 环境配置（`openai_api_key`、`hermes_endpoint`） |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/app/agent/page.tsx` | /agent 页面（含 RuntimeHealthBadge 组件） |
| `frontend/src/app/risk/page.tsx` | /risk 独立工具页面 |
| `frontend/src/lib/api.ts` | API 客户端（`RuntimeHealth` 类型定义） |

---

## 10. 变更日志

### MVP 3.3（当前版本）

- **Agent Risk Workflow**: Agent 自动识别风险预算任务，调用 risk_tools，在报告内嵌入 RiskCard
- **Risk Workspace 面板**: /agent 页面追加可折叠面板，包含组合快照、持仓列表、暴露概览、快速测算、风险规则、仓位计划 6 个子模块
- **Runtime Health 扩展**: `GET /api/agent/runtime/health` 新增 `vision_configured`、`vision_provider`、`supports_image_input`、`image_input_max_mb` 四个字段
- **Vision Import 预留**: 创建 `backend/app/agent/vision/` 包，包含桩类和 Pydantic 模型，路由未注册
- **合规继承**: 复用 /risk 模块的全部护栏规则和免责声明

### MVP 3.2

- 风险预算模块: `backend/app/risk/` 包，6 个数据模型，11 个 REST 端点
- 仓位大小计算引擎、回撤熔断系统、组合暴露分析、个股风险扣分引擎
- 合规护栏: 14 条禁用词替换 + 强制免责声明

### MVP 3.1

- Research Thesis 闭环
- 观察池扩展
- 报告质量评分
- Alternative signals
