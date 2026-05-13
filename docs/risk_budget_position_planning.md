# Alpha Radar MVP 3.2: 风险预算 / 仓位计划模块

## 1. 模块定位

风险预算 / 仓位计划模块，不是交易建议系统。将主观判断和投研 thesis 转换为可验证的风险预算计划。

### 核心原则

| 维度 | 传统交易系统 | Alpha Radar 风险预算模块 |
|------|-------------|------------------------|
| 输出 | 买卖信号、目标价、仓位推荐 | 风险预算上限、约束清单、压力情景 |
| 输入 | 技术指标、信号 | 用户主观判断：入场价、无效点、置信度 |
| 验证机制 | 回测 | 后验复盘：实际 vs 预算对比 |
| 用户动作 | 跟随信号执行 | 独立决策是否在预算上限内执行 |
| 合规 | 持牌要求 | 禁用词替换 + 强制免责声明 |

本模块仅解决一个问题：**给定主观判断（入场价、无效点、风险比例），在多种硬约束下计算出客观的风险预算上限**。不评价 theses 质量，不推荐买卖。

---

## 2. 核心公式

### 计算链

```
单笔风险金额 = 账户权益 × 单笔风险比例 × 回撤调整系数
单股风险 = 入场参考价 - 无效点价格
最大股数 = 单笔风险金额 / 单股风险
名义仓位 = 最大股数 × 入场参考价
名义仓位比例 = 名义仓位 / 账户权益
最终仓位上限 = min(风险预算仓位, 单票上限, 可用现金, 回撤调整后总仓位上限, 主题暴露剩余额度)
```

### 约束优先级（由松到紧）

1. **风险预算约束**：`单笔风险金额 / 单股风险` 计算出的理论数量
2. **最小交易单位对齐**：向下取整至最近的手数（A 股 100 股，港股/美股 1 股）
3. **单票百分比上限**：`账户权益 × max_single_position_pct`
4. **可用现金约束**：名义仓位不能超过 `available_cash`
5. **回撤熔断约束**：通过 `drawdown_multiplier` 缩放风险预算
6. **主题暴露剩余额度**：假设仓位加入后不超过 `max_theme_exposure_pct`

### 实现路径

路径: `backend/app/risk/calculators.py` 第17行 `calculate_position_size()`

---

## 3. 核心闭环

```
Thesis → invalidation condition → risk budget → position plan → exposure check → review
```

### 闭环说明

| 步骤 | 说明 | 关联模块 |
|------|------|---------|
| **Thesis** | 投研观点，包含 direction / confidence / invalidation_conditions | `research_thesis` |
| **Invalidation condition** | 从 thesis 的 invalidation_conditions_json 提取无效点/止损价 | 用户/Agent 输入 |
| **Risk budget** | `calculate_position_size()` 计算风险预算上限 | `risk/calculators.py` |
| **Position plan** | 写入 `position_plans` 表，保存计算快照 | `PositionPlan` 模型 |
| **Exposure check** | 检查加入后是否触发行业/主题/单票集中度违规 | `risk/exposure.py` |
| **Review** | 按计划复盘：实际价格 vs 入场价，计算 realized_risk_pct | `PositionPlanReview` |

### 状态流转

```
position_plan.status:
  draft ──→ active ──→ completed
     │                    │
     └──→ archived        └──→ archived
```

- `draft`: 测算草稿，未生效
- `active`: 已确认执行，纳入组合敞口计算
- `completed`: 已平仓/到期，标记完成
- `archived`: 归档

---

## 4. 数据模型

路径: `backend/app/db/models.py`

### risk_portfolios

```sql
CREATE TABLE risk_portfolios (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              VARCHAR(64),          -- 用户标识
    name                 VARCHAR(128) DEFAULT '默认组合',
    base_currency        VARCHAR(8) DEFAULT 'CNY',
    total_equity         FLOAT DEFAULT 0.0,    -- 账户总权益
    cash                 FLOAT DEFAULT 0.0,    -- 可用现金
    current_drawdown_pct FLOAT,                -- 当前回撤百分比
    created_at           DATETIME,
    updated_at           DATETIME
);
```

