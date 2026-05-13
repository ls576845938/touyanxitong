# Alpha Radar MVP 3.0: Research Thesis Closed Loop

## 1. 新定位 (New Positioning)

Alpha Radar 不是交易决策系统，而是**投研判断与复盘系统**。

### 核心区别

| 维度 | 交易决策系统 | Alpha Radar (投研判断与复盘系统) |
|------|-------------|-------------------------------|
| 输出 | 买入/卖出/目标价 | 可追踪、可验证、可复盘的投研观点 |
| 数据模型 | 交易信号 | ResearchThesis + Review Schedule |
| 验证机制 | 回测（历史） | 后验复盘（未来按计划校验） |
| 用户动作 | 下单执行 | 加入观察池, 跟踪证据链, 复盘判断 |
| 合规 | 持牌要求 | 13组禁用词替换 + 免责声明 |

从 MVP 2.x 的"信息系统"升级为"投研系统"：不仅展示信息，还生成可证伪的投研观点，安排后续验证计划，并记录每次复盘的命中/失效结果。

---

## 2. 核心闭环 (Core Closed Loop)

```
发现异常信号/趋势
      ↓
Agent / 日报提取可证伪观点 (ResearchThesis)
      ↓
加入观察池 (WatchlistItem, 关联 thesis)
      ↓
安排验证计划 (ResearchThesisReview: 5日/20日/60日)
      ↓
到期自动复盘 (run_due_reviews)
      ↓
命中 或 失效 或 待定
      ↓
更新 thesis.status (validated / missed / invalidated)
更新 ReportQualityScore (hit_rate_5d / 20d / 60d)
      ↓
反哺评分和报告质量
```

---

## 3. 新增数据模型 (New Data Models)

### research_thesis / research_theses

路径: `backend/app/db/models.py` (第885行 `ResearchThesis`, 第752行 `ResearchThesis`(旧表名 `research_theses`))

```sql
CREATE TABLE research_thesis (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type     VARCHAR(32)  DEFAULT 'agent',       -- daily_report / agent_run / manual
    source_id       VARCHAR(64),                         -- 来源记录主键
    subject_type    VARCHAR(32)  DEFAULT 'stock',        -- stock / industry / market / theme
    subject_id      VARCHAR(64),                         -- 标的代码或ID
    subject_name    VARCHAR(128),                        -- 标的名
    thesis_title    TEXT,                                -- 观点标题
    thesis_body     TEXT,                                -- 观点内容（可证伪判断）
    direction       VARCHAR(16)  DEFAULT 'up',           -- positive / negative / neutral / mixed
    horizon_days    INTEGER      DEFAULT 20,             -- 验证周期（天）
    confidence      FLOAT        DEFAULT 0.0,            -- 置信度 0-100
    evidence_refs_json TEXT     DEFAULT '[]',            -- 证据引用列表
    key_metrics_json TEXT       DEFAULT '{}',            -- 关键指标
    invalidation_conditions_json TEXT DEFAULT '[]',      -- 证伪条件
    risk_flags_json TEXT        DEFAULT '[]',            -- 风险标记
    status          VARCHAR(24)  DEFAULT 'active',       -- active / validated / missed / invalidated / archived
    created_at      DATETIME,
    updated_at      DATETIME
);
```

关键字段说明:

- `direction`: 观点方向。`positive`=看多, `negative`=看空, `neutral`=中性, `mixed`=多空交织
- `confidence`: 置信度，范围 0-100，越高越确信
- `invalidation_conditions_json`: 证伪条件列表。当条件满足时，观点自动判定为失效
- `status`: `active`=活跃观点, `validated`=已验证命中, `missed`=未命中, `invalidated`=证伪失效, `archived`=归档

### research_thesis_review

路径: `backend/app/db/models.py` (第915行 `ResearchThesisReview`, 第775行旧表 `research_thesis_reviews`)

