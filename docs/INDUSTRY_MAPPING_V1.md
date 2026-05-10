# Industry Mapping V1

行业映射 v1 是规则闭环：用行业关键词、股票名称、`concepts`、`industry_level2` 把空行业或“未分类”股票映射到现有 44 个行业主题。

## 边界

- 只填补 `industry_level1` 为空、`未分类`、`未知`、`未知行业` 的股票。
- 已有强分类不会被覆盖。
- 置信度、原因、命中关键词和命中字段写入 `stock.metadata_json.industry_mapping_v1`。
- 不改 DB schema、DB session 迁移和回填队列。

## 运行

```bash
cd backend
python scripts/run_industry_mapping.py --markets A,US,HK
```

先看结果但不落库：

```bash
python scripts/run_industry_mapping.py --markets A --dry-run
```

## 查看摘要

```text
GET /api/industries/mapping-summary
GET /api/industries/mapping-summary?market=A
```

摘要包含股票总数、未分类数量、行业分布和最近样本的映射原因。