### risk_positions

```sql
CREATE TABLE risk_positions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id      INTEGER REFERENCES risk_portfolios(id),
    symbol            VARCHAR(32),             -- 标的代码
    name              VARCHAR(128),            -- 标的名
    market            VARCHAR(16),             -- 市场: A / HK / US
    quantity          FLOAT DEFAULT 0.0,       -- 持仓数量
    avg_cost          FLOAT,                   -- 平均成本
    last_price        FLOAT,                   -- 最新价
    market_value      FLOAT,                   -- 持仓市值
    position_pct      FLOAT,                   -- 仓位占比(%)
    industry          VARCHAR(64),             -- 行业（自动从 Stock 表同步）
    theme_tags_json   TEXT DEFAULT '[]',        -- 主题标签（自动从 Stock.concepts 同步）
    updated_at        DATETIME
);
```

关键行为: `POST /api/risk/portfolios/{portfolio_id}/positions` 创建/更新仓位时，自动从 `Stock` 表查询 `industry_level1` 和 `concepts` 并填充到 `industry` / `theme_tags_json`。

### risk_rules

```sql
CREATE TABLE risk_rules (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  VARCHAR(64),
    portfolio_id             INTEGER REFERENCES risk_portfolios(id),
    max_risk_per_trade_pct   FLOAT DEFAULT 1.0,     -- 默认单笔风险比例 1%
    max_single_position_pct  FLOAT DEFAULT 20.0,     -- 默认单票上限 20%
    max_industry_exposure_pct FLOAT DEFAULT 40.0,    -- 默认行业暴露上限 40%
    max_theme_exposure_pct   FLOAT DEFAULT 30.0,     -- 默认主题暴露上限 30%
    drawdown_rules_json      TEXT DEFAULT '[...]',   -- 回撤熔断规则 JSON
    created_at               DATETIME,
    updated_at               DATETIME
);
```

创建组合时自动生成一条默认 RiskRule。

### risk_events

```sql
CREATE TABLE risk_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        VARCHAR(64),
    portfolio_id   INTEGER REFERENCES risk_portfolios(id),
    event_type     VARCHAR(32) DEFAULT 'breach',     -- plan_created / plan_reviewed / breach
    severity       VARCHAR(16) DEFAULT 'info',       -- info / warning / critical
    message        TEXT,
    related_symbol VARCHAR(32),
    related_theme  VARCHAR(64),
    payload_json   TEXT,
    created_at     DATETIME
);
```

### position_plans

```sql
CREATE TABLE position_plans (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                  VARCHAR(64),
    portfolio_id             INTEGER REFERENCES risk_portfolios(id),
    thesis_id                INTEGER REFERENCES research_thesis(id),
    watchlist_item_id        INTEGER REFERENCES watchlist_item(id),
    symbol                   VARCHAR(32),
    subject_name             VARCHAR(128),
    subject_type             VARCHAR(16) DEFAULT 'stock',
    entry_price              FLOAT DEFAULT 0.0,
    invalidation_price       FLOAT,               -- 无效点/止损价
    risk_per_share           FLOAT,               -- 每股风险
    risk_per_trade_pct       FLOAT DEFAULT 1.0,   -- 单笔风险比例
    max_loss_amount          FLOAT,               -- 最大亏损预算
    calculated_quantity      INTEGER,             -- 计算股数（对齐手数后）
    calculated_position_value FLOAT,              -- 名义仓位
    calculated_position_pct  FLOAT,               -- 名义仓位比例
    theme_exposure_after_pct  FLOAT,              -- 假设加入后主题暴露
    industry_exposure_after_pct FLOAT,            -- 假设加入后行业暴露
    status                   VARCHAR(16) DEFAULT 'draft',  -- draft / active / completed / archived
    warnings_json            TEXT DEFAULT '[]',
    constraints_json         TEXT DEFAULT '[]',
    calculation_json         TEXT DEFAULT '{}',
    created_at               DATETIME,
    updated_at               DATETIME
);
```

