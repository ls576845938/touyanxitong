from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Industry, Stock
from app.engines.industry_mapping_engine import build_mapping_rules, map_stock_industry
from app.pipeline.industry_mapping_job import run_industry_mapping_job


EXPANDED_INDUSTRIES = (
    "AI算力",
    "半导体",
    "互联网平台",
    "软件服务",
    "创新药",
    "医疗器械",
    "银行",
    "保险",
    "券商",
    "白酒",
    "食品饮料",
    "家电",
    "物流快递",
    "航运港口",
    "煤炭",
    "油气",
    "有色金属",
    "黄金",
    "电力电网",
    "核电",
    "工程机械",
    "军工信息化",
    "消费电子",
    "新能源车",
)


def _rules():
    return build_mapping_rules({industry: [] for industry in EXPANDED_INDUSTRIES})


def _sample_stock(
    code: str,
    name: str,
    *,
    market: str = "A",
    industry_level1: str = "未分类",
    industry_level2: str = "",
    concepts: list[str] | None = None,
):
    return SimpleNamespace(
        code=code,
        symbol=code,
        name=name,
        market=market,
        industry_level1=industry_level1,
        industry_level2=industry_level2,
        concepts=json.dumps(concepts or [], ensure_ascii=False),
    )


@pytest.mark.parametrize(
    ("code", "name", "expected"),
    [
        ("600519", "贵州茅台", "白酒"),
        ("600036", "招商银行", "银行"),
        ("688981", "中芯国际", "半导体"),
        ("600900", "长江电力", "电力电网"),
        ("601088", "中国神华", "煤炭"),
        ("600031", "三一重工", "工程机械"),
    ],
)
def test_large_cap_a_share_name_and_code_hints_map_common_industries(code: str, name: str, expected: str) -> None:
    match = map_stock_industry(_sample_stock(code, name), _rules())

    assert match is not None
    assert match.industry == expected
    assert match.confidence >= 0.5
    assert match.matched_keywords
    assert {item["field"] for item in match.evidence} & {"code", "name"}


@pytest.mark.parametrize(
    ("code", "name", "expected"),
    [
        ("NVDA", "NVIDIA Corporation", "AI算力"),
        ("JPM", "JPMorgan Chase & Co.", "银行"),
        ("XOM", "Exxon Mobil Corporation", "油气"),
        ("MSFT", "Microsoft Corporation", "软件服务"),
        ("AAPL", "Apple Inc.", "消费电子"),
        ("CAT", "Caterpillar Inc.", "工程机械"),
    ],
)
def test_english_us_stock_names_and_symbols_map_to_expected_industries(code: str, name: str, expected: str) -> None:
    stock = _sample_stock(code, name, market="US")

    match = map_stock_industry(stock, _rules())

    assert match is not None
    assert match.industry == expected
    assert any(item["field"] == "code" for item in match.evidence)


def test_generic_name_words_do_not_overmap_to_software_service() -> None:
    rules = build_mapping_rules({"软件服务": ["软件", "科技", "云服务"], "互联网平台": ["平台"]})
    generic_name = _sample_stock("GENERIC", "未来科技控股", market="HK")
    stronger_field = _sample_stock("SOFT1", "样本公司", industry_level2="企业软件")

    assert map_stock_industry(generic_name, rules) is None

    match = map_stock_industry(stronger_field, rules)
    assert match is not None
    assert match.industry == "软件服务"
    assert any(item["field"] == "industry_level2" for item in match.evidence)


def test_existing_strong_industry_is_not_overridden_by_expanded_hints() -> None:
    stock = _sample_stock("TSLA", "Tesla Inc.", market="US", industry_level1="汽车零部件")

    assert map_stock_industry(stock, _rules()) is None


def test_batch_job_maps_most_unclassified_cross_market_samples_and_preserves_metadata() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    samples = [
        ("600519", "贵州茅台", "A", "SSE"),
        ("600036", "招商银行", "A", "SSE"),
        ("688981", "中芯国际", "A", "SSE"),
        ("NVDA", "NVIDIA Corporation", "US", "NASDAQ"),
        ("MSFT", "Microsoft Corporation", "US", "NASDAQ"),
        ("AAPL", "Apple Inc.", "US", "NASDAQ"),
        ("TSLA", "Tesla Inc.", "US", "NASDAQ"),
        ("601088", "中国神华", "A", "SSE"),
        ("XOM", "Exxon Mobil Corporation", "US", "NYSE"),
        ("300760", "迈瑞医疗", "A", "SZSE"),
        ("601919", "中远海控", "A", "SSE"),
        ("CAT", "Caterpillar Inc.", "US", "NYSE"),
        ("GENERIC", "未来科技控股", "HK", "HKEX"),
    ]

    with Session() as session:
        session.add_all(Industry(name=industry, description="") for industry in EXPANDED_INDUSTRIES)
        session.add_all(
            [
                Stock(
                    code=code,
                    name=name,
                    market=market,
                    board="main",
                    exchange=exchange,
                    industry_level1="未分类",
                    industry_level2="",
                    concepts="[]",
                    asset_type="equity",
                    listing_status="listed",
                    is_active=True,
                )
                for code, name, market, exchange in samples
            ]
        )
        session.add(
            Stock(
                code="KEEP",
                name="NVIDIA Corporation",
                market="US",
                board="nasdaq",
                exchange="NASDAQ",
                industry_level1="半导体",
                industry_level2="",
                concepts="[]",
                asset_type="equity",
                listing_status="listed",
                is_active=True,
            )
        )
        session.commit()

        result = run_industry_mapping_job(session)
        stocks = {stock.code: stock for stock in session.scalars(select(Stock)).all()}

        assert result["mapped"] >= 12
        assert result["unmapped"] == 1
        assert result["skipped_strong"] == 1
        assert stocks["GENERIC"].industry_level1 == "未分类"
        assert stocks["KEEP"].industry_level1 == "半导体"
        assert stocks["NVDA"].industry_level1 == "AI算力"
        assert stocks["MSFT"].industry_level1 == "软件服务"
        assert stocks["XOM"].industry_level1 == "油气"

        metadata = json.loads(stocks["NVDA"].metadata_json)["industry_mapping_v1"]
        assert metadata["version"] == "industry_mapping_v1"
        assert metadata["confidence"] >= 0.5
        assert metadata["reason"]
        assert metadata["matched_keywords"]
        assert metadata["evidence"]
