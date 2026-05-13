# Alpha Radar MVP 3.1: Thesis Review Reality Check

## 1. 本轮定位

MVP 3.1 不新增功能。本轮的目标是**验证 Alpha Radar 是否能产出有效的投研判断**。

MVP 3.0 搭建了 thesis -> review -> quality 的闭环数据管道。MVP 3.1 对这一管道输出的真实性做一次"现实检验"(reality check) -- 收集足够样本，量化命中率，校准置信度，识别哪些 thesis 有效、哪些 evidence 失效，最终回答：Alpha Radar 的投研判断是否值得信任。

**不做的事：**

- 不新增 Agent 工具
- 不新增数据源
- 不新增前端页面路由（仅增强现有 dashboard）
- 不改动 thesis/review 数据模型

---

## 2. 核心问题

本轮 Reality Check 要回答以下五个问题：

### Q1: Thesis 是否有命中率？

通过足够样本量（>100 条 thesis）统计整体 hit_rate。如果命中率显著高于随机（>50%），说明 thesis 有预测力。如果接近随机或更低，说明 thesis 生成逻辑有问题。

### Q2: Confidence 是否校准？

比较 confidence 分数与实际命中率。如果 high-confidence thesis 的命中率显著低于 high-confidence 应有的水平（>70%），说明 confidence 分数存在偏差，需要 recalibration。

### Q3: 哪类 thesis 有效？

按维度拆解命中率：

| 维度 | 分组 | 说明 |
|------|------|------|
| subject_type | stock / industry / market / theme | 哪类标的 thesis 更准 |
| direction | positive / negative / neutral / mixed | 看多 vs 看空的命中差异 |
| horizon | 5d / 20d / 60d | 短中长周期哪个更可靠 |
| source_type | daily_report / agent_run / manual | 不同来源质量差异 |
| confidence_bucket | low / medium / high | 置信度分桶后的实际命中率 |

### Q4: 哪类 evidence 失效？

分析 evidence_refs_json 中的引用，标注每条 thesis 生成时使用的 evidence 类型。统计每种 evidence 类型对应的 thesis 命中率，识别"有 evidence 但不准"和"无 evidence 但命中"两种情况。

### Q5: 日报质量是否提升？

对比 MVP 3.0 上线前后的 report_quality_scores 趋势。

---

## 3. 数据流程

```
daily report / agent report
  │
  ├── thesis 抽取 (thesis_engine.py)
  │   └── 写入 research_thesis 表
  │
  ├── review schedule 生成 (thesis_review_engine.create_review_schedule)
  │   └── 写入 research_thesis_review 表 (5d / 20d / 60d)
  │
  ├── review 到期执行 (thesis_review_engine.run_due_reviews)
  │   └── 更新 review_status / realized_return / benchmark_return
  │
  ├── analytics snapshot (run_thesis_replay.py / run_thesis_review.py)
  │   └── 写入 thesis_review_analytics_snapshots 表
  │       ├── hit_rate / miss_rate / inconclusive_rate
  │       ├── by_subject_type_json / by_direction_json / by_horizon_json
  │       ├── by_confidence_bucket_json / by_evidence_type_json / by_source_type_json
  │       ├── calibration_report_json
  │       └── low_sample_warnings_json
  │
  ├── report quality time series (report_quality_engine.py)
  │   └── 写入 / 更新 report_quality_scores 表
  │
  ├── feedback events (ScoringFeedbackEvent)
  │   └── 自动记录评分与实际表现的偏差
  │
  └── manual annotation (人工标注)
      └── 写入 research_thesis_annotations 表
          ├── label: accurate / inaccurate / evidence_weak / too_vague / useful / not_useful / unclear
          ├── rating: 1-5
          └── note: 自由文本备注
```

### 关键表：thesis_review_analytics_snapshots

路径: `backend/app/db/models.py` (第941行 `ThesisReviewAnalyticsSnapshot`)

```sql
CREATE TABLE thesis_review_analytics_snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date           DATE,                -- 快照日期
    sample_size             INTEGER DEFAULT 0,   -- 样本量
    hit_count               INTEGER DEFAULT 0,   -- 命中数
    missed_count            INTEGER DEFAULT 0,   -- 未命中数
    invalidated_count       INTEGER DEFAULT 0,   -- 证伪失效数
    inconclusive_count      INTEGER DEFAULT 0,   -- 无法判定数
    hit_rate                FLOAT,               -- 命中率
    miss_rate               FLOAT,               -- 未命中率
    inconclusive_rate       FLOAT,               -- 无法判定率
    by_subject_type_json    TEXT DEFAULT '{}',    -- 按标的类型拆解
    by_direction_json       TEXT DEFAULT '{}',    -- 按方向拆解
    by_horizon_json         TEXT DEFAULT '{}',    -- 按周期拆解
    by_confidence_bucket_json TEXT DEFAULT '{}',  -- 按置信度分桶拆解
    by_evidence_type_json   TEXT DEFAULT '{}',    -- 按证据类型拆解
    by_source_type_json     TEXT DEFAULT '{}',    -- 按来源拆解
    calibration_report_json TEXT DEFAULT '{}',    -- 校准报告
    low_sample_warnings_json TEXT DEFAULT '[]',   -- 低样本警告列表
    created_at              DATETIME
);
```

