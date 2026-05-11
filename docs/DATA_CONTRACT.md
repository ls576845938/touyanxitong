# Data Contract

所有入库数据必须保留 `source` 与 `created_at` 或 `ingested_at` 字段。派生数据必须保留 `explanation` 与生成时间。

## 数据层

- `stock`: 股票基础库。
- `daily_bar`: 日线行情。
- `fundamental_metric`: 基本面财报快照。
- `industry`: 产业分类。
- `industry_keyword`: 产业关键词。
- `chain_node`: 可投资、可观测、可传导的产业链节点。
- `chain_edge`: 节点之间的物理流、投入产出、物流、回收或控制关系。
- `chain_node_industry_map`: 节点到现有行业分类的映射。
- `chain_node_stock_map`: 节点到上市公司的映射。
- `chain_node_region`: 节点到资源地、产能地、装配地、枢纽和消费地的地理映射。
- `chain_node_indicator`: 节点到商品、指数、运价、利率等可观测指标的映射。
- `chain_node_heat`: 节点级热度历史与传播结果。
- `news_article`: 新闻、公告、研报标题等文本数据。
- `trend_signal`: K 线趋势指标。
- `industry_heat`: 产业热度。
- `stock_score`: 十倍股早期特征评分。
- `evidence_chain`: 单股证据链。
- `tenbagger_thesis`: 十倍股研究假设，承接空间、成长、质量、估值、趋势、证据、风险、门控状态和证伪条件。
- `signal_backtest_run`: 信号回测/校准运行摘要，用于按 as-of 日期评估规则分层效果。
- `daily_report`: 每日投研简报。

## Source

第一版支持 mock 数据，同时接入市场级 Provider Registry。真实数据源不可用时，mock 数据只保证 pipeline 闭环可复现，不能进入正式研究准入池。

数据源由环境变量控制：

- `MOCK_DATA=true`: 强制使用可复现 mock 数据。
- `MARKET_DATA_SOURCE=mock|auto|akshare|tencent|yahoo|baostock`: 选择免费行情和股票基础库 provider；也可以传逗号分隔 provider chain。
- `MARKET_DATA_PROVIDER_CHAIN=A=tencent,yahoo,baostock,akshare;HK=tencent,yahoo,akshare;US=yahoo,akshare`: 可选市场级 provider 优先级覆盖。默认链路不使用付费源。
- `ALLOW_MOCK_FALLBACK=true`: 真实源失败时是否允许 mock fallback。生产回填建议设为 `false`，避免生成非正式数据。
- `NEWS_DATA_SOURCE=mock|auto|rss|news`: 选择资讯 provider。`mock` 保持可复现样本；`auto` 默认使用无需 key 的 Google News RSS search，按产业名和核心关键词生成搜索 feed；`rss` / `news` 使用统一 RSS 适配抽象，配置 `NEWS_RSS_FEEDS` 时按显式 feed 抓取。
- `NEWS_RSS_FEEDS=https://example.com/rss.xml,...`: RSS 源列表，逗号分隔。
- `ENABLED_MARKETS=A,US,HK`: 控制 pipeline 扫描市场范围。
- `MAX_STOCKS_PER_MARKET=50`: 控制每个市场单次行情下载股票数；设置为 `0` 才表示不限制。
- `MARKET_DATA_PERIODS=320`: 控制每只股票请求的日线根数。
- `DATABASE_URL`: 默认 SQLite 数据库统一解析到 `backend/data/alpha_radar.db`，避免从项目根目录或 `backend/` 目录启动时生成两个 `alpha_radar.db`。显式传入绝对 SQLite 路径或非 SQLite URL 时按传入值使用。
- `DATABASE_POOL_PRE_PING=true`: SQLAlchemy 连接池借出连接前先探活。默认开启，主要用于 PostgreSQL 长连接恢复；SQLite 本地运行可保持默认。
- `TUSHARE_TOKEN` / `POLYGON_API_KEY` / `TIINGO_API_KEY` / `EODHD_API_KEY`: 预留可选凭证。当前默认链路不使用这些付费或 token 型 provider。

