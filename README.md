# AlphaRadar

个人投资者的 AI 产业趋势雷达与十倍股早期特征发现系统。

AlphaRadar 不是荐股 App，不输出买入、卖出、目标价或收益承诺。它的目标是把产业信息、公司基础信息、行情趋势、新闻热度、风险信号串成可解释证据链，生成值得进一步研究的赛道和股票观察池。

## MVP 能力

- 全市场分区：A股、美股、港股；A股继续拆分主板、创业板、科创板、北交所。
- 股票基础库默认使用 deterministic mock 数据，支持通过 provider 工厂切换 AKShare，并在真实源失败时自动回退 mock。
- 日 K 数据入库，并计算均线、多头排列、120/250 日新高、相对强度、成交额放大、回撤控制等趋势指标。
- 数据源运行留痕：记录 universe / market data job 的 requested source、effective source、市场范围、行数、状态和错误。
- 产业关键词库与产业热度计算。
- 行业映射 v1：用行业关键词、股票名称、concepts、industry_level2 为未分类股票补齐 44 个行业主题，并保留置信度和原因。
- Tenbagger Early Signal Score：产业趋势分、公司质量分、股价趋势分、信息催化分、风险扣分。
- 公司证据链与每日投研简报。
- FastAPI 后端与 Next.js 前端。
- Docker Compose 预留 PostgreSQL、后端、前端一键启动。

## 本地运行

一键恢复本地可用状态。脚本会先运行 daily pipeline，再启动 FastAPI 和 Next.js；前端会通过同源 `/api/*` 代理访问后端，避免浏览器直连 `:8000` 失败：

```bash
./scripts/start_alpha_radar.sh
./scripts/status_alpha_radar.sh
```

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/run_daily_pipeline.py
uvicorn app.main:app --reload
```

真实数据源试运行。先单市场、小批次，不要直接全市场硬拉：

```bash
cd backend
source .venv/bin/activate
pip install -e ".[dev,real-data]"
MOCK_DATA=false MARKET_DATA_SOURCE=auto ALLOW_MOCK_FALLBACK=false ENABLED_MARKETS=A python scripts/run_daily_pipeline.py --markets A --max-stocks-per-market 50 --periods 320
```

`MARKET_DATA_SOURCE=auto` 默认只使用免费源：A 股优先 `tencent/yahoo/baostock/akshare`，港股优先 `tencent/yahoo/akshare`，美股优先 `yahoo/akshare`。生产回填建议设置 `ALLOW_MOCK_FALLBACK=false`，避免把失败兜底数据写入正式数据库；前端 Dashboard 的“数据源状态”会显示实际使用源和覆盖率。

行业映射可单独运行，只填补空行业或“未分类”，不会覆盖已有强分类：

```bash
cd backend
source .venv/bin/activate
python scripts/run_industry_mapping.py --markets A,US,HK
```

映射摘要接口：`/api/industries/mapping-summary`。

Dashboard 的“真实数据分批接入计划”会展示当前批量上限、每个市场下一批数量和推荐命令。每批运行后先看“全市场数据质量门”，`FAIL` 时不要扩大范围。

Dashboard 还会展示“全市场回填进度”：读取 `/api/market/ingestion-tasks`、`/api/market/ingestion-batches`、`/api/market/data-status` 和 `/api/market/data-quality`。这些状态接口缺字段或暂不可用时，前端只降级为空态，不影响核心页面加载。

查看回填状态：

```bash
./scripts/status_alpha_radar.sh
```

停止正在前台执行的回填：在运行 `run_daily_pipeline.py`、`run_report_backfill.py` 或队列消费命令的终端按 `Ctrl-C`。如果是 `start_alpha_radar.sh` 启动的本地服务，只停止服务不会删除已入库数据或已排队任务：

```bash
kill "$(cat .runtime/backend.pid)" 2>/dev/null || true
kill "$(cat .runtime/frontend.pid)" 2>/dev/null || true
```

恢复回填：重新运行小批次命令，或从 Dashboard 推荐命令继续。已入库日线会按 upsert 更新，队列任务可继续通过后端队列接口消费；恢复后先用 `status_alpha_radar.sh` 和 Dashboard 的质量门确认覆盖率、失败数和最近运行源。

全量下载不要阻塞式一次完成。真实行情 provider 有频率限制、网络抖动、交易所覆盖差异和 schema 变化风险；单次全市场硬拉会让失败重试成本、锁等待、内存占用和质量定位成本同时放大。AlphaRadar 的策略是“小批次、可恢复、可观测”：每批写入运行留痕，质量门通过后再扩大市场和批量。

历史日报回放：

```bash
cd backend
source .venv/bin/activate
python scripts/run_report_backfill.py --start-date 2026-05-06 --end-date 2026-05-07 --markets A,US,HK --max-stocks-per-market 50 --periods 320
```

回放会按日期重跑 pipeline 并生成历史日报。前端 `/report` 页面会展示历史日报按钮，可切换查看不同日期，并用于观察池新进、移出、评级变化和评分变化对比。

前端：

```bash
cd frontend
npm install
npm run dev
```

打开：

```text
http://localhost:3000
```

API：

```text
http://localhost:8000/docs
```

## 数据库配置

本地默认 `DATABASE_URL=sqlite:///./alpha_radar.db` 会统一解析到 `backend/data/alpha_radar.db`。这样无论从项目根目录还是 `backend/` 目录启动，都不会生成多个默认 SQLite 文件。显式传入绝对 SQLite 路径时按传入路径使用。

PostgreSQL 使用 SQLAlchemy URL，例如：

```bash
DATABASE_URL=postgresql+psycopg://alpha:alpha@localhost:5432/alpha_radar
DATABASE_POOL_PRE_PING=true
```

应用启动时会先执行 SQLAlchemy metadata 建表，再写入轻量 `schema_migration` 版本表。`/health` 会返回 `database_dialect`、`database_path`、`schema_version`、`schema_expected_version` 和 `schema_current`，用于确认当前运行实例连接的是哪个数据库以及 schema 是否已到当前版本。

## Docker

```bash
docker compose up --build
```

## 核心边界

系统输出是研究辅助，不是投资建议。所有页面和报告使用“观察池、趋势强度、产业热度、证据链、风险提示、待验证事项”等措辞。
