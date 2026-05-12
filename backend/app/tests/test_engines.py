from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from types import SimpleNamespace

from app.data_sources.akshare_client import _infer_us_asset_type
from app.data_sources.mock_data import MockMarketDataClient
from app.data_sources.news_client import RssNewsClient
from app.data_sources.tencent_client import _normalize_tencent_rows, _to_tencent_symbol
from app.engines.data_quality_engine import StockDataProfile, assess_market_data_quality
from app.engines.backtest_engine import run_signal_backtest
from app.engines.data_gate_engine import ResearchDataGate, assess_research_data_gate
from app.engines.evidence_chain_engine import build_evidence_chain
from app.engines.industry_heat_engine import calculate_industry_heat
from app.engines.industry_mapping_engine import build_mapping_rules, map_stock_industry
from app.engines.retail_research_engine import (
    RetailStockEvidenceMapping,
    RetailStockPoolCandidate,
    RetailTradeReviewInput,
    analyze_portfolio_exposure,
    attribute_trade_reviews,
    extract_evidence_events,
    map_evidence_events_to_stocks,
    score_stock_pool_candidates,
)
from app.engines.tenbagger_thesis_engine import build_tenbagger_thesis
from app.engines.tenbagger_score_engine import calculate_stock_scores, rating_for_score
from app.engines.trend_engine import calculate_trend_metrics
from app.engines.universe_engine import UniverseProfile, build_research_universe
from app.engines.watchlist_change_engine import build_watchlist_changes


def test_industry_mapping_rules_map_unclassified_stock() -> None:
    stock = SimpleNamespace(
        code="T001",
        name="样本光模块",
        industry_level1="未分类",
        industry_level2="高速光模块",
        concepts=json.dumps(["CPO", "AI算力"], ensure_ascii=False),
    )
    rules = build_mapping_rules({"AI算力": ["光模块", "CPO"], "机器人": ["减速器"]})

    match = map_stock_industry(stock, rules)

    assert match is not None
    assert match.industry == "AI算力"
    assert match.confidence >= 0.5
    assert "光模块" in match.matched_keywords
    assert "置信度" in match.reason


def test_industry_mapping_does_not_override_strong_classification() -> None:
    stock = SimpleNamespace(
        code="T002",
        name="样本光模块",
        industry_level1="半导体",
        industry_level2="高速光模块",
        concepts=json.dumps(["CPO", "AI算力"], ensure_ascii=False),
    )
    rules = build_mapping_rules({"AI算力": ["光模块", "CPO"], "半导体": ["芯片"]})

    assert map_stock_industry(stock, rules) is None


def test_industry_mapping_short_name_hints_require_exact_match() -> None:
    stock = SimpleNamespace(
        code="T003",
        name="京东方A",
        industry_level1="未分类",
        industry_level2="",
        concepts=json.dumps([], ensure_ascii=False),
    )
    rules = build_mapping_rules({"互联网平台": ["电商"]})

    assert map_stock_industry(stock, rules) is None


def test_trend_engine_calculates_explainable_metrics() -> None:
    client = MockMarketDataClient()
    bars_by_stock = {
        "300308": client.fetch_daily_bars("300308", end_date=date(2026, 5, 7)),
        "688235": client.fetch_daily_bars("688235", end_date=date(2026, 5, 7)),
    }

    metrics = calculate_trend_metrics(bars_by_stock)

    assert len(metrics) == 2
    strongest = min(metrics, key=lambda row: row.relative_strength_rank)
    assert strongest.relative_strength_score == 100
    assert 0 <= strongest.trend_score <= 25
    assert "120日相对强度排名" in strongest.explanation


def test_score_engine_keeps_components_explainable() -> None:
    stock = SimpleNamespace(
        code="300308",
        name="中际旭创",
        industry_level1="AI算力",
        market_cap=1900,
        float_market_cap=1700,
        listing_date=date(2012, 4, 10),
        is_st=False,
        is_active=True,
    )
    trend = SimpleNamespace(
        stock_code="300308",
        trend_score=20.0,
        max_drawdown_60d=-0.04,
        volume_expansion_ratio=1.6,
    )
    heat = SimpleNamespace(heat_score=28.0)
    article = SimpleNamespace(title="AI算力订单延续增长")
    fundamental = SimpleNamespace(
        revenue_growth_yoy=34.0,
        profit_growth_yoy=31.0,
        gross_margin=0.42,
        roe=0.2,
        debt_ratio=0.35,
        cashflow_quality=1.25,
    )

    scores = calculate_stock_scores(
        [stock],
        {"300308": trend},
        {"AI算力": heat},
        {"300308": [article, article, article]},
        date(2026, 5, 7),
        {"300308": fundamental},
    )

    assert scores[0].final_score > 70
    assert scores[0].rating in {"观察", "强观察"}
    assert "产业趋势分" in scores[0].explanation
    assert scores[0].source_confidence == 0.8
    assert scores[0].data_confidence == 1.0
    assert scores[0].fundamental_confidence >= 0.6
    assert scores[0].news_confidence == 1.0
    assert scores[0].evidence_confidence == 1.0
    assert "营收同比34.0%" in scores[0].explanation
    assert rating_for_score(39) == "排除"