### position_plan_reviews

```sql
CREATE TABLE position_plan_reviews (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    position_plan_id  INTEGER REFERENCES position_plans(id),
    review_date       DATE,
    status            VARCHAR(24) DEFAULT 'pending',  -- pending / hit / missed / invalidated
    actual_price      FLOAT,
    realized_risk_pct FLOAT,                -- 实际亏损/收益占权益百分比
    review_note       TEXT,
    created_at        DATETIME
);
```

---

## 5. API 列表

路由: `backend/app/risk/portfolio_api.py` (prefix: `/api/risk`)

### Portfolio API

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/risk/portfolios` | 200 | 组合列表，支持 user_id 过滤 |
| POST | `/api/risk/portfolios` | 200 | 创建新组合（自动创建默认 RiskRule） |
| GET | `/api/risk/portfolios/{portfolio_id}` | 200 | 组合详情（含持仓列表） |

### Position API

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| POST | `/api/risk/portfolios/{portfolio_id}/positions` | 200 | 新增/更新仓位（自动同步 Stock 行业和主题） |
| DELETE | `/api/risk/portfolios/{portfolio_id}/positions/{symbol}` | 200 | 移除仓位 |

### Rule & Exposure API

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/risk/rules` | 200 | 风险规则列表，支持 portfolio_id / user_id 过滤 |
| POST | `/api/risk/rules` | 200 | 设置/更新风险规则 |
| GET | `/api/risk/exposure` | 200 | 组合暴露报告（个股/行业/主题维度暴露百分比） |
| POST | `/api/risk/portfolio-check` | 200 | 组合规则校验（支持假设仓位的情景测试） |

### Position Sizing API

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| POST | `/api/risk/position-size` | 200 | 仓位大小计算（核心测算端点） |

`POST /api/risk/position-size` 请求体:

```json
{
  "account_equity": 1000000.0,
  "available_cash": 500000.0,
  "symbol": "000001",
  "entry_price": 50.0,
  "invalidation_price": 45.0,
  "risk_per_trade_pct": 1.0,
  "max_single_position_pct": 20.0,
  "max_theme_exposure_pct": 30.0,
  "current_drawdown_pct": 2.0,
  "market": "A",
  "thesis_id": 42,
  "subject_name": "平安银行"
}
```

`POST /api/risk/position-size` 返回值:

```json
{
  "symbol": "000001",
  "entry_price": 50.0,
  "invalidation_price": 45.0,
  "risk_per_share": 5.0,
  "max_loss_amount": 10000.0,
  "raw_quantity": 2000.0,
  "rounded_quantity": 2000,
  "estimated_position_value": 100000.0,
  "estimated_position_pct": 10.0,
  "effective_risk_pct": 1.0,
  "cash_required": 100000.0,
  "cash_after": 400000.0,
  "warnings": [],
  "constraints_applied": ["最小交易单位对齐"],
  "calculation_explain": "基于账户权益 1000000.00...",
  "disclaimer": "本模块仅用于风险预算测算...",
  "error": null
}
```

### Drawdown API

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/risk/drawdown-status` | 200 | 回撤熔断状态（输入 current_drawdown_pct，返回乘数/等级/是否阻断新计划） |

### Event API

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/risk/events` | 200 | 风险事件列表，支持 portfolio_id / event_type / severity 过滤 |

---

## 6. 前端说明

### /risk 页面

路径: `/frontend/src/app/risk/` (待创建)

风险预算工作台。包含:
- 组合选择器（切换 portfolio）
- 当前暴露概览（行业/主题分布，`GET /api/risk/exposure`）
- 风险规则设置（`GET/POST /api/risk/rules`）
- 回撤熔断状态（`GET /api/risk/drawdown-status`）
- 仓位计划列表（`position_plans` 表）
- 风险事件流（`GET /api/risk/events`）

### /agent → 创建风险预算计划

