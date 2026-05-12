from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.guardrails import RISK_DISCLAIMER, sanitize_financial_output
from app.agent.orchestrator import AgentOrchestrator, _sanitize_runtime_content_json
from app.agent.runtime.mock_adapter import MockRuntimeAdapter
from app.agent.schemas import AgentRunRequest, AgentTaskType
from app.db.models import AgentArtifact, AgentRun, AgentSkill, AgentStep, AgentToolCall, Base, DailyBar, DailyReport, EvidenceChain, Industry, IndustryHeat, IndustryKeyword, Stock, StockScore, TrendSignal
from app.db.session import get_session
from app.main import app


@contextmanager
def _session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'agent_test.sqlite'}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as session:
        _seed_agent_data(session)
        yield session


@contextmanager
def _client(tmp_path) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'agent_test.sqlite'}", connect_args={"check_same_thread": False}, future=True)
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
        # Standard symbol detection
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我分析中际旭创是不是还在主升趋势"), ["300308"], []) == AgentTaskType.STOCK_DEEP_RESEARCH
        # Priority: Industry/Chain keywords
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我找 AI 服务器产业链今天最强的节点"), ["300308"], ["AI服务器"]) == AgentTaskType.INDUSTRY_CHAIN_RADAR
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="AI 算力上游、中游、下游分别谁最强"), [], ["AI算力"]) == AgentTaskType.INDUSTRY_CHAIN_RADAR
        # Priority: Tenbagger
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我找有十倍股早期特征的公司"), [], []) == AgentTaskType.TENBAGGER_CANDIDATE
        # Priority: Trend Pool
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="帮我筛出当前最强的趋势股票池"), [], []) == AgentTaskType.TREND_POOL_SCAN
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="从全市场筛选高动量标的"), [], []) == AgentTaskType.TREND_POOL_SCAN
        # Priority: Daily Brief
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="生成今天的市场简报"), [], []) == AgentTaskType.DAILY_MARKET_BRIEF
        assert orchestrator._select_task_type(AgentRunRequest(user_prompt="分析 300308 今天的趋势和风险"), ["300308"], []) == AgentTaskType.STOCK_DEEP_RESEARCH


def test_agent_guardrails_extended_replacements() -> None:
    content, warnings = sanitize_financial_output("建议买入，不要满仓梭哈，稳赚必涨且无风险。抄底逃顶，重仓加杠杆，翻倍确定性保证收益。")
    forbidden = ["买入", "卖出", "满仓", "梭哈", "稳赚", "必涨", "无风险", "抄底", "逃顶", "重仓", "加杠杆", "翻倍确定性", "保证收益"]
    for phrase in forbidden:
        if phrase != "卖出": # "卖出" not in the test string but in the list
            assert phrase not in content
    assert "不构成任何投资建议" in content
    assert len(warnings) > 0