def test_score_engine_downweights_low_confidence_evidence() -> None:
    stock = SimpleNamespace(
        code="LOW",
        name="低证据样本",
        industry_level1="未知行业",
        market_cap=0,
        float_market_cap=0,
        listing_date=None,
        is_st=False,
        is_active=True,
    )

    scores = calculate_stock_scores([stock], {}, {}, {}, date(2026, 5, 7))

    score = scores[0]
    assert score.raw_score < 0
    assert score.final_score == 0
    assert score.data_confidence < 0.5
    assert score.source_confidence < 0.5
    assert score.fundamental_confidence < 0.5
    assert score.news_confidence == 0
    assert score.evidence_confidence == 0
    assert score.confidence_level == "insufficient"
    assert score.rating in {"仅记录", "排除"}
    assert "当前证据不足，不能形成有效观察结论" in score.explanation
    assert {"行情趋势数据不足", "基本面数据缺失", "所属行业热度证据缺失", "个股资讯证据不足"}.issubset(set(score.confidence_reasons))


def test_formal_data_gate_blocks_mock_like_low_confidence_rows() -> None:
    stock = SimpleNamespace(code="MOCK", name="Mock", asset_type="equity", is_st=False, is_active=True)
    score = SimpleNamespace(
        source_confidence=0.1,
        data_confidence=0.4,
        fundamental_confidence=0.0,
        news_confidence=0.0,
        evidence_confidence=0.0,
    )

    gate = assess_research_data_gate(stock=stock, score=score, fundamental=None)

    assert gate.status == "FAIL"
    assert gate.score < 60
    assert any("mock/fallback" in action for action in gate.required_actions)


def test_tenbagger_thesis_identifies_missing_evidence_and_stage() -> None:
    stock = SimpleNamespace(
        code="300308",
        name="中际旭创",
        asset_type="equity",
        industry_level1="AI算力",
        market_cap=600,
        float_market_cap=520,
        is_st=False,
        is_active=True,
    )
    score = SimpleNamespace(
        stock_code="300308",
        final_score=82,
        trend_score=21,
        risk_penalty=0.5,
        source_confidence=0.92,
        data_confidence=0.9,
        fundamental_confidence=1.0,
        news_confidence=1.0,
        evidence_confidence=1.0,
    )
    trend = SimpleNamespace(
        is_breakout_250d=True,
        is_breakout_120d=True,
        is_ma_bullish=True,
        volume_expansion_ratio=1.6,
        max_drawdown_60d=-0.05,
    )
    heat = SimpleNamespace(heat_score=27)
    article = SimpleNamespace(title="光模块订单增长", source_url="https://example.com", source="rss", source_kind="rss")
    fundamental = SimpleNamespace(
        revenue_growth_yoy=38.0,
        profit_growth_yoy=45.0,
        gross_margin=0.43,
        roe=0.21,
        debt_ratio=0.32,
        cashflow_quality=1.2,
        report_title="2026Q1",
        source_url="https://example.com/report",
        source="fixture",
    )

    thesis = build_tenbagger_thesis(
        stock=stock,
        score=score,
        trend_signal=trend,
        industry_heat=heat,
        articles=[article, article],
        trade_date=date(2026, 5, 7),
        fundamental=fundamental,
    )

    assert thesis.thesis_score >= 70
    assert thesis.stage in {"verification", "candidate"}
    assert thesis.data_gate_status == "PASS"
    assert thesis.logic_gate_status in {"PASS", "WARN"}
    assert thesis.logic_gates
    assert thesis.alternative_data_signals
    assert thesis.valuation_simulation["valuation_ceiling_status"] in {"room", "balanced", "stretched", "insufficient"}
    assert thesis.contrarian_signal["label"] in {"cold_asset_reversal_watch", "hot_momentum", "neutral"}
    assert thesis.anti_thesis_score >= 0
    assert thesis.sniper_focus
    assert "估值" in " ".join(thesis.missing_evidence)
    assert thesis.source_refs
    assert "十倍股假设分" in thesis.explanation
    assert "逻辑门控" in thesis.explanation


