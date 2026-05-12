from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.guardrails import sanitize_financial_output
from app.agent.orchestrator import AgentOrchestrator
from app.agent.runtime.mock_adapter import MockRuntimeAdapter
from app.agent.schemas import AgentRunRequest, AgentTaskType
from app.db.models import AgentSkill, Base, DailyBar, DailyReport, EvidenceChain, Industry, IndustryHeat, IndustryKeyword, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.main import app


@contextmanager
def _session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'agent.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        _seed_agent_data(session)
        yield session


@contextmanager
def _client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'agent_api.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as seed_session:
        _seed_agent_data(seed_session)

    def override_session():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = override_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_agent_task_type_auto_detection(tmp_path) -> None:
    with _session(tmp_path) as session:
        orchestrator = AgentOrchestrator(session)
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我分析中际旭创是不是还在主升趋势"), ["300308"], []) == AgentTaskType.STOCK_DEEP_RESEARCH
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我找 AI 服务器产业链今天最强的节点"), [], ["AI服务器"]) == AgentTaskType.INDUSTRY_CHAIN_RADAR
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我筛出当前强势股股票池"), [], []) == AgentTaskType.TREND_POOL_SCAN
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我找十倍股早期特征候选"), [], []) == AgentTaskType.TENBAGGER_CANDIDATE


def test_agent_guardrails_replace_sensitive_advice() -> None:
    content, warnings = sanitize_financial_output("建议买入，不要满仓梭哈，稳赚必涨且无风险。")
    assert "买入" not in content
    assert "满仓" not in content
    assert "梭哈" not in content
    assert "稳赚" not in content
    assert "必涨" not in content
    assert "无风险" not in content
    assert "不构成任何投资建议" in content
    assert warnings


def test_mock_adapter_generates_stock_report() -> None:
    result = MockRuntimeAdapter().run(
        "帮我分析中际旭创是不是还在主升趋势",
        {
            "task_type": "stock_deep_research",
            "primary_symbol": "300308",
            "tool_results": {
                "market.get_stock_basic": {"status": "ok", "code": "300308", "name": "中际旭创", "industry_level1": "AI算力"},
                "market.get_price_trend": {"status": "ok", "trend_score": 82, "is_ma_bullish": True, "window_return_pct": 18},
                "scoring.get_score_breakdown": {"status": "ok", "final_score": 83, "rating": "强观察"},
                "industry.get_industry_mapping": {"status": "ok", "industry": "AI算力"},
                "evidence.get_stock_evidence": {"status": "ok", "summary": "证据链可用", "source_refs": []},
                "scoring.get_risk_flags": {"status": "ok", "flags": ["估值需复核"], "explanation": "仍需复核风险。"},
            },
        },
        tools={},
        skill_template="",
    )
    assert result.title == "个股深度投研：中际旭创"
    assert "风险提示" in result.content_md
    assert "证据链" in result.content_md
    assert "证据引用：S" in result.content_md
    assert result.evidence_refs
    assert result.evidence_refs[0]["id"] == "S1"


