# Scoring Model

总分：

```text
raw_score = industry_score + company_score + trend_score + catalyst_score - risk_penalty
final_score = raw_score * (0.65 + combined_confidence * 0.35)
```

## 权重

- 产业趋势分：30
- 公司质量分：25
- 股价趋势分：25
- 信息催化分：10
- 风险扣分：10

## 公司质量分

`company_score` 不使用固定占位值。优先读取最新 `fundamental_metric`：

- 营收同比增速：5 分。
- 利润同比增速：5 分。
- 毛利率：4 分。
- ROE：4 分。
- 负债率：3 分，负债率越低越好。
- 现金流质量：4 分。

缺少基本面快照时，只保留市值与上市日期形成的低上限基础分，且 `fundamental_confidence` 为低置信并在解释中标注“基本面数据缺失”。评分和证据链解释必须列出营收增速、利润增速、毛利率、ROE、负债率、现金流质量、财报日期和来源。

## 等级

- 85-100：强观察，需人工重点研究
- 70-84：观察，纳入候选池
- 55-69：弱观察，等待更多证据
- 40-54：仅记录
- 0-39：排除

## 解释要求

评分结果必须说明产业、趋势、催化、风险的主要贡献项。任何证据不足的股票应明确标注“当前证据不足，不能形成有效观察结论。”

## 产业雷达综合热度

`IndustryHeat` 表中的 `heat_1d`、`heat_7d`、`heat_30d` 和原始 `heat_score` 保留为资讯热度证据。`/api/industries/radar` 输出中的 `heat_score` 为综合热度，按请求市场口径组合：

- 资讯热度：来自最新 `IndustryHeat.heat_score`，同时以 `news_heat_score`/`global_heat_score` 返回。
- 股票覆盖：当前市场已上市、活跃、权益类股票的 `related_stock_count`。
- 评分覆盖：最新评分日的 `scored_stock_count`。
- 观察池宽度：最新评分日评级为“强观察/观察”的 `watch_stock_count`。
- 趋势宽度：最新趋势日均线多头股票占趋势覆盖股票比例，即 `trend_breadth`。
- 突破宽度：最新趋势日 120 日或 250 日突破股票占趋势覆盖股票比例，即 `breakout_breadth`。

结构热度以 `structure_heat_score` 返回，取值 0-30 分，只计入评分、观察池、趋势和突破证据：

```text
structure_heat_score = scored_factor * 10
                     + watch_factor * 8
                     + trend_breadth * trend_factor * 7
                     + breakout_breadth * breakout_factor * 5
```

其中各 `*_factor` 是当前行业相对同市场最大覆盖数的归一化比例。股票映射数量只用于市场口径过滤和资讯热度折算，不单独产生结构热度；仅有股票映射且没有评分、趋势、观察池或资讯时，综合热度为 0。

综合热度最高 30 分：

```text
heat_score = min(30, news_heat_score / 30 * 11 * market_news_factor
                     + structure_heat_score / 30 * 19)
```

`market_news_factor` 在市场筛选下按关联股票覆盖折算，全市场口径为 1。综合热度不设置最低 0.5 分兜底，缺少资讯和结构证据时保持 0。

`evidence_status` 标识当前热度证据状态：

- `news_active`：有资讯热度，`news_heat_score > 0`。
- `structure_active`：资讯热度为 0，但评分、观察池、趋势或突破证据给出非零结构热度。
- `mapped_only`：仅有股票映射，没有评分、趋势、观察池或资讯证据，`heat_score = 0`。
- `no_evidence`：无映射、无评分、无趋势、无资讯证据，`heat_score = 0`。

因此没有新闻的行业，只有在当前市场有已评分股票、观察池股票或趋势/突破证据时，才会获得非零综合热度。若综合热度为 0，`zero_heat_reason` 说明缺失来源；若资讯热度为 0 但综合热度非零，`zero_heat_reason` 和 `explanation` 会说明结构化证据来源。

前端展示约定：

- 产业页卡片必须展示“资讯活跃 / 结构活跃 / 仅有映射 / 无证据”之一，不能只用 `heat_score > 0` 推断活跃状态。
- `heat_score = 0` 时不得渲染为 active，应显示 `zero_heat_reason`；接口未返回原因时，按关联股票数量兜底为“仅有映射”或“无证据”。
- 首页“今日最强赛道”在 `top_keywords` 为空时，应展示证据状态、关联股票、观察池和趋势/突破宽度，避免用户把空关键词误读为热度证据。

## 置信度与研究准入

评分同时输出四类可解释置信度，并保留兼容字段：

- `source_confidence`：数据源可信度，主要衡量是否有有效行情趋势源。
- `data_confidence`：结构化数据可信度，衡量行情趋势、市值、上市日期等覆盖。
- `fundamental_confidence`：基本面摘要可信度，衡量最新财报快照是否覆盖营收增速、利润增速、毛利率、ROE、负债率和现金流质量。
- `news_confidence`：资讯证据可信度，衡量个股资讯证据覆盖。
- `evidence_confidence`：兼容字段，衡量行业热度和个股资讯证据覆盖。

综合置信度计算：

```text
combined_confidence = source_confidence * 0.20
                    + data_confidence * 0.30
                    + fundamental_confidence * 0.25
                    + news_confidence * 0.25
```

综合置信度低于 0.65 时，观察评级会被限制在“弱观察”或“仅记录”，并在解释中标明原因；这不是交易建议或荐股结论。前端展示两层门槛：

- 研究股票池准入：先过滤 ST、非活跃、历史不足、市值和流动性不足等标的。
- 评分可信度：展示 `high`、`medium`、`low`、`insufficient` 以及四类置信度，低可信度标记为“复核”。

前端字段约定：

- `/api/stocks/trend-pool` 在每只股票上返回 `research_gate`、`confidence`、`fundamental_summary`、`news_evidence_status`。
- `/api/stocks/{code}/evidence` 在 `score` 上返回同样的 `confidence`、`research_gate`、`fundamental_summary`、`news_evidence_status`，在 `evidence` 上返回 `evidence_status`。
- `/api/reports/latest` 会对日报内的观察股做兼容归一化，旧日报缺少细分字段时用原有 `data_confidence`、`evidence_confidence` 推导展示。

接口字段约定：

- `heat_score`：当前筛选市场下展示的综合热度。
- `global_heat_score`/`news_heat_score`：全市场资讯热度基准，用于说明行业新闻/资讯本身的热度。
- `structure_heat_score`：0-30 分结构热度，只来自评分、观察池、趋势和突破证据。
- `evidence_status`：证据状态，取值 `news_active`、`structure_active`、`mapped_only`、`no_evidence`，前端兼容对应中文值。
- `related_stock_count`：当前市场关联股票数量。
- `scored_stock_count`：当前市场已有评分的关联股票数量。
- `watch_stock_count`：当前市场进入观察池的关联股票数量。
- `trend_breadth`/`breakout_breadth`：当前市场趋势多头和突破宽度。
- `zero_heat_reason`：综合热度为 0，或资讯热度为 0 但结构化证据给出非零综合热度时的解释，避免把证据来源误读为系统异常。