def test_tenbagger_thesis_builds_contrarian_logic_and_tam_ceiling() -> None:
    stock = SimpleNamespace(
        code="COLD",
        name="冷资产样本",
        asset_type="equity",
        industry_level1="AI算力",
        market_cap=520,
        float_market_cap=430,
        is_st=False,
        is_active=True,
    )
    score = SimpleNamespace(
        stock_code="COLD",
        final_score=78,
        trend_score=11,
        risk_penalty=0.4,
        source_confidence=0.93,
        data_confidence=0.92,
        fundamental_confidence=1.0,
        news_confidence=0.9,
        evidence_confidence=0.9,
    )
    trend = SimpleNamespace(
        is_breakout_250d=False,
        is_breakout_120d=False,
        is_ma_bullish=False,
        volume_expansion_ratio=0.9,
        max_drawdown_60d=-0.12,
    )
    heat = SimpleNamespace(heat_score=22, heat_change_7d=-8.0, heat_change_30d=-10.0)
    article = SimpleNamespace(
        title="AI算力订单增长，客户交付与产能扩张继续验证",
        summary="光模块和CPO链路出现供应链份额提升迹象",
        source_url="https://example.com/cold",
        source="rss",
        source_kind="rss",
    )
    fundamental = SimpleNamespace(
        revenue_growth_yoy=42.0,
        profit_growth_yoy=48.0,
        gross_margin=0.46,
        roe=0.23,
        debt_ratio=0.3,
        cashflow_quality=1.18,
        report_title="2026Q1",
        source_url="https://example.com/report",
        source="fixture",
    )

    thesis = build_tenbagger_thesis(
        stock=stock,
        score=score,
        trend_signal=trend,
        industry_heat=heat,
        articles=[article],
        trade_date=date(2026, 5, 7),
        fundamental=fundamental,
    )

    assert thesis.contrarian_signal["reversal_watch"] is True
    assert thesis.contrarian_signal["label"] == "cold_asset_reversal_watch"
    assert thesis.valuation_simulation["tam_assumptions"]["penetration_stage"] in {"0_to_1_validation", "1_to_10_acceleration"}
    assert thesis.valuation_simulation["scenarios"]
    assert any(signal["id"] == "order_yield" for signal in thesis.alternative_data_signals)
    assert all("买入" not in item for item in thesis.sniper_focus)


def test_signal_backtest_uses_next_bar_and_groups_results() -> None:
    score = SimpleNamespace(
        stock_code="AAA",
        trade_date=date(2026, 1, 2),
        final_score=72,
        rating="观察",
        confidence_level="high",
    )
    bars = [
        SimpleNamespace(trade_date=date(2026, 1, 2), close=10),
        SimpleNamespace(trade_date=date(2026, 1, 3), close=11),
        SimpleNamespace(trade_date=date(2026, 1, 4), close=13),
        SimpleNamespace(trade_date=date(2026, 1, 5), close=22),
    ]

    result = run_signal_backtest(
        score_rows=[score],
        bars_by_stock={"AAA": bars},
        as_of_date=date(2026, 1, 5),
        horizon_days=2,
        min_score=55,
    )

    assert result.sample_count == 1
    assert result.average_forward_return == 1.0
    assert result.hit_rate_2x == 1.0
    assert result.bucket_summary[0]["bucket"] == "70-84"


def test_industry_heat_returns_zero_rows_with_reasons() -> None:
    industries = [
        SimpleNamespace(id=1, name="AI算力"),
        SimpleNamespace(id=2, name="无关键词行业"),
        SimpleNamespace(id=3, name="无资讯行业"),
    ]
    keywords = {
        1: [SimpleNamespace(keyword="AI算力", weight=1.0)],
        3: [SimpleNamespace(keyword="冷门", weight=1.0)],
    }
    article = SimpleNamespace(
        title="AI算力订单延续增长",
        matched_keywords=json.dumps(["AI算力"], ensure_ascii=False),
        published_at=date(2026, 5, 7),
    )

    rows = calculate_industry_heat(industries, keywords, [article], date(2026, 5, 7))

    assert len(rows) == 3
    zero_by_id = {row.industry_id: row for row in rows if row.heat_score == 0}
    assert {2, 3}.issubset(zero_by_id)
    assert "热度为0" in zero_by_id[2].explanation
    assert "热度为0" in zero_by_id[3].explanation


def test_industry_heat_downweights_mock_only_coverage() -> None:
    industries = [SimpleNamespace(id=1, name="AI算力")]
    keywords = {1: [SimpleNamespace(keyword="AI算力", weight=1.0)]}
    article = SimpleNamespace(
        title="AI算力订单延续增长",
        matched_keywords=json.dumps(["AI算力"], ensure_ascii=False),
        published_at=date(2026, 5, 7),
        source="mock",
        source_kind="mock",
        source_confidence=0.3,
    )

    rows = calculate_industry_heat(industries, keywords, [article], date(2026, 5, 7))

    assert rows[0].heat_7d < 1.0
    assert "资讯覆盖不足" in rows[0].explanation
    assert "mock:1" in rows[0].explanation


def test_rss_news_client_normalizes_source_metadata() -> None:
    item = RssNewsClient([])._normalize_item(
        ET.fromstring(
            """
            <item>
              <title>AI算力与光模块需求提升</title>
              <description>CPO产业链关注度上升</description>
              <link>https://example.com/a</link>
              <pubDate>Thu, 07 May 2026 09:00:00 GMT</pubDate>
            </item>
            """
        ),
        "https://example.com/rss.xml",
        "Example RSS",
    )

    assert item is not None
    assert item["source_kind"] == "rss"
    assert item["source_confidence"] == 0.8
    assert "AI算力" in json.loads(item["matched_keywords"])