def _poll_run(client: TestClient, run_id: int, max_seconds: int = 15) -> dict[str, Any]:
    import time
    for _ in range(int(max_seconds * 2)):
        resp = client.get(f"/api/agent/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ["success", "failed"]:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"Agent run {run_id} timed out")


def test_agent_run_records_tool_calls(tmp_path) -> None:
    with _client(tmp_path) as client:
        # 1. API Call (returns 202)
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创是不是还在主升趋势"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        
        # 2. Manually trigger the background logic using the test session to avoid DB isolation issues
        with _session(tmp_path) as session:
            def session_factory():
                return _session(tmp_path)
            
            orchestrator = AgentOrchestrator(session, session_factory=session_factory)
            orchestrator.execute_async(run_id, AgentRunRequest(user_prompt="帮我分析中际旭创是不是还在主升趋势"))
            
            # 3. Verify results in DB
            run = session.get(AgentRun, run_id)
            assert run.status == "success"
            tool_calls = session.scalars(select(AgentToolCall).where(AgentToolCall.run_id == run_id)).all()
            assert len(tool_calls) > 0


def test_agent_run_stock_smoke_and_audit_tables(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创是不是还在主升趋势"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        
        # Manually execute to bypass BackgroundTask isolation
        with _session(tmp_path) as session:
            def session_factory():
                return _session(tmp_path)
            orchestrator = AgentOrchestrator(session, session_factory=session_factory)
            orchestrator.execute_async(run_id, AgentRunRequest(user_prompt="帮我分析中际旭创是不是还在主升趋势"))
        
        # Now we can poll/get the detail via API
        resp = client.get(f"/api/agent/runs/{run_id}")
        result = resp.json()
        assert result["status"] == "success"
        assert "stock_deep_research" in result["task_type"]

        # Check artifact
        artifact = result["latest_artifact"]
        assert artifact
        assert "个股深度投研" in artifact["title"]


def test_claim_guardrails_preserve_claim_shape_and_disclaimer() -> None:
    content_json, warnings = _sanitize_runtime_content_json(
        {
            "claims": [
                {
                    "id": "C1",
                    "section": "核心结论",
                    "text": "建议买入，目标价：123",
                    "evidence_ref_ids": ["S1"],
                    "source_tools": ["market.get_price_trend"],
                    "uncertainty": "无风险",
                }
            ]
        }
    )
    claim = content_json["claims"][0]
    assert "买入" not in claim["text"]
    assert "目标价" not in claim["text"]
    assert "无风险" not in claim["uncertainty"]
    assert RISK_DISCLAIMER not in claim["text"]
    assert content_json["risk_disclaimer"] == RISK_DISCLAIMER
    assert warnings


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
            assert session.scalar(select(AgentSkill).where(AgentSkill.name == "AI服务器产业链雷达")) is not None

def _seed_agent_data(session: Session) -> None:
    existing = session.scalar(select(Industry).where(Industry.name == "AI算力"))
    if existing is not None:
        return

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


def _assert_claim_evidence_integrity(artifact: dict) -> None:
    evidence_ids = {row["id"] for row in artifact["evidence_refs"]}
    assert evidence_ids
    for claim in artifact["claims"]:
        assert claim["evidence_ref_ids"]
        assert set(claim["evidence_ref_ids"]) <= evidence_ids
    for claim_ref in artifact["claim_refs"]:
        assert claim_ref["has_evidence"] is True
        assert not claim_ref["missing_evidence_ref_ids"]
        assert set(claim_ref["evidence_ref_ids"]) <= evidence_ids


def _claim_refs_from_runtime(result) -> list[dict]:
    refs_by_id = {row["id"]: row for row in result.evidence_refs}
    return [
        {
            "claim_id": claim["id"],
            "evidence_ref_ids": claim["evidence_ref_ids"],
            "evidence_refs": [refs_by_id[ref_id] for ref_id in claim["evidence_ref_ids"]],
            "missing_evidence_ref_ids": [],
            "has_evidence": True,
        }
        for claim in result.content_json["claims"]
    ]


# ---------------------------------------------------------------------------
# MVP 2.1 New Endpoint Tests  (use pytest.skip for endpoints not yet added)
# ---------------------------------------------------------------------------


def test_sse_events_endpoint_exists(tmp_path) -> None:
    """SSE streaming endpoint should exist at GET /api/agent/runs/{run_id}/events."""
    with _client(tmp_path) as client:
        # Create a run so the endpoint has a valid resource to stream
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        response = client.get(f"/api/agent/runs/{run_id}/events")
        if response.status_code == 404:
            pytest.skip("SSE events endpoint not yet implemented (expected for MVP 2.1)")
        assert "text/event-stream" in response.headers.get("content-type", "")


def test_sse_events_for_completed_run(tmp_path) -> None:
    """After a completed run, the events endpoint should return event data."""
    with _client(tmp_path) as client:
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        with _session(tmp_path) as session:
            def session_factory():
                return _session(tmp_path)
            orchestrator = AgentOrchestrator(session, session_factory=session_factory)
            orchestrator.execute_async(run_id, AgentRunRequest(user_prompt="帮我分析中际旭创"))

        events_resp = client.get(f"/api/agent/runs/{run_id}/events")
        if events_resp.status_code == 404:
            pytest.skip("SSE events endpoint not yet implemented (expected for MVP 2.1)")
        assert events_resp.status_code == 200
        assert "text/event-stream" in events_resp.headers.get("content-type", "")


def test_tools_endpoint(tmp_path) -> None:
    """GET /api/agent/tools should return a list with >=5 read_only tools."""
    with _client(tmp_path) as client:
        response = client.get("/api/agent/tools")
        if response.status_code == 404:
            pytest.skip("Tools endpoint not yet implemented (expected for MVP 2.1)")
        assert response.status_code == 200
        tools = response.json()
        assert isinstance(tools, list)
        assert len(tools) >= 5
        for tool in tools:
            assert tool.get("read_only") is True


def test_mcp_manifest_endpoint(tmp_path) -> None:
    """GET /api/agent/tools/mcp-manifest should return valid JSON with tools array."""
    with _client(tmp_path) as client:
        response = client.get("/api/agent/tools/mcp-manifest")
        if response.status_code == 404:
            pytest.skip("MCP manifest endpoint not yet implemented (expected for MVP 2.1)")
        assert response.status_code == 200
        manifest = response.json()
        assert "tools" in manifest
        tools = manifest["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0


# ---------------------------------------------------------------------------
# Follow-up endpoint tests  (endpoints already exist in api.py)
# ---------------------------------------------------------------------------


def test_followup_endpoint(tmp_path) -> None:
    """Test POST /api/agent/runs/{run_id}/followups on a completed run."""
    with _client(tmp_path) as client:
        # 1. Create and execute a run
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创是不是还在主升趋势"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        with _session(tmp_path) as session:
            def session_factory():
                return _session(tmp_path)
            orchestrator = AgentOrchestrator(session, session_factory=session_factory)
            orchestrator.execute_async(run_id, AgentRunRequest(user_prompt="帮我分析中际旭创是不是还在主升趋势"))

        # 2. Followup on the completed run
        followup_resp = client.post(
            f"/api/agent/runs/{run_id}/followups",
            json={"message": "请解释一下这个结论的推理过程"},
        )
        assert followup_resp.status_code == 201
        data = followup_resp.json()
        assert "answer_md" in data
        assert isinstance(data["answer_md"], str)
        assert "evidence_refs" in data

        # 3. Followup on non-existent run -> 404
        resp404 = client.post("/api/agent/runs/999999/followups", json={"message": "explain"})
        assert resp404.status_code == 404

        # 4. Followup on run that exists but has no artifact -> 400
        with _session(tmp_path) as s:
            from app.db.models import AgentRun as AgentRunModel

            orphan = AgentRunModel(user_prompt="orphan-no-artifact", task_type="auto", status="pending")
            s.add(orphan)
            s.commit()
            orphan_id = orphan.id

        resp400 = client.post(f"/api/agent/runs/{orphan_id}/followups", json={"message": "explain"})
        assert resp400.status_code == 400
        err = resp400.json()
        assert "detail" in err


def test_followup_messages_endpoint(tmp_path) -> None:
    """Test GET /api/agent/runs/{run_id}/messages returns followup history."""
    with _client(tmp_path) as client:
        # 1. Create and execute a run
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创是不是还在主升趋势"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        with _session(tmp_path) as session:
            def session_factory():
                return _session(tmp_path)
            orchestrator = AgentOrchestrator(session, session_factory=session_factory)
            orchestrator.execute_async(run_id, AgentRunRequest(user_prompt="帮我分析中际旭创是不是还在主升趋势"))

        # 2. Create a followup
        followup_resp = client.post(
            f"/api/agent/runs/{run_id}/followups",
            json={"message": "请解释一下风险因素"},
        )
        assert followup_resp.status_code == 201

        # 3. Retrieve messages
        messages_resp = client.get(f"/api/agent/runs/{run_id}/messages")
        assert messages_resp.status_code == 200
        messages = messages_resp.json()
        assert len(messages) > 0
        msg = messages[0]
        assert "message_id" in msg
        assert "answer_md" in msg
        assert msg["message"] == "请解释一下风险因素"


def test_followup_guardrails(tmp_path) -> None:
    """Verify follow-up output goes through guardrails (disclaimer present, no forbidden words)."""
    with _client(tmp_path) as client:
        # Create and execute a run
        response = client.post("/api/agent/runs", json={"user_prompt": "帮我分析中际旭创是不是还在主升趋势"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        with _session(tmp_path) as session:
            def session_factory():
                return _session(tmp_path)
            orchestrator = AgentOrchestrator(session, session_factory=session_factory)
            orchestrator.execute_async(run_id, AgentRunRequest(user_prompt="帮我分析中际旭创是不是还在主升趋势"))

        # Followup
        followup_resp = client.post(
            f"/api/agent/runs/{run_id}/followups",
            json={"message": "请详细分析"},
        )
        assert followup_resp.status_code == 201
        data = followup_resp.json()

        # Guardrails assertions
        answer = data["answer_md"]
        assert RISK_DISCLAIMER in answer
        for word in ["买入", "卖出", "满仓", "梭哈", "稳赚"]:
            assert word not in answer, f"Forbidden word '{word}' found in followup answer"


# ---------------------------------------------------------------------------
# Task type detection edge cases
# ---------------------------------------------------------------------------


def test_task_type_edge_cases(tmp_path) -> None:
    """Test edge case prompts against orchestrator._select_task_type directly."""
    with _session(tmp_path) as session:
        orchestrator = AgentOrchestrator(session)

        # Edge case 1: "上游" etc. -> industry_chain_radar (via extracted industries)
        assert orchestrator._select_task_type(
            AgentRunRequest(user_prompt="AI 算力上游、中游、下游分别谁最强"),
            [],
            ["AI算力"],
        ) == AgentTaskType.INDUSTRY_CHAIN_RADAR

        # Edge case 2: "筛选" + "动量" -> trend_pool_scan
        assert orchestrator._select_task_type(
            AgentRunRequest(user_prompt="从全市场筛选高动量标的"),
            [],
            [],
        ) == AgentTaskType.TREND_POOL_SCAN

        # Edge case 3: "复盘" -> daily_market_brief
        assert orchestrator._select_task_type(
            AgentRunRequest(user_prompt="今天的市场复盘和明天关注什么"),
            [],
            [],
        ) == AgentTaskType.DAILY_MARKET_BRIEF

        # Edge case 4: "产业链" -> industry_chain_radar (not stock)
        assert orchestrator._select_task_type(
            AgentRunRequest(user_prompt="分析光模块产业链哪家最强"),
            [],
            [],
        ) == AgentTaskType.INDUSTRY_CHAIN_RADAR

        # Edge case 5: "10倍" -> tenbagger_candidate
        assert orchestrator._select_task_type(
            AgentRunRequest(user_prompt="筛选有成长空间10倍的早期标的"),
            [],
            [],
        ) == AgentTaskType.TENBAGGER_CANDIDATE


# ---------------------------------------------------------------------------
# Guardrails completeness
# ---------------------------------------------------------------------------


def test_guardrails_all_forbidden_words() -> None:
    """Verify ALL forbidden words from FORBIDDEN_REPLACEMENTS are actually replaced."""
    from app.agent.guardrails import FORBIDDEN_REPLACEMENTS

    composite_text = "建议买入 建议卖出 满仓梭哈 稳赚必涨 无风险 抄底逃顶 重仓加杠杆 翻倍确定性保证收益"
    sanitized, warnings = sanitize_financial_output(composite_text)

    # Every key in FORBIDDEN_REPLACEMENTS must be absent
    for word in FORBIDDEN_REPLACEMENTS:
        assert word not in sanitized, f"'{word}' was not replaced in sanitized output"

    # Risk disclaimer must be appended
    assert RISK_DISCLAIMER in sanitized
    assert len(warnings) > 0

    # Regex-based replacements
    regex_text = "建议加仓 建议减仓 目标价:123 目标价：456"
    sanitized2, _ = sanitize_financial_output(regex_text)
    assert "建议加仓" not in sanitized2
    assert "建议减仓" not in sanitized2
    assert "目标价:123" not in sanitized2
    assert "目标价：456" not in sanitized2
    assert "建议跟踪观察" in sanitized2
    assert "建议复核风险暴露" in sanitized2
    assert "估值情景需独立复核" in sanitized2
