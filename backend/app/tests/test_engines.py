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
from app.engines.evidence_chain_engine import build_evidence_chain
from app.engines.industry_heat_engine import calculate_industry_heat
from app.engines.industry_mapping_engine import build_mapping_rules, map_stock_industry
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