def test_evidence_chain_uses_safe_research_wording() -> None:
    stock = SimpleNamespace(
        code="300308",
        name="中际旭创",
        industry_level1="AI算力",
        industry_level2="光模块",
    )
    score = SimpleNamespace(rating="观察", explanation="评分解释")
    trend = SimpleNamespace(explanation="均线多头排列")
    heat = SimpleNamespace(explanation="光模块热度上升")
    article = SimpleNamespace(
        title="光模块产业链关注度提升",
        source_url="mock://article/1",
        source="mock",
        source_kind="mock",
        source_confidence=0.3,
    )
    fundamental = SimpleNamespace(
        period="2026Q1",
        report_date=date(2026, 3, 31),
        revenue_growth_yoy=34.0,
        profit_growth_yoy=31.0,
        gross_margin=0.42,
        roe=0.2,
        debt_ratio=0.35,
        cashflow_quality=1.25,
        source="mock",
        source_url="mock://fundamental/300308/2026-03-31",
        report_title="中际旭创 2026Q1 mock 财务快照",
    )

    evidence = build_evidence_chain(stock, score, trend, heat, [article], date(2026, 5, 7), fundamental)

    payload = json.dumps(evidence.__dict__, ensure_ascii=False, default=str)
    assert "观察" in evidence.summary
    assert "买入" not in payload
    assert "卖出" not in payload
    assert "目标价" not in payload
    assert "营收同比34.0%" in evidence.company_logic
    assert evidence.questions_to_verify
    assert evidence.source_refs[0]["source_kind"] == "mock"
    assert any(ref["source_kind"] == "fundamental" for ref in evidence.source_refs)


def test_data_quality_engine_flags_unusable_history_and_bad_ohlc() -> None:
    good_bars = MockMarketDataClient().fetch_daily_bars("300308", end_date=date(2026, 5, 7), periods=260)
    bad_bars = [
        {
            "trade_date": date(2026, 5, 7),
            "open": 10,
            "high": 9,
            "low": 8,
            "close": 11,
            "volume": 0,
            "amount": 0,
            "source": "mock",
        }
    ]

    result = assess_market_data_quality(
        [
            StockDataProfile(code="300308", name="中际旭创", market="A", board="chinext", bars=good_bars),
            StockDataProfile(code="BROKEN", name="异常样本", market="A", board="chinext", bars=bad_bars),
        ]
    )

    assert result["status"] == "FAIL"
    assert result["summary"]["fail_count"] >= 1
    assert {item["issue_type"] for item in result["issues"]} >= {"insufficient_history", "bad_ohlc"}


def _research_grade_bars(source: str, count: int = 160) -> list[dict[str, object]]:
    return [
        {
            "trade_date": date(2025, 1, 1) + timedelta(days=idx),
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10,
            "volume": 1_000_000,
            "amount": 50_000_000,
            "source": source,
        }
        for idx in range(count)
    ]


def test_universe_engine_excludes_unresearchable_stocks() -> None:
    bars = _research_grade_bars("akshare", 260)
    result = build_research_universe(
        [
            UniverseProfile(
                code="300308",
                name="中际旭创",
                market="A",
                board="chinext",
                is_active=True,
                is_st=False,
                market_cap=1900,
                float_market_cap=1700,
                bars=bars,
                source="akshare",
                data_vendor="akshare",
            ),
            UniverseProfile(
                code="BAD",
                name="不可研究样本",
                market="A",
                board="main",
                is_active=True,
                is_st=True,
                market_cap=10,
                float_market_cap=8,
                bars=bars[:20],
            ),
        ]
    )

    assert result["summary"]["eligible_count"] == 1
    excluded = next(row for row in result["rows"] if row["code"] == "BAD")
    assert not excluded["eligible"]
    assert {"st_or_special_treatment", "insufficient_history", "market_cap_too_small"}.issubset(set(excluded["exclusion_reasons"]))
    assert result["exclusion_summary"]["insufficient_history"] >= 1
    assert next(item for item in result["segments"] if item["board"] == "main")["exclusion_reasons"]["st_or_special_treatment"] == 1


def test_universe_engine_rejects_mock_and_fallback_daily_bars_for_research_eligibility() -> None:
    result = build_research_universe(
        [
            UniverseProfile(
                code="MOCK_ONLY",
                name="Mock 行情样本",
                market="A",
                board="main",
                is_active=True,
                is_st=False,
                market_cap=500,
                float_market_cap=300,
                bars=_research_grade_bars("mock"),
                source="mock",
                data_vendor="mock",
            ),
            UniverseProfile(
                code="FALLBACK_ONLY",
                name="Fallback 行情样本",
                market="A",
                board="main",
                is_active=True,
                is_st=False,
                market_cap=500,
                float_market_cap=300,
                bars=_research_grade_bars("mock_fallback"),
                source="tencent+mock_fallback",
                data_vendor="tencent+mock_fallback",
            ),
        ]
    )

    rows = {row["code"]: row for row in result["rows"]}
    assert rows["MOCK_ONLY"]["eligible"] is False
    assert rows["FALLBACK_ONLY"]["eligible"] is False
    assert "untrusted_data_source" in rows["MOCK_ONLY"]["exclusion_reasons"]
    assert "untrusted_data_source" in rows["FALLBACK_ONLY"]["exclusion_reasons"]


