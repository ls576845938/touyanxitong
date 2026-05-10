from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes_chain import chain_node_detail, chain_overview
from app.db.models import Base, Industry, IndustryHeat, Stock, StockScore, TrendSignal


def test_chain_overview_returns_empty_graph_when_seed_missing(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'chain-overview.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def missing_loader():
        from app.services.chain_graph_engine import ChainSeedBundle

        return ChainSeedBundle([], [], [], [], None, available=False, error="missing")

    monkeypatch.setattr("app.services.chain_graph_engine._load_chain_seed_contract", missing_loader)

    with Session() as session:
        payload = chain_overview(market="ALL", session=session)

    assert payload["summary"]["market"] == "ALL"
    assert payload["summary"]["seed_status"]["available"] is False
    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert payload["regions"] == []
    assert payload["default_focus_node_key"] is None


def test_chain_node_detail_returns_heat_and_neighbors(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'chain-node.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    trade_date = date(2026, 5, 9)

    with Session() as session:
        battery = Industry(name="动力电池", description="电池制造")
        lithium = Industry(name="锂矿", description="上游资源")
        session.add_all([battery, lithium])
        session.flush()
        session.add_all(
            [
                IndustryHeat(industry_id=battery.id, trade_date=trade_date, heat_score=24, heat_7d=20, heat_30d=18),
                IndustryHeat(industry_id=lithium.id, trade_date=trade_date, heat_score=12, heat_7d=10, heat_30d=8),
                Stock(
                    code="300001",
                    name="电池龙头",
                    market="A",
                    board="chinext",
                    exchange="SZ",
                    industry_level1="动力电池",
                    industry_level2="电芯",
                ),
                Stock(
                    code="600001",
                    name="锂矿资源",
                    market="A",
                    board="main",
                    exchange="SH",
                    industry_level1="锂矿",
                    industry_level2="资源",
                ),
                StockScore(stock_code="300001", trade_date=trade_date, final_score=88, industry_score=20, company_score=25, trend_score=22, rating="强观察"),
                TrendSignal(stock_code="300001", trade_date=trade_date, trend_score=76, is_ma_bullish=True, is_breakout_120d=True),
            ]
        )
        session.commit()

    fake_bundle = {
        "layers": ["upstream", "midstream"],
        "nodes": [
            {
                "node_key": "lithium",
                "name": "锂矿",
                "layer": "upstream",
                "node_type": "resource",
                "description": "锂资源",
                "industry_names": ["锂矿"],
                "tags": ["资源"],
                "anchor_companies": ["锂矿资源"],
                "indicators": ["锂价"],
            },
            {
                "node_key": "battery",
                "name": "动力电池",
                "layer": "midstream",
                "node_type": "manufacturing",
                "description": "电池制造",
                "industry_names": ["动力电池"],
                "tags": ["制造"],
                "anchor_companies": ["电池龙头"],
                "indicators": ["装机量"],
            },
        ],
        "edges": [
            {"source": "lithium", "target": "battery", "relation_type": "supply", "flow": "upstream_to_downstream", "weight": 0.8}
        ],
        "regions": [
            {
                "region_key": "cn",
                "label": "中国",
                "x": 0.6,
                "y": 0.5,
                "geo_role": "manufacturing",
                "specialty": "制造中心",
                "node_keys": ["battery", "lithium"],
                "listed_hubs": ["SZ", "SH"],
            }
        ],
        "default_focus_node_key": "battery",
    }

    def fake_loader():
        from app.services.chain_graph_engine import ChainSeedBundle

        return ChainSeedBundle(
            layers=fake_bundle["layers"],
            nodes=fake_bundle["nodes"],
            edges=fake_bundle["edges"],
            regions=fake_bundle["regions"],
            default_focus_node_key=fake_bundle["default_focus_node_key"],
            available=True,
            error=None,
        )

    monkeypatch.setattr("app.services.chain_graph_engine._load_chain_seed_contract", fake_loader)

    with Session() as session:
        overview_payload = chain_overview(market="A", session=session)
        assert overview_payload["summary"]["market"] == "A"
        assert overview_payload["summary"]["seed_status"]["available"] is True
        assert len(overview_payload["nodes"]) == 2
        assert overview_payload["default_focus_node_key"] == "battery"

        payload = chain_node_detail(node_key="battery", market="A", session=session)
        assert payload["node"]["node_key"] == "battery"
        assert payload["market"] == "A"
        assert payload["heat"]["heat_score"] > 0
        assert payload["heat"]["industry_count"] == 1
        assert payload["mapped_industries"][0]["name"] == "动力电池"
        assert payload["leading_stocks"][0]["code"] == "300001"
        assert payload["leading_stocks"][0]["rating"] == "强观察"
        assert payload["regions"][0]["region_key"] == "cn"
        assert payload["upstream"][0]["node_key"] == "lithium"
        assert payload["seed_status"]["available"] is True