当 `MOCK_DATA=false` 且 `MARKET_DATA_SOURCE=auto` 时，系统按市场级链路依次尝试免费 provider。默认链路为：A 股 `tencent -> yahoo -> baostock -> akshare`，港股 `tencent -> yahoo -> akshare`，美股 `yahoo -> akshare`。每次 `stock_universe` 和 `market_data` 运行都会写入 `data_source_run`，记录 requested source、effective source、source kind、source confidence、market scope、rows、status、error 和时间戳。

行情源合同：

- `daily_bar.source`: 具体 provider 名称，例如 `akshare`、`tencent`、`yahoo`、`baostock`、`mock`。`tushare/tiingo/polygon/eodhd` 等 token 型 provider 仅作为预留扩展。
- `daily_bar.source_kind`: 标准化来源类型，当前支持 `real`、`mock`、`fallback`、`unknown`。
- `daily_bar.source_confidence`: 0-1 来源置信度。默认 real=1.0、fallback=0.35、mock=0.1、unknown=0.0。
- `mock` 只用于可复现 MVP 闭环，`fallback` 只表示真实源不可用时的替代数据，两者都不能被当成正式研究行情。
- `/api/market/data-quality` 同时返回总体覆盖率和 `real_coverage_ratio`；只有 mock/fallback 覆盖时仍视为非正式研究数据。
- Provider 返回 `no_usable_bars` 或 `unsupported_daily_bars` 的标的会进入可解释失败与队列冷却，不应反复污染后续抓取任务。

资讯源合同：

- `news_article.source`: 具体来源名称，例如 `mock`、RSS channel title 或真实新闻供应商名称。
- `news_article.source_kind`: 标准化来源类型，当前支持 `mock`、`rss`、`news`，后续可扩展 `announcement`、`research`。
- `news_article.source_confidence`: 0-1 来源置信度。默认 mock=0.3、rss=0.8、news=0.9。
- RSS 适配会从标题和摘要匹配产业关键词，写入 `matched_keywords` 与 `related_industries`。未匹配关键词的资讯仍可入库，但不会贡献产业热度。
- `auto` 资讯源会为每个 `INDUSTRY_SEEDS` 行业生成一个搜索 feed，query 覆盖行业名和该行业核心关键词，并限制单 feed item 数以控制抓取耗时。单个 feed 网络错误或解析错误只跳过该 feed，不中断整批资讯入库。
- 产业关键词匹配会把 feed query 作为弱上下文参与匹配，用于处理搜索命中某赛道但标题/摘要未重复关键词的资讯；文章仍保留原始标题、摘要、`source_url` 和 `published_at`。
- 产业热度计算会按 `source_kind/source_confidence` 加权：mock 证据只用于闭环演示并显著降权；真实新闻/RSS 权重更高。近 30 日匹配资讯不足或只有 mock 证据时，`industry_heat.explanation` 必须明确提示“资讯覆盖不足/已降权”。

热词源合同：

- `/api/research/hot-terms` 聚合 `news_article`、`industry_heat` 和 `industry_keyword`，输出平台热词、热门产业、分平台矩阵和来源状态。
- `/api/research/hot-terms/refresh` 只抓公开 RSS 或公开列表页，覆盖 `xueqiu/reddit/tonghuashun/eastmoney/taoguba/ibkr/wsj/reuters_markets/cnbc_markets/marketwatch/barrons/investing`。不登录、不携带用户 Cookie、不绕过付费墙或私有 API。
- 外部热词入库仍写入 `news_article`：`source` 为平台 key，`source_kind` 为 `community|market_media|broker|professional_media`，`source_confidence` 按来源质量降权或加权。热词链路必须写入 `source_channel/source_label/source_rank/match_reason/is_synthetic`，其中 `is_synthetic=true` 不得作为正式外部热词入库；存量 `mock://`、`mock*`、`*fallback*` 新闻在迁移和 API 输出层都会强制标记为 synthetic。
- 每个平台刷新会写入 `data_source_run.job_name=hot_terms_<source>`，记录成功、部分失败、失败、空结果、错误信息、插入数、跳过数和过滤数。接口按最近一次运行把来源标成 `active`、`connected_empty`、`degraded`、`error` 或 `pending_connector`，并额外返回 `connector_status/window_data_status/relevance_rate` 供前端展示。
- 社区源只做标题/摘要级发现并降权；付费墙源只做标题级发现；正文、评论全文、研报全文不进入默认热词抓取。