def test_universe_engine_accepts_real_tencent_and_akshare_daily_bars() -> None:
    result = build_research_universe(
        [
            UniverseProfile(
                code="TENCENT_REAL",
                name="Tencent 真实行情样本",
                market="A",
                board="main",
                is_active=True,
                is_st=False,
                market_cap=500,
                float_market_cap=300,
                bars=_research_grade_bars("tencent"),
                source="tencent",
                data_vendor="tencent",
            ),
            UniverseProfile(
                code="AKSHARE_REAL",
                name="AKShare 真实行情样本",
                market="A",
                board="main",
                is_active=True,
                is_st=False,
                market_cap=500,
                float_market_cap=300,
                bars=_research_grade_bars("akshare"),
                source="akshare",
                data_vendor="akshare",
            ),
        ]
    )

    rows = {row["code"]: row for row in result["rows"]}
    assert result["summary"]["eligible_count"] == 2
    assert rows["TENCENT_REAL"]["eligible"] is True
    assert rows["AKSHARE_REAL"]["eligible"] is True
    assert rows["TENCENT_REAL"]["selected_bar_source"] == "tencent"
    assert rows["AKSHARE_REAL"]["selected_bar_source"] == "akshare"


def test_universe_engine_requires_trusted_single_source_history() -> None:
    def bars(source: str, count: int) -> list[dict[str, object]]:
        return [
            {
                "trade_date": date(2025, 1, 1).toordinal() + idx,
                "close": 10,
                "volume": 1_000_000,
                "amount": 50_000_000,
                "source": source,
            }
            for idx in range(count)
        ]

    result = build_research_universe(
        [
            UniverseProfile(
                code="MIXED",
                name="混源样本",
                market="A",
                board="main",
                is_active=True,
                is_st=False,
                market_cap=500,
                float_market_cap=300,
                bars=bars("akshare", 80) + bars("tencent", 80),
                source="akshare",
                data_vendor="akshare",
            ),
            UniverseProfile(
                code="UNKNOWN",
                name="未知源样本",
                market="A",
                board="main",
                is_active=True,
                is_st=False,
                market_cap=500,
                float_market_cap=300,
                bars=bars("unknown_vendor", 160),
                source="unknown_vendor",
                data_vendor="unknown_vendor",
            ),
        ]
    )

    mixed = next(row for row in result["rows"] if row["code"] == "MIXED")
    unknown = next(row for row in result["rows"] if row["code"] == "UNKNOWN")
    assert not mixed["eligible"]
    assert mixed["bars_count"] == 80
    assert mixed["source_profile"]["mixed_sources"] is True
    assert "insufficient_history" in mixed["exclusion_reasons"]
    assert not unknown["eligible"]
    assert "untrusted_data_source" in unknown["exclusion_reasons"]


def test_watchlist_change_engine_tracks_new_removed_and_rating_changes() -> None:
    stock_a = SimpleNamespace(code="AAA", name="样本A", market="A", board="main", industry_level1="AI算力")
    stock_b = SimpleNamespace(code="BBB", name="样本B", market="A", board="main", industry_level1="机器人")
    stock_c = SimpleNamespace(code="CCC", name="样本C", market="US", board="nasdaq", industry_level1="AI算力")
    latest = [
        SimpleNamespace(stock_code="AAA", rating="强观察", final_score=86),
        SimpleNamespace(stock_code="BBB", rating="仅记录", final_score=45),
        SimpleNamespace(stock_code="CCC", rating="观察", final_score=73),
    ]
    previous = [
        SimpleNamespace(stock_code="AAA", rating="观察", final_score=72),
        SimpleNamespace(stock_code="BBB", rating="观察", final_score=71),
    ]

    result = build_watchlist_changes(
        latest_date=date(2026, 5, 7),
        previous_date=date(2026, 5, 6),
        latest_scores=latest,
        previous_scores=previous,
        stocks_by_code={"AAA": stock_a, "BBB": stock_b, "CCC": stock_c},
    )

    assert result["summary"]["new_count"] == 1
    assert result["summary"]["removed_count"] == 1
    assert result["summary"]["upgraded_count"] == 1
    assert result["new_entries"][0]["code"] == "CCC"
    assert result["removed_entries"][0]["code"] == "BBB"
    assert result["upgraded"][0]["code"] == "AAA"


