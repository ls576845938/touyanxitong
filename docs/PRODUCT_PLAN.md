# Product Plan

AlphaRadar 的第一阶段是端到端 MVP：每天自动生成产业雷达、趋势股票池、单股证据链和每日投研简报。

## 非目标

- 不做荐股。
- 不预测明日涨跌。
- 不输出目标价。
- 不承诺十倍股。
- 第一版不做交易下单、组合管理或实盘接入。

## 第一版验收

- `python backend/scripts/run_daily_pipeline.py` 能完整运行。
- 后端 FastAPI 可启动。
- 数据库可初始化。
- 前端可展示 Dashboard、Industry Radar、Trend Pool、Stock Evidence、Daily Report。
- 所有分数都有解释。
- 所有结论保留来源和生成时间。