产业雷达 `/api/industries/radar` 的热度字段分层：

- `news_heat_score`: 资讯热度，来自 `industry_heat.heat_score`。
- `structure_heat_score`: 行情结构热度，来自股票映射覆盖、评分覆盖、观察池数量、趋势覆盖、均线多头宽度、突破宽度、平均 `stock_score.final_score` / `trend_score`、平均 `trend_signal.trend_score` 和 `volume_expansion_ratio`。
- `heat_score`: 综合热度，按当前 `market=A|HK|US|ALL` 口径融合资讯热度与行情结构热度。
- `explanation` / `zero_heat_reason`: 必须说明热度来自资讯、评分、观察池、趋势、突破、量能或仅映射等证据。即使 `news_heat_score=0`，只要存在评分、观察池、趋势或突破证据，`heat_score` 也可以大于 0；只有单纯股票映射且无结构证据时应保持 `mapped_only` 或低热度。

`未分类`、空行业名、`unknown` 等行业只用于数据质量诊断。产业雷达计算结构热度基准值时应排除这些未分类分组，未分类分组自身输出时需要降权，避免大量未分类股票压制已分类产业。

产业映射合同：

- `industry_mapping` 规则默认只填补 `stock.industry_level1` 为空、`未分类`、`未知`、`未知行业` 等弱分类的股票；已有强分类不能被默认覆盖。
- 映射证据来自股票名称、二级行业、概念标签和精确 `code/symbol/ticker` hints。短词和泛词不能仅因股票名称命中而落位，除非该词在明确公司名 hints 中；二级行业和概念标签可使用更通用的行业关键词。
- 每次成功映射都在 `stock.metadata_json.industry_mapping_v1` 写入 `version`、`industry`、`confidence`、`reason`、`matched_keywords`、`evidence`，用于审计映射版本、置信度和字段证据。

研究准入池会显式检查数据源可信度。当前免费正式研究可信源为 `tencent`、`yahoo`、`baostock`、`akshare` 等 `real` 来源；`mock/fallback` 只用于演示和失败兜底，不代表生产研究背书。基础库来源来自 `stock.source` / `stock.data_vendor`，行情来源来自 `daily_bar.source`。同一股票存在多行情源时，准入只选择一个可信度最高、历史最完整的 source 计数，不把不同 source 的 K 线条数相加。

产业链图谱合同：

- 节点是基本单位，不等同于传统行业。节点可以是资源、材料、部件、设备、终端、渠道、服务或回收环节。
- 内置种子图谱位于 `app.services.chain_seed`，导出 `CHAIN_LAYERS`、`CHAIN_NODES`、`CHAIN_EDGES`、`WORLD_REGIONS` 和 `DEFAULT_FOCUS_NODE_KEY`。当前种子图谱覆盖 8 层、97 个节点、190 条边和 10 个世界区域。
- `CHAIN_LAYERS` 固定为：自然资源、公共品与能源、基础材料、通用零部件、设备与系统、终端产品、渠道与服务、回收与再生产。
- `CHAIN_NODES.industry_names` 用于把节点映射回现有 `industry` 与 `stock.industry_level1`，从而复用行业热度、股票评分和趋势信号。
- `CHAIN_EDGES.weight` 是热度传播权重。当前传播只做轻量衰减，后续可替换为投入产出表或自研暴露度。
- `WORLD_REGIONS` 区分资源地、产能地、装配地、枢纽和消费地。前端只负责投影，不能把地理分布作为事实源硬编码。

