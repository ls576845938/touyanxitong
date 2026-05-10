from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Industry, IndustryHeat, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.main import app


TRADE_DATE = date(2026, 5, 7)


def _client_with_seed(tmp_path, seed):
    db_path = tmp_path / "industry_heat_market_structure.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as session:
        seed(session)
        session.commit()

    def override_session():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def _add_industry(session, name: str) -> Industry:
    industry = Industry(name=name, description="")
    session.add(industry)
    session.flush()
    session.add(
        IndustryHeat(
            industry_id=industry.id,
            trade_date=TRADE_DATE,
            heat_score=0,
            explanation="资讯热度为0：近30日未匹配到有效资讯证据。",
        )
    )
    return industry


def _add_stock(
    session,
    code: str,
    industry: str,
    market: str = "A",
    with_score: bool = False,
    with_trend: bool = False,
    rating: str = "仅记录",
    final_score: float = 70,
    trend_score: float = 16,
    volume_expansion_ratio: float = 1.4,
    breakout: bool = False,
) -> None:
    session.add(
        Stock(
            code=code,
            name=code,
            market=market,
            board="main",
            exchange="SSE" if market == "A" else market,
            industry_level1=industry,
            industry_level2="样本",
            concepts="[]",
            asset_type="equity",
            listing_status="listed",
            is_active=True,
        )
    )
    if with_score:
        session.add(
            StockScore(
                stock_code=code,
                trade_date=TRADE_DATE,
                final_score=final_score,
                trend_score=trend_score,
                rating=rating,
            )
        )
    if with_trend:
        session.add(
            TrendSignal(
                stock_code=code,
                trade_date=TRADE_DATE,
                is_ma_bullish=True,
                is_breakout_120d=breakout,
                is_breakout_250d=False,
                trend_score=trend_score,
                volume_expansion_ratio=volume_expansion_ratio,
            )
        )


def test_radar_heat_score_uses_structure_when_news_is_zero(tmp_path) -> None:
    def seed(session):
        _add_industry(session, "结构趋势行业")
        _add_stock(
            session,
            "STRUCT_A",
            "结构趋势行业",
            with_score=True,
            with_trend=True,
            rating="观察",
            final_score=86,
            trend_score=22,
            volume_expansion_ratio=1.9,
            breakout=True,
        )

    client = _client_with_seed(tmp_path, seed)
    try:
        response = client.get("/api/industries/radar?market=A")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    row = next(item for item in response.json() if item["name"] == "结构趋势行业")
    assert row["news_heat_score"] == 0
    assert row["structure_heat_score"] > 0
    assert row["heat_score"] > 0
    assert row["evidence_status"] == "structure_active"
    assert "资讯热度为0" in row["explanation"]
    assert "趋势覆盖" in row["explanation"]
    assert "平均综合评分" in row["explanation"]
    assert "平均量能放大" in row["explanation"]


def test_radar_mapped_only_without_trend_or_score_stays_low(tmp_path) -> None:
    def seed(session):
        _add_industry(session, "仅映射行业")
        _add_stock(session, "MAPPED_A", "仅映射行业")

    client = _client_with_seed(tmp_path, seed)
    try:
        response = client.get("/api/industries/radar?market=A")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    row = next(item for item in response.json() if item["name"] == "仅映射行业")
    assert row["related_stock_count"] == 1
    assert row["structure_heat_score"] == 0
    assert row["heat_score"] == 0
    assert row["evidence_status"] == "mapped_only"
    assert "仅有股票映射" in row["zero_heat_reason"]


def test_unclassified_large_stock_pool_does_not_suppress_classified_industry(tmp_path) -> None:
    def seed(session):
        _add_industry(session, "已分类强趋势")
        _add_industry(session, "未分类")
        _add_stock(
            session,
            "CLASSIFIED_A",
            "已分类强趋势",
            with_score=True,
            with_trend=True,
            rating="强观察",
            final_score=88,
            trend_score=24,
            volume_expansion_ratio=2.0,
            breakout=True,
        )
        for index in range(20):
            _add_stock(
                session,
                f"UNCLASS_{index}",
                "未分类",
                with_score=True,
                with_trend=True,
                rating="强观察",
                final_score=90,
                trend_score=25,
                volume_expansion_ratio=2.2,
                breakout=True,
            )

    client = _client_with_seed(tmp_path, seed)
    try:
        response = client.get("/api/industries/radar?market=A")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    rows = {item["name"]: item for item in response.json()}
    assert rows["已分类强趋势"]["structure_heat_score"] > 0
    assert rows["未分类"]["related_stock_count"] == 20
    assert rows["已分类强趋势"]["heat_score"] > rows["未分类"]["heat_score"]


def test_market_filter_limits_structure_heat_to_requested_market(tmp_path) -> None:
    def seed(session):
        _add_industry(session, "跨市场行业")
        _add_stock(session, "A_ONLY", "跨市场行业", market="A", with_score=True, with_trend=True, rating="观察")
        _add_stock(session, "US_ONLY", "跨市场行业", market="US")

    client = _client_with_seed(tmp_path, seed)
    try:
        a_response = client.get("/api/industries/radar?market=A")
        us_response = client.get("/api/industries/radar?market=US")
        hk_response = client.get("/api/industries/radar?market=HK")
    finally:
        app.dependency_overrides.clear()

    assert a_response.status_code == 200
    assert us_response.status_code == 200
    assert hk_response.status_code == 200
    a_row = next(item for item in a_response.json() if item["name"] == "跨市场行业")
    us_row = next(item for item in us_response.json() if item["name"] == "跨市场行业")
    hk_row = next(item for item in hk_response.json() if item["name"] == "跨市场行业")
    assert a_row["market"] == "A"
    assert a_row["heat_score"] > 0
    assert a_row["related_stock_count"] == 1
    assert us_row["market"] == "US"
    assert us_row["related_stock_count"] == 1
    assert us_row["heat_score"] == 0
    assert us_row["evidence_status"] == "mapped_only"
    assert hk_row["market"] == "HK"
    assert hk_row["related_stock_count"] == 0
    assert hk_row["heat_score"] == 0