```sql
CREATE TABLE research_thesis_review (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id           INTEGER REFERENCES research_thesis(id),
    review_horizon_days INTEGER,            -- 复盘周期（5/20/60）
    scheduled_review_date DATE,             -- 计划复盘日
    actual_review_date  DATE,               -- 实际复盘日
    review_status       VARCHAR(24) DEFAULT 'pending',  -- pending / hit / missed / invalidated
    realized_metrics_json TEXT DEFAULT '{}',             -- 实际指标值
    realized_return     FLOAT,              -- 实际收益率
    benchmark_return    FLOAT,              -- 基准收益率
    review_note         TEXT,               -- 复盘备注
    evidence_update_json TEXT DEFAULT '{}',              -- 证据更新
    created_at          DATETIME
);
```

复盘状态流转:

- `pending` -> `hit` (命中, 观点方向与市场表现一致)
- `pending` -> `missed` (未命中, 方向错误)
- `pending` -> `invalidated` (证伪条件触发)

每个 thesis 创建时自动生成 3 条 review schedule: 5日 / 20日 / 60日。

### report_quality_scores

路径: `backend/app/db/models.py` (第937行 `ReportQualityScore`)

```sql
CREATE TABLE report_quality_scores (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type             VARCHAR(24),       -- daily_report / agent_run
    source_id               INTEGER,
    thesis_count            INTEGER DEFAULT 0, -- 报告包含的观点数
    evidence_count          INTEGER DEFAULT 0, -- 报告包含的证据数
    avg_confidence          FLOAT DEFAULT 0.0, -- 平均置信度
    hit_rate_5d             FLOAT,             -- 5日命中率
    hit_rate_20d            FLOAT,             -- 20日命中率
    hit_rate_60d            FLOAT,             -- 60日命中率
    unavailable_data_count  INTEGER DEFAULT 0, -- 不可用数据次数
    guardrail_violation_count INTEGER DEFAULT 0, -- 合规违规次数
    quality_score           FLOAT DEFAULT 0.0, -- 综合质量分 0-100
    created_at              DATETIME
);
```

评分不自动调整系统权重，仅用于监控报告质量趋势。

### scoring_feedback_events

路径: `backend/app/db/models.py` (第958行 `ScoringFeedbackEvent`)

```sql
CREATE TABLE scoring_feedback_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id         INTEGER REFERENCES research_thesis(id),
    subject_type      VARCHAR(16),     -- stock / industry / market / theme
    subject_id        VARCHAR(32),
    signal_name       VARCHAR(64),     -- 评分维度名
    expected_direction VARCHAR(16),    -- positive / negative / neutral
    actual_direction  VARCHAR(16),     -- 实际方向
    review_status     VARCHAR(24) DEFAULT 'pending',
    confidence        INTEGER DEFAULT 50,
    created_at        DATETIME
);
```

### alternative_signals

路径: `backend/app/db/models.py` (第629行 `AlternativeSignalRecord`)

```sql
CREATE TABLE alternative_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_name     VARCHAR(64),     -- evidence_momentum / news_sentiment
    subject_type    VARCHAR(16),     -- stock / industry
    subject_id      VARCHAR(32),
    subject_name    VARCHAR(128),
    value           FLOAT,           -- 归一化 0-100
    value_type      VARCHAR(16),     -- score / count / ratio
    source          VARCHAR(32),     -- internal_evidence / news_aggregation / deterministic_proxy
    observed_at     DATE,
    confidence      FLOAT DEFAULT 0.5,
    freshness       VARCHAR(16) DEFAULT 'daily',  -- realtime / daily / weekly
    status          VARCHAR(24) DEFAULT 'available',
    metadata_json   TEXT DEFAULT '{}',
    created_at      DATETIME
);
```

当前已实现的两个计算引擎 (`backend/app/engines/alternative_signals_engine.py`):

- `evidence_momentum`: 比较近7日与前7日 EvidenceEvent 数量，判断关注度是否加速
- `news_sentiment`: 比较近7日与前7日 NewsArticle 覆盖量，判断话题热度变化

### watchlist_items (扩展字段)

路径: `backend/app/db/models.py` (第453行 `WatchlistItem`)