产业链接口：

- `/api/chain/overview`: 返回全图摘要、层、节点、边、区域和默认焦点。
- `/api/chain/nodes/{node_key}`: 返回单节点、上下游、同层联动、映射行业、龙头股票、区域、指标和热度解释。
- `/api/chain/geo?node_key=...`: 返回世界区域热度与区域间路径。
- `/api/chain/timeline?node_key=...`: 返回节点热度时间序列，当前按映射行业的 `IndustryHeat` 聚合。

节点热度字段：

- `industry_heat_score`: 映射行业的行业热度贡献。
- `stock_signal_score`: 映射股票的评分、趋势和观察池贡献。
- `propagated_heat_score`: 上游节点沿 `chain_edge.weight` 衰减传播后的贡献。
- `heat_score` / `heat`: 节点综合热度，0-100。
- `intensity`: 前端热力强度，0-1。黄、橙、红只表达强度，不表达投资建议。
- `explanation` / `heat_explanation`: 必须说明热度来自行业热度、股票评分、趋势信号、传播或仅映射。

基本面源合同：

- `fundamental_metric.stock_code`: 股票代码，关联 `stock.code`。
- `fundamental_metric.report_date`: 财报日期或公告报告期日期。
- `fundamental_metric.period`: 报告期，例如 `2026Q1`。
- `revenue_growth_yoy` / `profit_growth_yoy`: 营收和利润同比增速，单位为百分点。
- `gross_margin` / `roe` / `debt_ratio`: 毛利率、ROE、负债率，均为 0-1 小数。
- `cashflow_quality`: 现金流质量，使用经营现金流/净利润等可比口径。
- `report_title` / `source` / `source_url`: 财报或公告来源引用。

mock provider 在 `stock_universe` 阶段同步写入可复现财务快照，保证后续 `stock_score.company_score` 和 `evidence_chain.company_logic` 不依赖固定占位值。

## Database Reliability

默认本地数据库：

```text
sqlite:///./alpha_radar.db -> backend/data/alpha_radar.db
```

PostgreSQL 示例：

```text
postgresql+psycopg://alpha:alpha@localhost:5432/alpha_radar
```

启动时数据库初始化顺序是：

1. 解析并规范化 `DATABASE_URL`。
2. SQLite 文件型数据库自动创建父目录。
3. 执行 SQLAlchemy metadata 建表。
4. 执行轻量 schema migrations，并写入 `schema_migration(version, name, applied_at)`。

当前 schema 版本由后端常量维护，已应用版本保存在数据库中。`/health` 暴露 `database_dialect`、`database_path`、`schema_version`、`schema_expected_version`、`schema_current` 和 `database_available`。SQLite 的 `database_path` 是实际文件路径；PostgreSQL 没有本地文件路径，返回 `null`。

## Market Segments

股票基础库使用稳定代码区分市场和板块：

- `market=A`: A股
- `market=US`: 美股
- `market=HK`: 港股

A股 `board` 至少支持：

- `main`: 主板
- `chinext`: 创业板
- `star`: 科创板
- `bse`: 北交所

美股和港股可按交易所或市场层级扩展，例如 `nasdaq`、`nyse`、`hk_main`。前端只做展示映射，分析与筛选统一依赖 `market` 和 `board` 字段。

## Data Source Run

`data_source_run` 是 pipeline 运行留痕表：

- `job_name`: `stock_universe` / `market_data`
- `requested_source`: 配置请求的数据源。
- `effective_source`: 实际使用的数据源，可能是真实源，也可能是 fallback。
- `source_kind` / `source_confidence`: 本次运行有效数据源的可信类别和置信度。
- `markets`: 本次扫描市场范围。
- `status`: `success` / `failed`
- `rows_inserted` / `rows_updated` / `rows_total`
- `error`
- `started_at` / `finished_at`