在 Agent 对话框输入投研观点后，支持:
1. 提取 thesis 中的 entry_price / invalidation_price
2. 调用 `POST /api/risk/position-size` 测算
3. 将结果保存为 `position_plan`（draft 状态）
4. 关联 thesis_id

### /watchlist → 创建风险预算计划

在观察池条目的操作菜单中:
1. 选中一条 watchlist_item（已有 thesis 关联）
2. 自动填充 `entry_price`（当前价）和 `invalidation_conditions_json` 中的价格
3. 调用测算端点
4. 保存 plan，关联 `watchlist_item_id` 和 `thesis_id`

### /stocks/[code] → 快速测算

在个股证据终端的"风险核验" Tab:
1. 显示当前价、ST 状态、市值偏小等风险扣分（`risk_engine.py` 的 `assess_stock_risk()`）
2. 提供快速仓位测算入口（填入入场价、无效点、风险比例）
3. 调用 `POST /api/risk/position-size` 返回结果
4. 支持一键保存为 `position_plan`

### 风险扣分引擎

路径: `backend/app/engines/risk_engine.py`

| 条件 | 扣分 | 说明 |
|------|------|------|
| ST 或风险警示 | -4 | 直接扣分 |
| 非活跃或退市风险 | -5 | 直接扣分 |
| 市值 < 80亿 | -1.5 | 流动性风险 |
| 60日最大回撤 > 25% | -2 | 趋势风险 |
| 成交额放大 > 3.5倍 | -1.5 | 情绪过热风险 |

---

## 7. Guardrails

### 系统定位

Alpha Radar 风险预算模块定位为"风险预算测算和仓位计划记录系统"，不输出买卖建议。

### 禁用词替换 (14 条)

路径: `backend/app/risk/guardrails.py`

| 原词 | 替换为 |
|------|--------|
| 建议买入 | 风险预算测算中 |
| 建议卖出 | 风险暴露评估中 |
| 应该买 | 是否执行需由用户独立判断 |
| 应该卖 | 是否执行需由用户独立判断 |
| 可以重仓 | 风险暴露较高，需谨慎评估 |
| 满仓 | 风险暴露达到上限 |
| 梭哈 | 避免单一方向过度暴露 |
| 加杠杆 | 谨慎评估风险暴露 |
| 稳赚 | 存在不确定性 |
| 必涨 | 仍需进一步确认 |
| 无风险 | 风险尚未充分暴露 |
| 保证收益 | 收益预期需独立评估 |
| 仓位推荐 | 风险预算上限 |

### 强制免责声明

所有 API 返回体包含 `boundary` 字段或 `disclaimer` 字段:

```
本模块仅用于风险预算测算和仓位计划记录，不构成任何投资建议、
买卖建议或收益承诺。市场有风险，决策需独立判断。
```

### 只输出风险预算上限

本模块的最终输出是"上限"而非"建议":

- 输出 `effective_risk_pct`: 在全部约束生效后的实际风险比例
- 输出 `estimated_position_pct`: 名义仓位占比上限
- 不输出"建议买入/卖出"类文字
- 所有计算说明经过 `sanitize_risk_output()` 过滤

---

## 8. 示例

### 情景设置

- 账户权益: 1,000,000 元
- 单笔风险比例: 1%
- 入场参考价: 50 元
- 无效点价格: 45 元
- 市场: A 股
- 回撤: 2%（正常区间）
- 可用现金: 500,000 元
- 单票上限: 20%

### 计算过程

```
最大风险金额 = 1,000,000 × 1% × 1.0(回撤乘数) = 10,000 元
每股风险 = 50 - 45 = 5 元
理论最大股数 = 10,000 / 5 = 2,000 股
对齐手数(100)后 = 2,000 股
名义仓位 = 2,000 × 50 = 100,000 元
名义仓位比例 = 100,000 / 1,000,000 = 10%
```

### 约束校验