def test_tencent_client_normalizes_a_and_hk_daily_rows() -> None:
    assert _to_tencent_symbol("00700.HK", "HK") == "hk00700"
    assert _to_tencent_symbol("600519", "A") == "sh600519"
    assert _to_tencent_symbol("000333", "A") == "sz000333"
    rows = _normalize_tencent_rows(
        [
            ["2026-05-06", "470.600", "463.000", "473.400", "460.200", "44367227.000"],
            ["2026-05-07", "472.200", "477.400", "481.000", "471.000", "20000000.000"],
        ],
        "00700.HK",
        end_date=date(2026, 5, 8),
        periods=320,
    )
    assert len(rows) == 2
    assert rows[0]["source"] == "tencent"
    assert rows[0]["trade_date"] == date(2026, 5, 6)
    assert rows[1]["pre_close"] == rows[0]["close"]
    assert rows[1]["pct_chg"] != 0


def test_akshare_us_asset_classifier_filters_non_common_codes() -> None:
    assert _infer_us_asset_type("AAPL", "AAPL", "Apple Inc.") == "equity"
    assert _infer_us_asset_type("105.AAPL22", "105.AAPL22", "Apple structured row") == "other"
    assert _infer_us_asset_type("106.BRK_A", "BRK_A", "Berkshire class encoded row") == "other"
    assert _infer_us_asset_type("SPY", "SPY", "SPDR S&P 500 ETF Trust") == "etf"


def test_retail_research_extracts_and_maps_ai_compute_evidence() -> None:
    stock = SimpleNamespace(
        code="300308",
        name="中际旭创",
        industry_level1="AI算力",
        industry_level2="光模块",
        concepts=json.dumps(["光模块", "CPO", "AI算力"], ensure_ascii=False),
    )
    rules = build_mapping_rules({"AI算力": ["AI算力", "光模块", "CPO"]})
    rows = [
        SimpleNamespace(
            title="光模块订单增长，AI服务器需求继续扩张",
            summary="中际旭创与 CPO 环节订单延续增长",
            source="Fixture RSS",
            source_kind="rss",
            source_confidence=0.9,
            source_url="https://example.com/news/ai-1",
            published_at=date(2026, 5, 7),
            matched_keywords=json.dumps(["AI算力", "光模块", "CPO"], ensure_ascii=False),
            related_industries=json.dumps(["AI算力"], ensure_ascii=False),
            related_stocks=json.dumps(["300308"], ensure_ascii=False),
        ),
        SimpleNamespace(
            title="AI算力 capex discussion keeps optical module demand hot",
            summary="Community thread highlights AI算力 and 光模块 demand",
            source="Reddit",
            source_kind="community",
            source_confidence=0.56,
            source_url="https://reddit.test/r/stocks/ai",
            published_at=date(2026, 5, 7),
            matched_keywords=json.dumps(["AI算力", "光模块"], ensure_ascii=False),
            related_industries="[]",
            related_stocks="[]",
        ),
        SimpleNamespace(
            title="Weekend portfolio chat with no mapped industry signal",
            summary="General discussion without investable keywords",
            source="Reddit",
            source_kind="community",
            source_confidence=0.56,
            source_url="https://reddit.test/r/stocks/noise",
            published_at=date(2026, 5, 7),
            matched_keywords="[]",
            related_industries="[]",
            related_stocks="[]",
        ),
    ]

    events = extract_evidence_events(rows, industry_rules=rules)
    mapping = map_evidence_events_to_stocks(events, [stock], industry_rules=rules)[0]

    assert len(events) == 3
    assert any(event.social_only for event in events)
    assert any("industry" in event.signal_types for event in events if event.title.startswith("AI算力 capex"))
    assert mapping.stock_code == "300308"
    assert mapping.direct_event_count == 1
    assert mapping.industry_event_count >= 2
    assert mapping.evidence_score >= 70
    assert "光模块订单增长" in mapping.company_logic