前端 Dashboard 通过 `/api/market/data-status` 展示各市场日线覆盖率、按 `source_kind` 拆分的行情覆盖和最近运行状态。

## Research Universe

`/api/market/research-universe` 返回研究准入池摘要。准入规则按市场配置，最小闭环必须同时检查：

- `min_history_bars`: 选定单一行情 source 的历史 K 线根数。
- `min_avg_amount_20d`: 最近 20 日平均成交额。
- `min_market_cap` / `min_float_market_cap`: 总市值与流通市值。
- `min_price`: 最新收盘价。
- `is_active`、`listing_status`、`is_st`、`is_etf`、`asset_type`: 活跃、未退市、非 ST、非 ETF、普通股。
- `data_source_trust`: 基础库和行情 source 必须可信。

响应字段：

- `summary`: 总股票数、可研究数、排除数、准入率。
- `segments`: 按 `market` + `board` 汇总，并包含该分段的 `exclusion_reasons` 计数。
- `exclusion_summary`: 全市场排除原因计数。
- `rules`: 各市场准入阈值。
- `trusted_data_sources`: 当前可信源及权重。
- `rows`: 仅在 `include_rows=true` 时返回，包含 `eligible`、`exclusion_reasons`、`selected_bar_source`、`data_source_trust`、`source_profile`。

`trend_signal` pipeline 必须先通过同一套准入池筛选股票，再计算趋势指标；历史不足、低成交额、低市值、低价、ST/退市/非活跃或 source 不可信的股票不能进入趋势池，也不能继续生成评分、证据链和日报候选。

## Tenbagger Research Loop

十倍股研究闭环分为三层：

- 发现层：`stock_score` 仍负责产业、公司、趋势、催化、风险的早期线索排序。
- 假设层：`tenbagger_thesis` 在评分之上生成可证伪研究假设，拆分为空间、成长、质量、估值容忍、趋势时机、证据覆盖、风险和 readiness。估值/TAM/管理层等数据缺失时必须写入 `missing_evidence`，不能用高分掩盖证据缺口。
- 校准层：`signal_backtest_run` 用历史信号日后的同源 K 线计算 forward return、max return 和分层命中率。该结果只用于规则校准，不代表可交易收益。

正式研究数据门控：

- `data_gate_status=FAIL`：不得进入正式十倍股候选，只能作为线索或数据补齐任务。
- `data_gate_status=WARN`：可进入验证队列，但必须显示待补证据。
- `data_gate_status=PASS`：行情、结构化数据、基本面和证据覆盖达到当前系统要求。
- mock/fallback 行情、mock 基本面、个股新闻/公告证据缺失都会降低 readiness；不能被前端展示为正式通过。

Point-in-time 约束：

- 行情只使用 `trade_date <= as_of_date`。
- 财务只使用 `report_date <= as_of_date`。
- 新闻、公告和 RSS 只使用 `published_at <= as_of_date`。
- 回测入场价使用信号日后的下一根同 source K 线，避免信号日收盘后不可得价格造成偏差。

## Backfill Manifest

全市场行情回填脚本 `backend/scripts/backfill_all_market_data.py` 默认写入 `backend/data/backfill/market_data_backfill_manifest.json`。该 manifest 是轻量状态摘要，用于审计和恢复：

- `database`: 实际数据库 URL 与 SQLite 文件路径。
- `coverage`: 按市场统计 eligible、covered、partial、empty symbols、覆盖率、日期范围和完整覆盖阈值。
- `batches`: 按状态汇总 `data_ingestion_batch`，并保留最近批次。
- `data_sources`: 日线表中实际来源和最近 `data_source_run`。
- `totals`: 本次或累计回填的批次、插入、更新、失败与处理 symbol 数。
- `resume`: 每个 symbol 的尝试次数；脚本重跑时会读取该字段并跳过超过 `--max-attempts-per-symbol` 的标的。