| 约束 | 上限值 | 是否触发 |
|------|--------|---------|
| 风险预算 | 2,000 股 | - |
| 单票 20% | 200,000 元 -> 4,000 股 | 否（10% < 20%） |
| 可用现金 | 500,000 元 -> 10,000 股 | 否（100,000 < 500,000） |
| 回撤熔断 | 乘数 1.0 | 否 |
| 有效风险 | 1%（未变化） | - |

### 结果

```
最终股数: 2,000
名义仓位: 100,000 元 (10%)
有效风险比例: 1%
占用现金: 100,000 元
剩余现金: 400,000 元
```

---

## 9. 回撤熔断

路径: `backend/app/risk/drawdown.py`

当组合发生回撤时，通过 `drawdown_multiplier` 缩放风险预算，同时判断是否阻断新的 active 计划创建。

### 熔断等级

| 回撤范围 | 风险乘数 | 等级标签 | 行为 |
|---------|---------|---------|------|
| 0% ~ 3% | 1.0 | 正常 | 正常风险预算 |
| 3% ~ 5% | 0.8 | 谨慎 | 提示谨慎，避免随意新增计划 |
| 5% ~ 8% | 0.5 | 收缩 | 单笔风险预算减半 |
| 8% ~ 10% | 0.3 | 防御 | 总风险资产仓位上限降低，不建议新增 active plan |
| 10% ~ 15% | 0.1 | 冷静期 | 阻断新 active plan，仅允许 draft |
| > 15% | 0.05 | 防守期 | 严重回撤，阻断所有新计划 |

### 阻断规则

```python
> 10%: 阻断 active plan 创建，提示"仅保留 draft，待回撤恢复后考虑 activate"
> 15%: 阻断所有 new plan 创建，提示"处于防守期，不允许创建新的 active plan"
```

### 自定义规则

`risk_rules.drawdown_rules_json` 支持自定义回撤熔断规则。未配置时使用 `DEFAULT_DRAWDOWN_RULES`。

```json
[
  {"max_drawdown_pct": 3.0, "risk_multiplier": 1.0, "label": "正常", "description": "正常风险预算"},
  {"max_drawdown_pct": 5.0, "risk_multiplier": 0.8, "label": "谨慎", "description": "提示谨慎"},
  {"max_drawdown_pct": 8.0, "risk_multiplier": 0.5, "label": "收缩", "description": "单笔风险预算减半"},
  {"max_drawdown_pct": 10.0, "risk_multiplier": 0.3, "label": "防御", "description": "总风险资产仓位上限降低"},
  {"max_drawdown_pct": 15.0, "risk_multiplier": 0.1, "label": "冷静期", "description": "只允许观察"},
  {"max_drawdown_pct": 999.0, "risk_multiplier": 0.05, "label": "防守期", "description": "严重回撤"}
]
```

---

## 10. 本地验收命令

### 环境准备

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate
```

### 后端测试

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend

# 风险模块单元测试
.venv/bin/python -m pytest app/tests/test_risk_calculators.py -q -v

# 风险模块全部测试
.venv/bin/python -m pytest app/tests/test_risk*.py -q -v

# 全量测试
.venv/bin/python -m pytest -q
```

### 接口验证