def test_retail_research_candidate_scoring_applies_formula_and_grade_guards() -> None:
    good_stock = SimpleNamespace(
        code="300308",
        name="中际旭创",
        industry_level1="AI算力",
        market_cap=650,
        float_market_cap=520,
        listing_date=date(2012, 4, 10),
        is_st=False,
        is_active=True,
    )
    fail_stock = SimpleNamespace(
        code="FAIL1",
        name="低质量样本",
        industry_level1="AI算力",
        market_cap=180,
        float_market_cap=90,
        listing_date=date(2024, 1, 1),
        is_st=False,
        is_active=True,
    )
    social_stock = SimpleNamespace(
        code="SOC1",
        name="社媒热词样本",
        industry_level1="未知行业",
        market_cap=220,
        float_market_cap=150,
        listing_date=date(2021, 6, 1),
        is_st=False,
        is_active=True,
    )
    trend = SimpleNamespace(
        stock_code="300308",
        trend_score=21.0,
        explanation="120日相对强度领先，均线多头排列",
        max_drawdown_60d=-0.06,
        volume_expansion_ratio=1.5,
    )
    trend_by_code = {
        "300308": trend,
        "FAIL1": trend,
        "SOC1": SimpleNamespace(stock_code="SOC1", trend_score=18.0, explanation="趋势尚可", max_drawdown_60d=-0.08, volume_expansion_ratio=1.2),
    }
    heat = SimpleNamespace(heat_score=27.0, explanation="AI算力景气扩散，光模块热度提升")
    heat_by_name = {"AI算力": heat}
    good_score = SimpleNamespace(
        evidence_confidence=0.95,
        news_confidence=1.0,
        trend_score=21.0,
        risk_penalty=0.6,
        source_confidence=0.92,
        data_confidence=0.91,
        fundamental_confidence=1.0,
        explanation="公司逻辑完整",
    )
    fail_score = SimpleNamespace(
        evidence_confidence=0.9,
        news_confidence=0.9,
        trend_score=21.0,
        risk_penalty=0.8,
        source_confidence=0.3,
        data_confidence=0.45,
        fundamental_confidence=0.2,
        explanation="数据质量弱",
    )
    social_score = SimpleNamespace(
        evidence_confidence=0.45,
        news_confidence=0.5,
        trend_score=18.0,
        risk_penalty=1.0,
        source_confidence=0.7,
        data_confidence=0.7,
        fundamental_confidence=0.6,
        explanation="只有社媒热词",
    )
    fundamental = SimpleNamespace(
        revenue_growth_yoy=38.0,
        profit_growth_yoy=42.0,
        cashflow_quality=1.2,
        debt_ratio=0.32,
        source="fixture",
    )
    mappings = {
        "300308": RetailStockEvidenceMapping(
            stock_code="300308",
            stock_name="中际旭创",
            industry_name="AI算力",
            event_count=3,
            direct_event_count=2,
            industry_event_count=3,
            social_event_count=1,
            social_only_event_count=0,
            evidence_score=88.0,
            industry_logic="AI服务器需求拉动光模块景气",
            company_logic="订单增长与份额提升",
            trend_logic="放量突破并保持均线多头",
            risk_alert="估值扩张过快需核验",
            falsification_condition="订单未兑现或趋势失守",
            only_social_heat=False,
        ),
        "FAIL1": RetailStockEvidenceMapping(
            stock_code="FAIL1",
            stock_name="低质量样本",
            industry_name="AI算力",
            event_count=2,
            direct_event_count=1,
            industry_event_count=2,
            social_event_count=0,
            social_only_event_count=0,
            evidence_score=85.0,
            industry_logic="行业热度存在",
            company_logic="公司叙事存在",
            trend_logic="趋势存在",
            risk_alert="数据源不足",
            falsification_condition="若证据无法复核则撤销",
            only_social_heat=False,
        ),
        "SOC1": RetailStockEvidenceMapping(
            stock_code="SOC1",
            stock_name="社媒热词样本",
            industry_name="未知行业",
            event_count=2,
            direct_event_count=0,
            industry_event_count=0,
            social_event_count=2,
            social_only_event_count=2,
            evidence_score=55.0,
            industry_logic="",
            company_logic="",
            trend_logic="",
            risk_alert="社媒噪音高",
            falsification_condition="无产业证据则撤销",
            only_social_heat=True,
        ),
    }
    gate_by_code = {
        "300308": ResearchDataGate(status="PASS", score=92.0, reasons=["正式研究数据门通过"], required_actions=[]),
        "FAIL1": ResearchDataGate(status="FAIL", score=48.0, reasons=["行情来源置信度不足"], required_actions=["补齐 real 行情源"]),
        "SOC1": ResearchDataGate(status="WARN", score=76.0, reasons=["只有社媒证据"], required_actions=["补产业证据"]),
    }

    candidates = score_stock_pool_candidates(
        [good_stock, fail_stock, social_stock],
        evidence_mappings_by_code=mappings,
        latest_trend_by_code=trend_by_code,
        latest_heat_by_industry_name=heat_by_name,
        latest_score_by_code={"300308": good_score, "FAIL1": fail_score, "SOC1": social_score},
        latest_fundamental_by_code={"300308": fundamental},
        data_gate_by_code=gate_by_code,
    )
    candidate_by_code = {item.stock_code: item for item in candidates}
    good = candidate_by_code["300308"]
    failed = candidate_by_code["FAIL1"]
    social = candidate_by_code["SOC1"]
    expected = round(
        0.25 * good.evidence_score
        + 0.20 * good.industry_heat_score
        + 0.20 * good.trend_score
        + 0.15 * good.quality_score
        + 0.10 * good.valuation_score
        - 0.10 * good.risk_score,
        2,
    )

    assert good.grade in {"S", "A"}
    assert good.conviction_score == expected
    assert all([good.industry_logic, good.company_logic, good.trend_logic, good.risk_alert, good.falsification_condition])
    assert failed.grade not in {"S", "A"}
    assert failed.data_quality_status == "FAIL"
    assert social.grade == "C"
    assert social.only_social_heat is True