推荐按小批次持续运行，可用 `--max-batches` 限制单次耗时。中断后使用同一个 `--status-path` 重跑即可延续 attempts 与统计。

## Ingestion Plan

`/api/market/ingestion-plan` 用于真实数据接入前的分批计划：

- 显示当前数据源模式、启用市场、每市场批量上限和日线周期数。
- 按市场给出下一批建议数量和当前覆盖率。
- 生成可执行命令，例如：

```bash
MOCK_DATA=false MARKET_DATA_SOURCE=auto ALLOW_MOCK_FALLBACK=false ENABLED_MARKETS=A python scripts/run_daily_pipeline.py --markets A --max-stocks-per-market 50 --periods 320
```

原则：先单市场小批次运行，每批之后必须检查 `/api/market/data-quality`。质量门 `FAIL` 时，不扩大抓取范围；`real_coverage_ratio` 未达标时，即使 mock/fallback 覆盖率很高，也不能扩大真实研究范围。

## Backfill Observability

前端 Dashboard 使用以下接口拼出全市场回填状态：

- `/api/market/data-status`: 覆盖率、最近 `data_source_run`、实际使用源和行数。
- `/api/market/data-quality`: 覆盖率、历史长度和异常质量门。
- `/api/market/ingestion-plan`: 下一批建议数量、批量上限和推荐命令。
- `/api/market/ingestion-tasks`: 队列任务状态、requested / processed / failed。
- `/api/market/ingestion-batches`: 最近批次处理进度和失败数。

这些接口是增量可用的。后端暂未返回某个字段或接口失败时，前端必须优雅降级为空态或 `-`，不能阻塞 Dashboard 主数据加载。

回填运行原则：

- 查看：运行 `./scripts/status_alpha_radar.sh`，或打开 Dashboard 的“数据源状态”“全市场回填进度”“真实数据分批接入计划”。
- 停止：前台回填用 `Ctrl-C`；本地服务用 `.runtime/backend.pid` 和 `.runtime/frontend.pid` 停止进程。停止进程不删除已入库数据。
- 恢复：重新运行推荐的小批次命令或继续消费队列；恢复后先检查质量门，不直接扩大到全市场全量。

全量下载不能设计成阻塞式一次完成。真实数据源会受到频率限制、网络波动、端点 schema 变化、单市场覆盖差异和局部脏数据影响；一次性长事务会放大失败重跑成本，也会让用户无法判断当前卡在下载、清洗、写入还是质量检查。回填必须以小批次、可中断、可恢复、可观测的方式推进。

## Industry Heat Evidence

产业雷达的综合热度不再只依赖资讯：

- `news_heat_score`: 由 RSS/新闻/公告等资讯匹配关键词得到。
- `structure_heat_score`: 由行业内股票数量、已评分股票数量、观察池数量、均线多头占比、突破数量、平均趋势分、平均综合分和量能放大计算。
- `heat_score`: 资讯热度与市场结构热度的组合分。市场筛选为 A/HK/US 时，只使用该市场内映射股票的结构证据。
- `evidence_status`: `news_active` / `structure_active` / `mapped_only` / `no_evidence`。

全市场行业映射按证据强度分层：

1. 免费行业成分源：A 股优先使用新浪行业板块成分，写入 `sector_industry_mapping_v1` metadata。
2. 代码/名称/概念规则：适用于 A/HK/US，写入 `industry_mapping_v1` metadata。
3. 保守名称模式：只在仍未分类时使用明确行业词，低置信度落位，不覆盖已有强分类。

不允许用“科技控股”这类泛词强行归类。免费源没有稳定行业字段的股票可以继续保留 `未分类`，但不能让 `未分类` 的大样本数量压低已分类行业的热度分。