```bash
# 启动后端
cd /home/lishuonewbing/投研系统/alpha-radar/backend
.venv/bin/uvicorn app.main:app --reload --port 8000

# 创建组合
curl -X POST "http://localhost:8000/api/risk/portfolios" \
  -H "Content-Type: application/json" \
  -d '{"name":"测试组合","total_equity":1000000,"cash":500000,"current_drawdown_pct":2.0}'

# 组合列表
curl "http://localhost:8000/api/risk/portfolios"

# 组合详情
curl "http://localhost:8000/api/risk/portfolios/1"

# 新增仓位
curl -X POST "http://localhost:8000/api/risk/portfolios/1/positions" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"000001","quantity":1000,"avg_cost":50,"last_price":52,"market_value":52000,"position_pct":5.2}'

# 仓位大小测算
curl -X POST "http://localhost:8000/api/risk/position-size" \
  -H "Content-Type: application/json" \
  -d '{"account_equity":1000000,"available_cash":500000,"symbol":"000001","entry_price":50,"invalidation_price":45,"risk_per_trade_pct":1.0,"current_drawdown_pct":2.0,"market":"A"}'

# 回撤熔断状态
curl "http://localhost:8000/api/risk/drawdown-status?current_drawdown_pct=6.5"

# 暴露报告
curl "http://localhost:8000/api/risk/exposure?portfolio_id=1"

# 组合规则校验
curl -X POST "http://localhost:8000/api/risk/portfolio-check" \
  -H "Content-Type: application/json" \
  -d '{"portfolio_id":1,"symbol":"000001","position_pct":15}'

# 风险规则列表
curl "http://localhost:8000/api/risk/rules?portfolio_id=1"

# 更新风险规则
curl -X POST "http://localhost:8000/api/risk/rules" \
  -H "Content-Type: application/json" \
  -d '{"portfolio_id":1,"max_risk_per_trade_pct":1.5,"max_single_position_pct":25}'

# 风险事件列表
curl "http://localhost:8000/api/risk/events?portfolio_id=1"
```

### 前端检查

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/frontend
npx tsc --noEmit
npm run lint
npm run build
```

### 前端启动

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/frontend
npm run dev
```

---

## 11. 核心文件路径汇总

### 后端

| 文件 | 说明 |
|------|------|
| `backend/app/risk/__init__.py` | 风险模块包初始化 |
| `backend/app/risk/api.py` | 路由聚合入口 |
| `backend/app/risk/portfolio_api.py` | 所有 `/api/risk` 端点实现（组合/仓位/规则/暴露/事件/回撤/测算） |
| `backend/app/risk/calculators.py` | 仓位大小计算引擎 `calculate_position_size()` |
| `backend/app/risk/drawdown.py` | 回撤熔断规则引擎 `get_drawdown_multiplier()` / `should_block_new_active_plan()` |
| `backend/app/risk/exposure.py` | 组合暴露计算 `compute_exposure()` / `check_portfolio_rules()` |
| `backend/app/risk/guardrails.py` | 合规护栏（14条替换词 + 免责声明 + `sanitize_risk_output()`） |
| `backend/app/risk/schemas.py` | Pydantic 请求/响应模型 `PositionSizeRequest` / `PositionSizeResponse` |
| `backend/app/engines/risk_engine.py` | 个股风险扣分引擎 `assess_stock_risk()`（ST/市值/回撤/成交量） |
| `backend/app/db/models.py` | 6 个数据模型定义（第983行起） |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/app/risk/` | 风险预算工作台页面（待创建） |
| `frontend/src/app/agent/page.tsx` | Agent 页（风险预算计划创建入口） |
| `frontend/src/app/watchlist/page.tsx` | 观察池页（风险预算计划创建入口） |
| `frontend/src/app/stocks/[code]/page.tsx` | 个股证据终端（风险核验 Tab + 快速测算） |

---

## 12. 变更日志

### MVP 3.2 (当前版本)

- **新增风险预算模块**: `backend/app/risk/` 包，6 个数据模型，11 个 REST 端点
- **仓位大小计算引擎**: `calculate_position_size()` 支持多约束层级（风险预算 -> 手数 -> 单票 -> 现金 -> 回撤 -> 主题）
- **回撤熔断系统**: 6 级熔断等级，自动缩放风险预算，阻断新计划创建
- **组合暴露分析**: 个股/行业/主题三个维度的集中度计算和预警
- **个股风险扣分引擎**: `risk_engine.py` 5 项风险扣分因子
- **合规护栏**: 14 条禁用词替换 + 强制免责声明 + sanitize 过滤
- **组合管理 CRUD**: 组合创建、仓位录入、自动行业/主题标签同步
- **情景校验**: `portfolio-check` 端点支持假设仓位加入后的规则违规检测

### MVP 3.1

- Research Thesis 闭环
- 观察池扩展
- 报告质量评分
- Alternative signals

### MVP 3.0

- Agent 多运行时架构
- 报告导出
- 基础数据模型