该表是 Reality Check 的核心数据输出。每个快照代表一个时间点的复盘分析结果，支持按日期回溯命中率变化趋势。

### 关键表：research_thesis_annotations

路径: `backend/app/db/models.py` (第927行 `ResearchThesisAnnotation`)

```sql
CREATE TABLE research_thesis_annotations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    thesis_id       INTEGER REFERENCES research_thesis(id),
    user_id         VARCHAR(64),          -- 标注者标识（可选）
    label           VARCHAR(32),          -- accurate / inaccurate / evidence_weak / too_vague / useful / not_useful / unclear
    rating          INTEGER,              -- 评分 1-5（可选）
    note            TEXT,                 -- 自由文本备注（可选）
    created_at      DATETIME
);
```

人工标注**不修改** thesis.review_status 或 thesis.status，仅作为独立分析数据使用。

---

## 4. 脚本说明

### run_thesis_replay.py

路径: `backend/scripts/run_thesis_replay.py`

用途: 对历史数据回放，生成 thesis。用于在无 Agent 运行的情况下快速积累 thesis 样本。

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate

# 回放最近 90 天的日报数据，生成 thesis
python -m backend.scripts.run_thesis_replay --days 90 --source daily_report

# 回放 Agent 运行记录
python -m backend.scripts.run_thesis_replay --days 90 --source agent_run

# 全量回放
python -m backend.scripts.run_thesis_replay --days 90 --all
```

输出:
- 新写入 research_thesis 表的记录数
- 新生成 research_thesis_review 的 schedule 数
- 按 source_type 统计的 thesis 数量

### run_thesis_review.py

路径: `backend/scripts/run_thesis_review.py`

用途: 执行到期 review。支持指定日期，默认当天。

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate

# 执行当天到期复盘
python -m backend.scripts.run_thesis_review

# 执行指定日期到期复盘
python -m backend.scripts.run_thesis_review 2026-05-13
```

输出:
- 总处理 review 数量
- 每条 review 的 thesis_id、review_status、review_horizon_days
- 执行完成后自动触发 analytics snapshot 更新

### daily_research_ops.py

路径: `backend/scripts/daily_research_ops.py`

用途: 每日 research 操作流水线。组合 thesis 生成、review 执行、analytics snapshot 三个步骤，适合 cron 定时调度。

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate

# 执行当日完整流水线
python -m backend.scripts.daily_research_ops --date 2026-05-13

# 跳过 thesis 生成（仅执行 review 和 snapshot）
python -m backend.scripts.daily_research_ops --date 2026-05-13 --skip-replay

# 仅更新 analytics snapshot
python -m backend.scripts.daily_research_ops --date 2026-05-13 --snapshot-only
```

流水线步骤:
1. (可选) thesis replay: 从日报/Agent 产出抽取 thesis
2. review execution: 执行到期 review
3. analytics snapshot: 更新 thesis_review_analytics_snapshots 表
4. report quality: 更新 report_quality_scores

---

## 5. API 说明

### Thesis Analytics API

路由: `backend/app/api/routes_thesis.py` (prefix: `/api/research`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/research/theses` | 200 | 观点列表，支持 status/subject_type/source_type/direction 过滤 |
| GET | `/api/research/theses/{thesis_id}` | 200 | 观点详情（含 reviews 列表） |

`GET /api/research/theses` 查询参数:

- `status`: `active` / `validated` / `hit` / `missed` / `invalidated` / `inconclusive` / `archived`
- `subject_type`: `stock` / `industry` / `market` / `theme`
- `source_type`: `daily_report` / `agent_run` / `manual`
- `direction`: `positive` / `negative` / `neutral` / `mixed`
- `limit`: 默认 50, 最大 200
- `offset`: 默认 0

### Report Quality Time Series API

