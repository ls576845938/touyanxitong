# Pipeline Design

第一版命令：

```bash
python backend/scripts/run_daily_pipeline.py
```

执行顺序：

1. `run_stock_universe_job`
2. `run_market_data_job`
3. `run_news_ingestion_job`
4. `run_industry_heat_job`
5. `run_trend_signal_job`
6. `run_tenbagger_score_job`
7. `run_evidence_chain_job`
8. `run_daily_report_job`

所有 job 都应可重复运行。相同日期、相同股票、相同来源的数据使用 upsert 语义，避免重复生成。