MVP 3.0 扩展字段:

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | VARCHAR(64) | 用户标识 |
| `subject_type` | VARCHAR(16) | stock / industry / theme |
| `subject_id` | VARCHAR(32) | 标的ID |
| `subject_name` | VARCHAR(128) | 标的名 |
| `source_thesis_id` | INTEGER FK | 关联 thesis ID |
| `source_report_id` | INTEGER | 来源报告ID |
| `reason` | TEXT | 加入理由(存 thesis_body) |
| `watch_metrics_json` | TEXT | 观察指标 |
| `invalidation_conditions_json` | TEXT | 失效条件 |
| `priority` | VARCHAR(8) DEFAULT 'B' | S / A / B 三级优先级 |

---

## 4. API 列表 (API Reference)

### Thesis API

路由: `backend/app/api/routes_thesis.py` (prefix: `/api/research`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/research/theses` | 200 | 观点列表，支持 status/subject_type/source_type/direction 过滤 |
| GET | `/api/research/theses/{thesis_id}` | 200 | 观点详情（含 reviews 列表） |

`GET /api/research/theses` 查询参数:

- `status`: `active` / `validated` / `missed` / `invalidated` / `archived`
- `subject_type`: `stock` / `industry` / `market` / `theme`
- `source_type`: `daily_report` / `agent_run` / `manual`
- `direction`: `positive` / `negative` / `neutral` / `mixed`
- `limit`: 默认 50, 最大 200
- `offset`: 默认 0

### Review API

路由: `backend/app/api/routes_thesis_review.py` (prefix: `/api/research/theses`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/research/theses/{thesis_id}/reviews` | 200 | 获取观点复盘列表 |
| POST | `/api/research/theses/{thesis_id}/review` | 200 | 触发单条观点复盘 |
| POST | `/api/research/theses/review-due` | 200 | 批量触发所有到期复盘 |

`POST /api/research/theses/{thesis_id}/review` 触发逻辑:

1. 找到 thesis 的下一个 pending review
2. 调用 `thesis_review_engine.run_thesis_review()` 计算实际表现
3. 更新 review 的 realized_return / benchmark_return / review_status
4. 更新 thesis.status (validated / missed / invalidated)

`POST /api/research/theses/review-due` 批量执行:

```json
{
  "as_of_date": "2026-05-13",
  "total_reviewed": 12,
  "summary": {
    "hit": 5,
    "missed": 3,
    "invalidated": 1,
    "pending": 3
  },
  "results": [...]
}
```

### Watchlist API

路由: `backend/app/api/routes_watchlist.py` (prefix: `/api/watchlist`)

**存量端点 (向后兼容):**

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/watchlist` | 200 | 观察列表（基础版） |
| GET | `/api/watchlist/changes` | 200 | 观察池变动（新进/移出/评分变化） |
| GET | `/api/watchlist/timeline` | 200 | 观察池时间线复盘 |
| POST | `/api/watchlist` | 200 | 添加观察到列表 |

**新增端点 (thesis 闭环):**

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/watchlist/items` | 200 | 观察池条目列表（支持 status/priority/subject_type 过滤） |
| POST | `/api/watchlist/items` | 200 | 从 thesis 添加到观察池 |
| GET | `/api/watchlist/items/{item_id}` | 200 | 获取单条观察池详情 |
| PATCH | `/api/watchlist/items/{item_id}` | 200 | 更新优先级/备注/状态 |
| POST | `/api/watchlist/items/{item_id}/archive` | 200 | 归档观察项 |
| GET | `/api/watchlist/summary` | 200 | 观察池总览（用于 dashboard） |

`POST /api/watchlist/items` 请求体:

```json
{
  "thesis_id": 42,
  "note": "",
  "priority": "A"
}
```

`GET /api/watchlist/summary` 返回值包含:

- `total_active` / `total_archived`: 活跃和归档数量
- `by_priority`: 按优先级分布 {S: 0, A: 0, B: 0}
- `upcoming_reviews`: 即将到期的复盘（含 item_id, subject_name, scheduled_review_date）
- `recently_archived`: 近30天归档记录

### Report Quality API

路由: `backend/app/api/routes_quality.py` (prefix: `/api/research`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/research/report-quality` | 200 | 获取报告质量评分（按需计算） |
| POST | `/api/research/report-quality/compute` | 200 | 强制重新计算质量分 |
| POST | `/api/research/report-quality/update-reviews` | 200 | 用复盘结果更新质量分 |
| GET | `/api/research/feedback-events` | 200 | 评分反馈事件列表 |
| GET | `/api/research/quality-summary` | 200 | 近期质量分汇总 |

`GET /api/research/report-quality` 查询参数:

- `source_type`: `daily_report` 或 `agent_run`（必填）
- `source_id`: 来源记录ID（必填）

`GET /api/research/quality-summary` 返回:

- `window_days`: 统计窗口天数
- `average_quality_score`: 平均质量分
- `total_thesis_count`: 总观点数
- `recent_feedback_event_count`: 近期反馈事件数
- `rows`: 详细记录列表

### Alternative Signals API

路由: `backend/app/api/routes_research.py` (第159行, prefix: `/api/research`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/research/alternative-signals` | 200 | 获取指定标的的 alternative signals |

查询参数:

- `subject_type`: `stock`（当前仅支持 stock）
- `subject_id`: 标的代码（必填）
- `limit`: 默认 20, 最大 100

---

## 5. 引擎说明 (Engine Reference)

### Thesis Engine

路径: `backend/app/engines/thesis_engine.py`

- 从 Agent 产物的 `thesis_ids_json` 字段中提取观点
- 解析每个 thesis 的 direction / confidence / invalidation_conditions
- 写入 `research_thesis` 表

### Thesis Review Engine

路径: `backend/app/engines/thesis_review_engine.py`

核心函数:

- `create_review_schedule(thesis, session)`: 为 thesis 生成 5/20/60 日复盘计划
- `run_thesis_review(thesis, review, session)`: 执行单条复盘，对比 realized_return vs benchmark_return
- `run_due_reviews(as_of_date, session)`: 批量执行所有到期复盘

### Report Quality Engine

路径: `backend/app/engines/report_quality_engine.py`

核心函数:

- `compute_report_quality(source_type, source_id, session)`: 综合计算报告质量分
- `update_quality_from_reviews(source_type, source_id, session)`: 用复盘结果更新命中率

### Alternative Signals Engine

路径: `backend/app/engines/alternative_signals_engine.py`

已实现信号:

- `evidence_momentum`: 证据事件动量评分（近7日 vs 前7日数量比较）
- `news_sentiment`: 新闻覆盖动量评分（文章数量变化）

Pipeline 调度: `backend/app/pipeline/alternative_signals_job.py`

### Watchlist Change Engine

路径: `backend/app/engines/watchlist_change_engine.py`

- `build_watchlist_changes(...)`: 比较两个交易日观察池状态，提取新进/移出/评级变动

---

## 6. 前端工作流 (Frontend Workflow)

核心 4 页面收敛。MVP 3.0 之前共有 27 个页面路由，V3.0 收敛至 4 个核心页面。

### /dashboard - 总览 (`/frontend/src/app/dashboard/page.tsx`)

- **今日核心观点**: 调用 `GET /api/research/theses?source_type=daily_report&status=active` 展示最新观点卡片
- **待复盘观点**: 调用 `GET /api/research/theses?status=active` 筛选即将到期的复盘
- **观察池摘要**: 调用 `GET /api/watchlist/items?status=active` 显示优先级标识 (S/A/B)
- **异常信号**: 产业热度异常波动 (heat_change_7d > 30)
- **观察池核心变动**: 新进/移出/评分变化
- **十倍股研究闭环**: Tenbagger Thesis loop 入口
- **正式研究门控**: Data Gate 状态 (PASS/WARN/FAIL)
- **信号回测校准**: Signal Backtest 快照

### /agent - 投研Agent (`/frontend/src/app/agent/page.tsx`)

- 自然语言投研查询
- 报告生成（含 Thesis 抽取: Agent 产物中的 `thesis_ids_json` 字段）
- 一键加入观察池 (调用 `POST /api/watchlist/items`)
- Follow-up 问答

### /stocks/[code] - 个股证据终端 (`/frontend/src/app/stocks/[code]/page.tsx`)

- K 线趋势图 (`CandleChart` 组件)
- 评分拆解 (行业/公司/趋势/催化剂/风险)
- 证据链 (EvidenceChain 数据)
- 相关观点与复盘历史 (`ResearchThesis` + `ResearchThesisReview`)
- 观察池状态

### /watchlist - 观察池复盘工作台 (`/frontend/src/app/watchlist/page.tsx`)

- 观察池时间线复盘（按交易日追踪变动逻辑）
- 新进/移出/评级上调/评分大幅上升/降级分组
- 市场/板位筛选
- 趋势增强观察标的排行

---

## 7. Guardrails (合规护栏)

### 系统定位

Alpha Radar 定位为"投研判断与复盘系统"，不输出买卖建议。

### 禁用词替换 (13 条)

路径: `backend/app/agent/guardrails.py`

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

### 正则替换 (3 条)

| 模式 | 替换为 |
|------|--------|
| 建议加仓 | 建议跟踪观察 |
| 建议减仓 | 建议复核风险暴露 |
| 目标价[\s]*[:：]?[\s]*[\d.]+ | 估值情景需独立复核 |

### 强制附加内容

所有 Agent 产出自动附加:

```
本报告仅用于投研分析和信息整理，不构成任何投资建议。市场有风险，决策需独立判断。
```

---

## 8. 本地验收命令 (Verification Commands)

### 环境准备

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate
```

### 后端测试

```bash
# 仅存在 test_alternative_signals.py 专用测试文件
cd /home/lishuonewbing/投研系统/alpha-radar/backend
.venv/bin/python -m pytest app/tests/test_alternative_signals.py -q

# 全量测试（含存量测试）
.venv/bin/python -m pytest -q

# Agent 核心测试
.venv/bin/python -m pytest app/tests/test_agent.py -q
.venv/bin/python -m pytest app/tests/test_agent_runtime.py -q
.venv/bin/python -m pytest app/tests/test_agent_events.py -q
.venv/bin/python -m pytest app/tests/test_agent_export.py -q

# 端到端评估
.venv/bin/python scripts/run_agent_eval.py
```

### 接口验证

```bash
# 启动后端
cd /home/lishuonewbing/投研系统/alpha-radar/backend
.venv/bin/uvicorn app.main:app --reload --port 8000

# Thesis 列表
curl "http://localhost:8000/api/research/theses?status=active&limit=5"

# Thesis 详情
curl "http://localhost:8000/api/research/theses/1"

# Thesis 复盘列表
curl "http://localhost:8000/api/research/theses/1/reviews"

# 触发到期复盘
curl -X POST "http://localhost:8000/api/research/theses/review-due"

# 观察池条目列表
curl "http://localhost:8000/api/watchlist/items?status=active"

# 观察池摘要
curl "http://localhost:8000/api/watchlist/summary"

# 报告质量
curl "http://localhost:8000/api/research/report-quality?source_type=daily_report&source_id=1"

# 质量汇总
curl "http://localhost:8000/api/research/quality-summary?days=30"

# Alternative signals
curl "http://localhost:8000/api/research/alternative-signals?subject_type=stock&subject_id=000001"
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

## 9. 核心文件路径汇总

### 后端

| 文件 | 说明 |
|------|------|
| `backend/app/db/models.py` | 所有数据模型定义 (ResearchThesis, ResearchThesisReview, ReportQualityScore, ScoringFeedbackEvent, AlternativeSignalRecord, WatchlistItem) |
| `backend/app/api/routes_thesis.py` | Thesis CRUD API |
| `backend/app/api/routes_thesis_review.py` | Thesis Review API |
| `backend/app/api/routes_watchlist.py` | Watchlist API (含 thesis 闭环端点) |
| `backend/app/api/routes_quality.py` | Report Quality API |
| `backend/app/api/routes_research.py` | Alternative Signals API (第159行) |
| `backend/app/api/routes_stocks.py` | 个股证据与评分接口 |
| `backend/app/engines/thesis_engine.py` | Thesis 抽取引擎 |
| `backend/app/engines/thesis_review_engine.py` | 复盘引擎 (创建计划 + 执行复盘) |
| `backend/app/engines/report_quality_engine.py` | 报告质量计算引擎 |
| `backend/app/engines/alternative_signals_engine.py` | 替代数据信号计算引擎 |
| `backend/app/engines/watchlist_change_engine.py` | 观察池变动分析引擎 |
| `backend/app/agent/guardrails.py` | 合规护栏 (13条替换 + 3条正则 + 免责声明) |
| `backend/app/pipeline/alternative_signals_job.py` | Alternative signals pipeline job |
| `backend/app/pipeline/tenbagger_thesis_job.py` | Tenbagger thesis pipeline job |
| `backend/scripts/run_thesis_review.py` | Thesis 复盘 CLI 脚本 |
| `backend/scripts/run_agent_eval.py` | Agent 端到端评估脚本 |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/app/dashboard/page.tsx` | 总览页 (今日核心观点/待复盘/观察池摘要/异常信号) |
| `frontend/src/app/agent/page.tsx` | 投研 Agent 页 |
| `frontend/src/app/stocks/[code]/page.tsx` | 个股证据终端 (K线/评分拆解/证据链) |
| `frontend/src/app/watchlist/page.tsx` | 观察池复盘工作台 |
| `frontend/src/app/research/thesis/page.tsx` | Tenbagger 逻辑狙击工作台 |
| `frontend/src/app/research/thesis/[code]/page.tsx` | Thesis 明细页 |
| `frontend/src/lib/api.ts` | 前端 API 客户端 (第1354行 ResearchThesis 类型, 第1378行 WatchlistItemEnhanced 类型) |

---

## 10. 变更日志 (Change Log)

### MVP 3.0 (当前版本)

- **新增 ResearchThesis 模型**: 支持观点抽取、存储和状态管理
- **新增 ResearchThesisReview 模型**: 5日/20日/60日验证计划
- **日报观点化**: 每日报告抽取 3-5 条明确判断 (thesis_ids_json)
- **Thesis 后验验证**: 到期自动复盘，计算 realized_return vs benchmark_return
- **评分反馈层**: ScoringFeedbackEvent 记录评分与实际表现的对比（不自动改权重）
- **ReportQualityScore**: 综合报告质量评分（含命中率统计）
- **Alternative data 第一个 connector**: evidence_momentum + news_sentiment 计算引擎
- **WatchlistItem 扩展**: 关联 thesis、优先级 (S/A/B)、证伪条件、观察指标
- **观察池闭环**: thesis -> watchlist -> review -> quality update
- **前端工作流收敛**: 27 页路由收缩为 4 个核心页面
- **Golden Cases 升级**: task_type 维度升级为 thesis quality 维度
- **新增 API 端点**: 14 个新 REST 端点 (thesis/review/watchlist/quality/signals)

### MVP 2.3

- Agent 多运行时架构 (LLM / Hermes / Mock)
- MCP Server (HTTP + stdio)
- SSE 流式事件推送
- 19 个只读工具
- 报告导出 (Markdown / HTML / Print HTML)
- Runtime Health API
- 用户隔离 (X-Alpha-User-Id)
- 运行历史列表

---

## 11. 下一轮建议 (Next Phase Recommendations)

- **更高质量真实数据源**: 降低对 mock 数据的依赖
- **更多 alternative data connectors**: 扩展信号类型和覆盖范围
- **产业链知识图谱增强**: 增加更细粒度的产业链关联
- **Report Quality Dashboard**: 可视化报告质量趋势
- **人工标注反馈**: 支持用户手动标注 thesis 命中/失效
- **真实用户试用**: 收集用户反馈改进产品
- **以下暂缓**: OpenClaw / Skill 市场 / 外部沙箱