def test_retail_research_exposure_analysis_flags_concentration_and_low_quality() -> None:
    candidates = {
        "A1": RetailStockPoolCandidate(
            stock_code="A1",
            stock_name="AI一号",
            industry_name="AI算力",
            grade="A",
            data_quality_status="PASS",
            conviction_score=78.0,
            evidence_score=80.0,
            industry_heat_score=88.0,
            trend_score=76.0,
            quality_score=85.0,
            valuation_score=68.0,
            risk_score=16.0,
            industry_logic="产业逻辑",
            company_logic="公司逻辑",
            trend_logic="趋势逻辑",
            risk_alert="风险提示",
            falsification_condition="证伪条件",
            only_social_heat=False,
        ),
        "A2": RetailStockPoolCandidate(
            stock_code="A2",
            stock_name="AI二号",
            industry_name="AI算力",
            grade="B",
            data_quality_status="FAIL",
            conviction_score=62.0,
            evidence_score=66.0,
            industry_heat_score=88.0,
            trend_score=60.0,
            quality_score=48.0,
            valuation_score=64.0,
            risk_score=28.0,
            industry_logic="产业逻辑",
            company_logic="公司逻辑",
            trend_logic="趋势逻辑",
            risk_alert="风险提示",
            falsification_condition="证伪条件",
            only_social_heat=False,
        ),
        "S1": RetailStockPoolCandidate(
            stock_code="S1",
            stock_name="社媒一号",
            industry_name="未知行业",
            grade="C",
            data_quality_status="WARN",
            conviction_score=48.0,
            evidence_score=45.0,
            industry_heat_score=20.0,
            trend_score=52.0,
            quality_score=72.0,
            valuation_score=58.0,
            risk_score=25.0,
            industry_logic="",
            company_logic="",
            trend_logic="",
            risk_alert="社媒噪音",
            falsification_condition="无产业证据则撤销",
            only_social_heat=True,
        ),
    }

    exposure = analyze_portfolio_exposure(
        [
            {"stock_code": "A1", "weight": 0.45},
            {"stock_code": "A2", "weight": 0.30},
            {"stock_code": "S1", "weight": 0.25},
        ],
        candidates,
    )

    assert exposure.total_weight == 1.0
    assert exposure.industry_exposure[0]["industry"] == "AI算力"
    assert any("主题集中度偏高" in item for item in exposure.warnings)
    assert any("数据门控 FAIL 暴露" in item for item in exposure.warnings)
    assert any("纯社媒热词暴露" in item for item in exposure.warnings)


def test_retail_research_trade_review_attributes_evidence_break_and_trend_followthrough() -> None:
    entry = RetailStockPoolCandidate(
        stock_code="300308",
        stock_name="中际旭创",
        industry_name="AI算力",
        grade="A",
        data_quality_status="PASS",
        conviction_score=78.0,
        evidence_score=84.0,
        industry_heat_score=86.0,
        trend_score=80.0,
        quality_score=90.0,
        valuation_score=70.0,
        risk_score=18.0,
        industry_logic="产业逻辑",
        company_logic="公司逻辑",
        trend_logic="趋势逻辑",
        risk_alert="风险提示",
        falsification_condition="证伪条件",
        only_social_heat=False,
    )
    exit_loss = RetailStockPoolCandidate(
        stock_code="300308",
        stock_name="中际旭创",
        industry_name="AI算力",
        grade="B",
        data_quality_status="PASS",
        conviction_score=58.0,
        evidence_score=46.0,
        industry_heat_score=60.0,
        trend_score=42.0,
        quality_score=88.0,
        valuation_score=66.0,
        risk_score=34.0,
        industry_logic="产业逻辑",
        company_logic="公司逻辑",
        trend_logic="趋势走弱",
        risk_alert="风险提示",
        falsification_condition="证伪条件",
        only_social_heat=False,
    )
    exit_win = RetailStockPoolCandidate(
        stock_code="300308",
        stock_name="中际旭创",
        industry_name="AI算力",
        grade="S",
        data_quality_status="PASS",
        conviction_score=88.0,
        evidence_score=90.0,
        industry_heat_score=92.0,
        trend_score=91.0,
        quality_score=90.0,
        valuation_score=74.0,
        risk_score=12.0,
        industry_logic="产业逻辑",
        company_logic="公司逻辑",
        trend_logic="趋势强化",
        risk_alert="风险提示",
        falsification_condition="证伪条件",
        only_social_heat=False,
    )

    summary = attribute_trade_reviews(
        [
            RetailTradeReviewInput(
                stock_code="300308",
                stock_name="中际旭创",
                action="buy",
                entry_candidate=entry,
                exit_candidate=exit_loss,
                realized_return=-0.14,
                holding_days=18,
                exit_reason="订单证据走弱后离场",
            ),
            RetailTradeReviewInput(
                stock_code="300308",
                stock_name="中际旭创",
                action="buy",
                entry_candidate=entry,
                exit_candidate=exit_win,
                realized_return=0.22,
                holding_days=26,
                exit_reason="趋势和订单兑现后止盈",
            ),
        ]
    )

    assert len(summary.trades) == 2
    assert summary.trades[0].outcome == "loss"
    assert summary.trades[0].primary_driver in {"evidence_break", "trend_reversal"}
    assert summary.trades[1].primary_driver in {"evidence_validation", "trend_follow_through", "industry_tailwind"}
    assert summary.average_return == 0.04
    assert summary.win_rate == 0.5