路由: `backend/app/api/routes_quality.py` (prefix: `/api/research`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/research/report-quality` | 200 | 获取报告质量评分（按需计算） |
| POST | `/api/research/report-quality/compute` | 200 | 强制重新计算质量分 |
| POST | `/api/research/report-quality/update-reviews` | 200 | 用复盘结果更新质量分 |
| GET | `/api/research/feedback-events` | 200 | 评分反馈事件列表 |
| GET | `/api/research/quality-summary` | 200 | 近期质量分汇总 |

`GET /api/research/quality-summary` 查询参数:

- `days`: 统计窗口天数，默认 30

返回:

```json
{
  "window_days": 30,
  "average_quality_score": 72.5,
  "total_thesis_count": 156,
  "recent_feedback_event_count": 23,
  "rows": [
    {
      "source_type": "daily_report",
      "source_id": 42,
      "quality_score": 78.0,
      "hit_rate_20d": 0.65,
      "created_at": "2026-05-13T00:00:00"
    }
  ]
}
```

### Annotations API

路由: `backend/app/api/routes_annotations.py` (prefix: `/api/research`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| POST | `/api/research/theses/{thesis_id}/annotations` | 201 | 创建人工标注 |
| GET | `/api/research/theses/{thesis_id}/annotations` | 200 | 获取指定 thesis 的标注列表 |
| GET | `/api/research/annotations` | 200 | 全局标注列表（支持过滤） |
| GET | `/api/research/annotations/summary` | 200 | 标注汇总统计 |

`POST /api/research/theses/{thesis_id}/annotations` 请求体:

```json
{
  "label": "accurate",
  "user_id": "analyst_01",
  "rating": 4,
  "note": "判断准确，证据充分"
}
```

有效 label 值:

- `accurate`: 判断准确
- `inaccurate`: 判断错误
- `evidence_weak`: 证据不足
- `too_vague`: 判断模糊
- `useful`: 有参考价值
- `not_useful`: 无参考价值
- `unclear`: 无法判断

`GET /api/research/annotations/summary` 返回:

```json
{
  "total_annotations": 45,
  "by_label": {
    "accurate": 20,
    "inaccurate": 8,
    "evidence_weak": 5,
    "too_vague": 4,
    "useful": 3,
    "not_useful": 2,
    "unclear": 3
  },
  "average_rating": 3.4
}
```

### Reviews API

路由: `backend/app/api/routes_thesis_review.py` (prefix: `/api/research/theses`)

| 方法 | 路径 | 状态码 | 说明 |
|------|------|--------|------|
| GET | `/api/research/theses/{thesis_id}/reviews` | 200 | 获取观点复盘列表 |
| POST | `/api/research/theses/{thesis_id}/review` | 200 | 触发单条观点复盘 |
| POST | `/api/research/theses/review-due` | 200 | 批量触发所有到期复盘 |

`POST /api/research/theses/review-due` 返回:

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

---

## 6. Dashboard 说明

以下 dashboard 模块全部在已有页面内增强，不新增路由。

### Thesis Review Overview

位置: `frontend/src/app/dashboard/page.tsx`

展示内容:

- **整体命中率**: 取最新 thesis_review_analytics_snapshots 的 hit_rate
- **样本量**: snapshot.sample_size
- **趋势折线图**: 近 30/60/90 天 hit_rate 变化（按 snapshot_date 排序）
- **按方向拆解**: positive / negative / neutral 各自的 hit_rate
- **按周期拆解**: 5d / 20d / 60d hit_rate 对比

调用端点:

- `GET /api/research/theses?status=validated&limit=200` 获取已验证 thesis
- 结合 review 数据计算各维度命中率（前端聚合或新增专用后端端点）

### Confidence Calibration

位置: `frontend/src/app/dashboard/page.tsx`

展示内容:

- **校准曲线**: X 轴为 confidence bucket (0-20, 20-40, 40-60, 60-80, 80-100)，Y 轴为对应 bucket 的 hit_rate
- **理想校准线**: 对角线（confidence = hit_rate）作为参考
- **偏差标注**: 实际命中率显著偏离对角线的 bucket 用红色标记
- **低样本警告**: sample_size < 10 的 bucket 标注 "样本不足"

数据来源:

- thesis_review_analytics_snapshots.calibration_report_json
- thesis_review_analytics_snapshots.by_confidence_bucket_json

### Report Quality Trend

位置: `frontend/src/app/dashboard/page.tsx`

展示内容:

- **质量分时间序列**: report_quality_scores 按 created_at 排序
- **命中率变化**: hit_rate_5d / 20d / 60d 叠加显示
- **质量分 vs 命中率对比**: 判断 quality_score 是否与实际命中率正相关

调用端点:

- `GET /api/research/quality-summary?days=90`
- `GET /api/research/report-quality?source_type=daily_report&source_id={id}`

### Pending Reviews

位置: `frontend/src/app/dashboard/page.tsx`（已有"待复盘观点"模块增强）

展示内容:

- 待复盘 thesis 列表（按 scheduled_review_date 升序）
- 每条显示 thesis_title、subject_name、horizon_days、剩余天数
- "执行复盘"按钮（调用 `POST /api/research/theses/{thesis_id}/review`）
- "批量执行"按钮（调用 `POST /api/research/theses/review-due`）

调用端点:

- `GET /api/research/theses?status=active` 筛选 pending review

---

## 7. 如何解释结果

### 整体 hit_rate 解读

| hit_rate | 解读 | 行动 |
|----------|------|------|
| > 60% | Thesis 有预测力，系统有效 | 可进入小范围试用的阶段 |
| 40-60% | 有一定参考价值但需改进 | 分析哪类 thesis 拖低命中率 |
| < 40% | 预测力不足，需要排查根本原因 | 检查 thesis 生成逻辑和数据质量 |

### inconclusive_rate 解读

| inconclusive_rate | 解读 | 行动 |
|-------------------|------|------|
| < 10% | 正常水平 | 无需特别处理 |
| 10-30% | 部分 thesis 无法验证 | 检查数据覆盖是否完整 |
| > 30% | 大量 thesis 无法判定 | 优先补数据，不要加 Agent 功能 |

### 分层解读示例

```
按 subject_type:
  stock:      hit_rate 68% (n=85)   -- 有效
  industry:   hit_rate 45% (n=30)   -- 需要改进
  market:     hit_rate 30% (n=10)   -- 样本不足

按 direction:
  positive:   hit_rate 62% (n=70)   -- 看多更准
  negative:   hit_rate 48% (n=35)   -- 看空需谨慎
  neutral:    hit_rate 55% (n=20)   -- 中性判断尚可

按 horizon:
  5d:         hit_rate 72% (n=60)   -- 短期预测准
  20d:        hit_rate 55% (n=80)   -- 中期尚可
  60d:        hit_rate 38% (n=30)   -- 长期预测不可靠

按 confidence bucket:
  80-100:     hit_rate 55% (n=25)   -- 高置信度但命中率偏低 → calibration 失败
  60-80:      hit_rate 65% (n=40)   -- 校准良好
  40-60:      hit_rate 58% (n=35)   -- 中等置信度，命中率基本匹配
  0-40:       hit_rate 45% (n=20)   -- 低置信度，符合预期
```

以上示例中需要关注的问题：
1. high confidence (80-100) 但 hit_rate 仅 55% -- confidence 未校准
2. 60d horizon hit_rate 仅 38% -- 长期 thesis 不具备预测力
3. market 类型样本仅 10 -- 不足以做判断

### 高置信度不准的情况

如果 confidence > 80 但 hit_rate < 60%，说明 confidence 分数存在系统性偏差。可能原因：

- thesis 生成时高估了证据质量
- evidence_refs 引用不足或过时
- confidence 分数本身缺少 calibration

处理方式：重新设计 confidence 评分规则，或者在报告中降低 confidence 分。

---

## 8. 下一步决策规则

基于 Reality Check 的结果，按以下规则决策 MVP 3.2 的优先级。

```
                    hit_rate > 60%
                   /              \
                  /                \
         inconclusive < 10%    inconclusive 10-30%
              |                      |
              v                      v
      小范围真实试用           改进 evidence / scoring
      收集用户反馈              修复数据覆盖
              |                      |
              v                      v
          MVP 3.2                MVP 3.2
      真实用户试点              evidence 增强

                    hit_rate 40-60%
                         |
                         v
                  改进 evidence / scoring
                  优化 thesis 生成 prompt
                  增加 evidence 覆盖
                         |
                         v
                      MVP 3.2
                  evidence 增强

                    hit_rate < 40%
                    (或 inconclusive > 50%)
                         |
                         v
                  补数据，不加 Agent 功能
                  检查数据源质量
                  扩展数据覆盖范围
                  重新跑 reality check
                         |
                         v
                      MVP 3.2
                  数据质量改进

              高置信度不准 (confidence > 80, hit_rate < 60%)
                         |
                         v
                  重做 confidence calibration
                  调整 thesis 生成的 confidence 规则
                  重新评估 evidence 质量
```

### 决策条件速查表

| 条件 | 决策 | 对应 MVP |
|------|------|----------|
| hit_rate > 60% 且 inconclusive < 10% | 小范围真实试用 | 3.2 用户试点 |
| hit_rate > 60% 且 inconclusive 10-30% | 改进 evidence / scoring | 3.2 evidence 增强 |
| hit_rate 40-60% | 改进 evidence / scoring | 3.2 evidence 增强 |
| hit_rate < 40% | 补数据，不加功能 | 3.2 数据质量 |
| inconclusive > 50% | 补数据，不加功能 | 3.2 数据质量 |
| high confidence 不准 | 重做 calibration | 3.2 calibration |

---

## 9. 本地验收命令

### 后端测试

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate

# 全部测试
.venv/bin/python -m pytest -q

# Reality Check 相关测试
.venv/bin/python -m pytest app/tests/test_thesis_review.py -q -v
.venv/bin/python -m pytest app/tests/test_annotations.py -q -v
.venv/bin/python -m pytest app/tests/test_quality.py -q -v

# 运行 thesis review 脚本（干跑，不写库）
python -m backend.scripts.run_thesis_review --dry-run

# 运行 thesis replay（干跑，回显即将生成的 thesis）
python -m backend.scripts.run_thesis_replay --dry-run --days 30

# 运行每日流水线（干跑）
python -m backend.scripts.daily_research_ops --date 2026-05-13 --dry-run

# 后端启动
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 接口验证

```bash
cd /home/lishuonewbing/投研系统/alpha-radar/backend
source .venv/bin/activate

# Thesis 列表（含 inconclusive 状态）
curl "http://localhost:8000/api/research/theses?status=active&limit=5"

# Thesis 详情
curl "http://localhost:8000/api/research/theses/1"

# 到期复盘执行
curl -X POST "http://localhost:8000/api/research/theses/review-due"

# 报告质量汇总（近 90 天）
curl "http://localhost:8000/api/research/quality-summary?days=90"

# 人工标注
curl -X POST "http://localhost:8000/api/research/theses/1/annotations" \
  -H "Content-Type: application/json" \
  -d '{"label":"accurate","rating":4,"note":"判断准确"}'

# 获取标注
curl "http://localhost:8000/api/research/theses/1/annotations"

# 标注汇总
curl "http://localhost:8000/api/research/annotations/summary"
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

### 期望结果

| 检查项 | 期望结果 |
|--------|----------|
| backend tests | 全部通过 |
| run_thesis_review --dry-run | 输出待处理 review 清单，无报错 |
| run_thesis_replay --dry-run | 输出待生成 thesis 清单，无报错 |
| curl endpoint 验证 | 返回 200，JSON 格式正确 |
| tsc --noEmit | 无 type error |
| npm run lint | 无 lint error |
| npm run build | 构建成功 |

---

## 10. 核心文件路径汇总

### 后端

| 文件 | 说明 |
|------|------|
| `backend/app/db/models.py` | 数据模型 (ResearchThesis 第846行, ResearchThesisReview 第871行, ReportQualityScore 第891行, ScoringFeedbackEvent 第912行, ResearchThesisAnnotation 第927行, ThesisReviewAnalyticsSnapshot 第941行) |
| `backend/app/api/routes_thesis.py` | Thesis 列表 + 详情 API |
| `backend/app/api/routes_thesis_review.py` | Review 执行 API (单条 + 批量到期) |
| `backend/app/api/routes_quality.py` | Report quality 评分 API + feedback events |
| `backend/app/api/routes_annotations.py` | 人工标注 API (CRUD + 汇总) |
| `backend/app/engines/thesis_engine.py` | Thesis 抽取引擎 |
| `backend/app/engines/thesis_review_engine.py` | 复盘执行引擎 (create_review_schedule, run_thesis_review, run_due_reviews) |
| `backend/app/engines/report_quality_engine.py` | 报告质量计算引擎 |
| `backend/scripts/run_thesis_review.py` | 到期 review CLI 脚本 |
| `backend/scripts/run_thesis_replay.py` | 历史回放生成 thesis CLI 脚本 (计划) |
| `backend/scripts/daily_research_ops.py` | 每日 research 流水线 CLI 脚本 (计划) |

### 前端

| 文件 | 说明 |
|------|------|
| `frontend/src/app/dashboard/page.tsx` | 总览页 (含 Thesis Review Overview, Confidence Calibration, Report Quality Trend, Pending Reviews) |
| `frontend/src/app/research/thesis/page.tsx` | Thesis 列表页 |
| `frontend/src/app/research/thesis/[code]/page.tsx` | Thesis 明细页 |

### 测试

| 文件 | 说明 |
|------|------|
| `backend/app/tests/test_thesis_review.py` | Thesis review 引擎测试 |
| `backend/app/tests/test_annotations.py` | 人工标注 API 测试 |
| `backend/app/tests/test_quality.py` | Report quality 引擎测试 |