def test_agent_run_stock_smoke_and_audit_tables(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创是不是还在主升趋势"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "success"
        assert payload["selected_task_type"] == "stock_deep_research"

        steps = client.get(f"/api/agent/runs/{payload['run_id']}/steps")
        assert steps.status_code == 200
        assert {row["step_name"] for row in steps.json()} >= {"classify_task", "collect_context", "guardrails", "persist_artifact"}

        artifacts = client.get(f"/api/agent/runs/{payload['run_id']}/artifacts")
        assert artifacts.status_code == 200
        artifact = artifacts.json()[0]
        report = artifact["content_md"]
        assert "风险提示" in report
        assert "不构成投资建议" in report
        assert "证据引用：S" in report
        assert artifact["evidence_refs"]
        assert "买入" not in report


def test_agent_skills_save_success(tmp_path) -> None:
    with _client(tmp_path) as client:
        skill = client.post(
            "/api/agent/skills",
            json={
                "name": "AI服务器产业链雷达",
                "description": "复用产业链雷达工作流",
                "skill_type": "industry_chain_radar",
                "skill_md": "# AI服务器产业链雷达",
                "skill_config": {"industry_keywords": ["AI服务器"]},
            },
        )
        assert skill.status_code == 200
        assert skill.json()["id"]

        skills = client.get("/api/agent/skills")
        assert skills.status_code == 200
        names = {row["name"] for row in skills.json()}
        assert "AI服务器产业链雷达" in names
        assert "个股深度投研" in names

        with _session(tmp_path) as session:
            assert session.scalar(select(AgentSkill).where(AgentSkill.name == "AI服务器产业链雷达")) is None


def _seed_agent_data(session: Session) -> None:
    industry = Industry(name="AI算力", description="AI服务器、光模块、算力基础设施")
    session.add(industry)
    session.flush()
    session.add(IndustryKeyword(industry_id=industry.id, keyword="AI服务器", weight=1.0))
    session.add(
        Stock(
            code="300308",
            name="中际旭创",
            market="A",
            board="chinext",
            exchange="SZSE",
            industry_level1="AI算力",
            industry_level2="光模块",
            concepts=json.dumps(["AI服务器", "光模块"], ensure_ascii=False),
            market_cap=900,
            float_market_cap=850,
            source="test",
            data_vendor="test",
        )
    )
    session.add_all(
        [
            DailyBar(stock_code="300308", trade_date=date(2026, 5, 10), open=100, high=105, low=99, close=104, pre_close=100, volume=1000, amount=100000, pct_chg=4, source="test", source_kind="real", source_confidence=1.0),
            DailyBar(stock_code="300308", trade_date=date(2026, 5, 11), open=104, high=112, low=103, close=111, pre_close=104, volume=1500, amount=160000, pct_chg=6.7, source="test", source_kind="real", source_confidence=1.0),
        ]
    )
    session.add(
        TrendSignal(
            stock_code="300308",
            trade_date=date(2026, 5, 11),
            ma20=100,
            ma60=92,
            ma120=85,
            ma250=70,
            return_20d=0.18,
            return_60d=0.35,
            return_120d=0.62,
            relative_strength_score=95,
            relative_strength_rank=3,
            is_ma_bullish=True,
            is_breakout_120d=True,
            is_breakout_250d=True,
            volume_expansion_ratio=1.8,
            max_drawdown_60d=-0.08,
            trend_score=84,
            explanation="均线多头，趋势强。",
        )
    )
    session.add(
        StockScore(
            stock_code="300308",
            trade_date=date(2026, 5, 11),
            industry_score=88,
            company_score=78,
            trend_score=84,
            catalyst_score=75,
            risk_penalty=12,
            raw_score=82,
            final_score=82,
            rating="强观察",
            confidence_level="high",
            confidence_reasons=json.dumps(["测试数据完整"], ensure_ascii=False),
            explanation="AI算力产业趋势强，趋势确认，风险需复核。",
        )
    )
    session.add(
        EvidenceChain(
            stock_code="300308",
            trade_date=date(2026, 5, 11),
            summary="中际旭创处于 AI 算力光模块产业链，需要跟踪订单与趋势延续。",
            industry_logic="AI服务器需求带动高速光模块。",
            company_logic="公司处于光模块环节。",
            trend_logic="趋势分较高且均线多头。",
            catalyst_logic="AI资本开支为主要催化。",
            risk_summary="估值、订单兑现和行业拥挤度需要复核。",
            questions_to_verify=json.dumps(["订单是否继续确认"], ensure_ascii=False),
            source_refs=json.dumps([{"title": "测试新闻", "source": "unit-test", "url": "https://example.com"}], ensure_ascii=False),
        )
    )
    session.add(
        IndustryHeat(
            industry_id=industry.id,
            trade_date=date(2026, 5, 11),
            heat_1d=80,
            heat_7d=75,
            heat_30d=70,
            heat_change_7d=5,
            heat_change_30d=12,
            heat_score=82,
            top_keywords=json.dumps(["AI服务器", "光模块"], ensure_ascii=False),
            top_articles=json.dumps(["测试新闻"], ensure_ascii=False),
            explanation="行业热度较高。",
        )
    )
    session.add(
        DailyReport(
            report_date=date(2026, 5, 11),
            title="AlphaRadar 每日市场简报",
            market_summary="AI算力链热度较高。",
            top_industries=json.dumps(["AI算力"], ensure_ascii=False),
            top_trend_stocks=json.dumps([{"code": "300308", "name": "中际旭创"}], ensure_ascii=False),
            new_watchlist_stocks=json.dumps([], ensure_ascii=False),
            risk_alerts=json.dumps(["数据为测试样本"], ensure_ascii=False),
            full_markdown="# 每日市场简报",
        )
    )
    session.commit()
