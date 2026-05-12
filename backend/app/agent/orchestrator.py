from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.events import publish_event
from app.agent.guardrails import RISK_DISCLAIMER, sanitize_financial_output, sanitize_financial_text
from app.agent.runtime import AgentRuntimeResult, MockRuntimeAdapter, RealRuntimeAdapter, RuntimeAdapter
from app.agent.schemas import AgentRunRequest, AgentRunResponse, AgentTaskType
from app.agent.skills.generator import generate_skill_from_run
from app.agent.skills.registry import load_skill_template
from app.agent.tools import evidence_tools, industry_tools, market_tools, report_tools, scoring_tools
from app.config import settings
from app.db.models import AgentArtifact, AgentRun, AgentSkill, AgentStep, AgentToolCall, Industry, IndustryKeyword, Stock
from app.services.stock_resolver import STOCK_ALIAS_CODES, resolve_stock


class AgentOrchestrator:
    def __init__(
        self,
        session: Session,
        runtime_adapter: RuntimeAdapter | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        if runtime_adapter:
            self.runtime_adapter = runtime_adapter
        elif settings.openai_api_key:
            self.runtime_adapter = RealRuntimeAdapter()
        else:
            self.runtime_adapter = MockRuntimeAdapter()

    def create_run_record(self, request: AgentRunRequest) -> int:
        run = AgentRun(
            user_id=request.user_id,
            task_type=str(request.task_type or AgentTaskType.AUTO),
            user_prompt=request.user_prompt,
            runtime_provider=self.runtime_adapter.provider_name,
            status="pending",
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        publish_event(
            self.session,
            run.id,
            "run_created",
            {
                "status": "pending",
                "task_type": str(request.task_type or AgentTaskType.AUTO),
                "user_prompt": request.user_prompt,
            },
        )
        self.session.commit()
        return run.id

    def execute_async(self, run_id: int, request: AgentRunRequest) -> None:
        """Entry point for background task execution."""
        from loguru import logger
        
        # Use injected factory or default production one
        if self.session_factory:
            factory = self.session_factory
        else:
            from app.db.session import SessionLocal as factory
        
        logger.info(f"Starting background agent run: {run_id}")
        try:
            with factory() as session:
                self.session = session
                run = session.get(AgentRun, run_id)
                if not run:
                    logger.error(f"Run {run_id} not found in background task")
                    return
                
                run.status = "running"
                session.commit()
                publish_event(session, run_id, "run_started", {"status": "running"})
                self._run_logic(run, request)
                logger.info(f"Finished background agent run: {run_id} with status {run.status}")
        except Exception as exc:
            logger.exception(f"Background agent run {run_id} failed: {exc}")
            try:
                with factory() as err_session:
                    run = err_session.get(AgentRun, run_id)
                    if run:
                        run.status = "failed"
                        run.error_message = str(exc)
                        run.completed_at = datetime.now(timezone.utc)
                        publish_event(
                            err_session,
                            run_id,
                            "run_failed",
                            {
                                "status": "failed",
                                "error_message": str(exc),
                                "completed_at": run.completed_at.isoformat(),
                            },
                        )
                        err_session.commit()
            except Exception:
                pass

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        """Legacy synchronous entry point."""
        run_id = self.create_run_record(request)
        run = self.session.get(AgentRun, run_id)
        if not run:
             raise RuntimeError("Failed to create run record")
        run.status = "running"
        self.session.commit()
        return self._run_logic(run, request)

    def _run_logic(self, run: AgentRun, request: AgentRunRequest) -> AgentRunResponse:
        artifact_id: int | None = None
        warnings: list[str] = []
        selected_task_type = AgentTaskType.STOCK_DEEP_RESEARCH
        report_title = "Agent 一键投研"
        summary = ""
        try:
            selected_symbols = self._extract_symbols(request)
            selected_industries = self._extract_industries(request)
            selected_task_type = self._select_task_type(request, selected_symbols, selected_industries)
            run.task_type = str(selected_task_type)
            run.selected_symbols_json = _json_dumps(selected_symbols)
            run.selected_industries_json = _json_dumps(selected_industries)
            self._record_step(
                run.id,
                "classify_task",
                "router",
                "success",
                {"prompt": request.user_prompt, "requested_task_type": str(request.task_type or AgentTaskType.AUTO)},
                {
                    "selected_task_type": str(selected_task_type),
                    "selected_symbols": selected_symbols,
                    "selected_industries": selected_industries,
                },
            )

            context = self._collect_context(run.id, request, selected_task_type, selected_symbols, selected_industries)
            skill_template = load_skill_template(selected_task_type)
            runtime_result = self.runtime_adapter.run(
                request.user_prompt,
                context,
                tools=self._tool_catalog(),
                skill_template=skill_template,
            )
            self._record_step(
                run.id,
                "generate_report",
                self.runtime_adapter.provider_name,
                "success",
                {"task_type": str(selected_task_type), "context_keys": sorted(context.keys())},
                {"title": runtime_result.title, "summary": runtime_result.summary},
            )

            content_md, guardrail_warnings = sanitize_financial_output(
                runtime_result.content_md,
                data_quality_warnings=runtime_result.warnings,
            )
            content_json, claim_warnings = _sanitize_runtime_content_json(runtime_result.content_json)
            warnings = _dedupe(runtime_result.warnings + guardrail_warnings + claim_warnings)
            self._record_step(
                run.id,
                "guardrails",
                "compliance",
                "success",
                {"title": runtime_result.title},
                {"warnings": warnings, "risk_disclaimer": RISK_DISCLAIMER},
            )

            artifact = AgentArtifact(
                run_id=run.id,
                artifact_type="research_report",
                title=runtime_result.title,
                content_md=content_md,
                content_json=_json_dumps(content_json),
                evidence_refs_json=_json_dumps(runtime_result.evidence_refs),
            )
            self.session.add(artifact)
            self.session.flush()
            artifact_id = artifact.id
            publish_event(
                self.session,
                run.id,
                "artifact_created",
                {
                    "id": artifact_id,
                    "artifact_type": "research_report",
                    "title": runtime_result.title,
                },
            )
            self._record_step(
                run.id,
                "persist_artifact",
                "artifact_writer",
                "success",
                {"artifact_type": "research_report"},
                {"artifact_id": artifact_id, "evidence_ref_count": len(runtime_result.evidence_refs)},
            )

            if request.save_as_skill:
                self._save_generated_skill(request, selected_task_type, runtime_result.title, context)
                self._record_step(
                    run.id,
                    "save_skill",
                    "skill_builder",
                    "success",
                    {"save_as_skill": True},
                    {"skill_type": str(selected_task_type)},
                )

            run.status = "success"
            run.completed_at = datetime.now(timezone.utc)
            publish_event(
                self.session,
                run.id,
                "run_completed",
                {
                    "status": "success",
                    "error_message": "",
                    "completed_at": run.completed_at.isoformat(),
                },
            )
            report_title = runtime_result.title
            summary = runtime_result.summary
            self.session.commit()
            return AgentRunResponse(
                run_id=run.id,
                status=run.status,
                selected_task_type=selected_task_type,
                report_title=report_title,
                summary=summary,
                artifact_id=artifact_id,
                warnings=warnings,
            )
        except Exception:
            # Re-raise to be caught by execute_async or synchronous run
            raise

    def _select_task_type(
        self,
        request: AgentRunRequest,
        selected_symbols: list[str],
        selected_industries: list[str],
    ) -> AgentTaskType:
        if request.task_type and request.task_type != AgentTaskType.AUTO:
            return request.task_type

        prompt = request.user_prompt
        # Priority 1: Industry/Chain keywords (Structural analysis is usually more specific)
        if _contains_any(prompt, ["产业链", "行业", "主题", "上下游", "节点", "赛道", "板块"]):
            return AgentTaskType.INDUSTRY_CHAIN_RADAR

        # Priority 2: Market Brief (Daily/Reports)
        if _contains_any(prompt, ["日报", "市场简报", "简报", "复盘"]):
            return AgentTaskType.DAILY_MARKET_BRIEF
        
        # Priority 3: Tenbagger (specialized growth search)
        if _contains_any(prompt, ["十倍股", "十倍", "成长空间", "早期特征", "10倍"]):
            return AgentTaskType.TENBAGGER_CANDIDATE

        # Priority 4: Specific Stocks (Deep Research)
        if selected_symbols:
            # Safety guard: if ALL auto-matched symbols are short codes (1-2 chars),
            # no explicit symbols were passed, and no clear code pattern exists,
            # these are likely false positives (e.g. "AI" matched from industry text).
            # Fall through to let industry/other priorities handle the request.
            if (not request.symbols
                    and all(len(s) <= 2 for s in selected_symbols)
                    and not _has_clear_stock_code(prompt)):
                pass  # Short-code false positive — do not treat as stock research
            else:
                return AgentTaskType.STOCK_DEEP_RESEARCH

        # Priority 5: Screening/Pools
        if _contains_any(prompt, ["筛选", "筛出", "股票池", "候选池", "强势股", "动量", "趋势池", "标的"]):
            return AgentTaskType.TREND_POOL_SCAN

        if _contains_any(prompt, ["今日", "今天"]):
             return AgentTaskType.DAILY_MARKET_BRIEF
            
        if selected_industries:
            return AgentTaskType.INDUSTRY_CHAIN_RADAR

        return AgentTaskType.TREND_POOL_SCAN

    def _collect_context(
        self,
        run_id: int,
        request: AgentRunRequest,
        task_type: AgentTaskType,
        selected_symbols: list[str],
        selected_industries: list[str],
    ) -> dict[str, Any]:
        primary_symbol = selected_symbols[0] if selected_symbols else (request.symbols or [""])[0]
        primary_industry = selected_industries[0] if selected_industries else (request.industry_keywords or [""])[0]
        tool_results: dict[str, Any] = {}
        tool_results["report.generate_report_outline"] = self._call_tool(run_id, "report.generate_report_outline", report_tools.generate_report_outline, str(task_type))

        if task_type == AgentTaskType.STOCK_DEEP_RESEARCH:
            tool_results["market.get_stock_basic"] = self._call_tool(run_id, "market.get_stock_basic", market_tools.get_stock_basic, self.session, primary_symbol)
            resolved_symbol = tool_results["market.get_stock_basic"].get("code") or primary_symbol
            tool_results["market.get_price_trend"] = self._call_tool(run_id, "market.get_price_trend", market_tools.get_price_trend, self.session, resolved_symbol, request.time_window)
            tool_results["industry.get_industry_mapping"] = self._call_tool(run_id, "industry.get_industry_mapping", industry_tools.get_industry_mapping, self.session, resolved_symbol)
            tool_results["scoring.get_score_breakdown"] = self._call_tool(run_id, "scoring.get_score_breakdown", scoring_tools.get_score_breakdown, self.session, resolved_symbol)
            tool_results["scoring.get_risk_flags"] = self._call_tool(run_id, "scoring.get_risk_flags", scoring_tools.get_risk_flags, self.session, resolved_symbol)
            tool_results["evidence.get_stock_evidence"] = self._call_tool(run_id, "evidence.get_stock_evidence", evidence_tools.get_stock_evidence, self.session, resolved_symbol)
        elif task_type == AgentTaskType.INDUSTRY_CHAIN_RADAR:
            tool_results["industry.get_industry_mapping"] = self._call_tool(run_id, "industry.get_industry_mapping", industry_tools.get_industry_mapping, self.session, primary_industry)
            mapped_industry = tool_results["industry.get_industry_mapping"].get("industry") or primary_industry
            tool_results["industry.get_industry_chain"] = self._call_tool(run_id, "industry.get_industry_chain", industry_tools.get_industry_chain, self.session, primary_industry or mapped_industry)
            tool_results["industry.get_industry_heatmap"] = self._call_tool(run_id, "industry.get_industry_heatmap", industry_tools.get_industry_heatmap, self.session, primary_industry or mapped_industry)
            tool_results["industry.get_related_stocks_by_industry"] = self._call_tool(run_id, "industry.get_related_stocks_by_industry", industry_tools.get_related_stocks_by_industry, self.session, mapped_industry)
            tool_results["evidence.get_industry_evidence"] = self._call_tool(run_id, "evidence.get_industry_evidence", evidence_tools.get_industry_evidence, self.session, primary_industry or mapped_industry)
        elif task_type == AgentTaskType.TREND_POOL_SCAN:
            tool_results["market.get_momentum_rank"] = self._call_tool(run_id, "market.get_momentum_rank", market_tools.get_momentum_rank, self.session, None, request.time_window, 30)
            tool_results["scoring.get_top_scored_stocks"] = self._call_tool(run_id, "scoring.get_top_scored_stocks", scoring_tools.get_top_scored_stocks, self.session, None, 30)
            tool_results["market.get_market_coverage_status"] = self._call_tool(run_id, "market.get_market_coverage_status", market_tools.get_market_coverage_status, self.session)
        elif task_type == AgentTaskType.TENBAGGER_CANDIDATE:
            tool_results["scoring.get_top_scored_stocks"] = self._call_tool(run_id, "scoring.get_top_scored_stocks", scoring_tools.get_top_scored_stocks, self.session, None, 30)
            tool_results["market.get_momentum_rank"] = self._call_tool(run_id, "market.get_momentum_rank", market_tools.get_momentum_rank, self.session, None, request.time_window, 30)
            tool_results["market.get_market_coverage_status"] = self._call_tool(run_id, "market.get_market_coverage_status", market_tools.get_market_coverage_status, self.session)
        else:
            tool_results["report.get_latest_daily_report"] = self._call_tool(run_id, "report.get_latest_daily_report", report_tools.get_latest_daily_report, self.session)
            tool_results["industry.get_industry_heatmap"] = self._call_tool(run_id, "industry.get_industry_heatmap", industry_tools.get_industry_heatmap, self.session, None)
            tool_results["market.get_momentum_rank"] = self._call_tool(run_id, "market.get_momentum_rank", market_tools.get_momentum_rank, self.session, None, request.time_window, 20)

        self._record_step(
            run_id,
            "collect_context",
            "tool_runner",
            "success",
            {"task_type": str(task_type), "primary_symbol": primary_symbol, "primary_industry": primary_industry},
            {"tool_names": sorted(tool_results.keys())},
        )
        return {
            "task_type": str(task_type),
            "primary_symbol": primary_symbol,
            "primary_industry": primary_industry,
            "selected_symbols": selected_symbols,
            "selected_industries": selected_industries,
            "risk_preference": request.risk_preference,
            "time_window": request.time_window,
            "tool_results": tool_results,
        }

    def _call_tool(self, run_id: int, tool_name: str, func: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
        started = time.perf_counter()
        input_json = {"args": [_safe_arg(arg) for arg in args], "kwargs": kwargs}
        publish_event(
            self.session,
            run_id,
            "tool_call_started",
            {"tool_name": tool_name, "input": input_json},
        )
        try:
            output = func(*args, **kwargs)
            success = output.get("status") != "error"
            error_message = "" if success else str(output.get("message", "tool error"))
        except Exception as exc:
            output = {"status": "error", "message": str(exc)}
            success = False
            error_message = str(exc)
        latency_ms = int((time.perf_counter() - started) * 1000)
        tc = AgentToolCall(
            run_id=run_id,
            tool_name=tool_name,
            input_json=_json_dumps(input_json),
            output_json=_json_dumps(output),
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
        )
        self.session.add(tc)
        self.session.flush()
        publish_event(
            self.session,
            run_id,
            "tool_call_completed",
            {
                "id": tc.id,
                "tool_name": tool_name,
                "output": output,
                "latency_ms": latency_ms,
                "success": success,
                "error_message": error_message,
            },
        )
        return output

    def _record_step(
        self,
        run_id: int,
        step_name: str,
        agent_role: str,
        status: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any],
        error_message: str = "",
    ) -> None:
        step = AgentStep(
            run_id=run_id,
            agent_role=agent_role,
            step_name=step_name,
            status=status,
            input_json=_json_dumps(input_json),
            output_json=_json_dumps(output_json),
            error_message=error_message,
        )
        self.session.add(step)
        self.session.flush()
        publish_event(
            self.session,
            run_id,
            "step_started",
            {
                "id": step.id,
                "step_name": step_name,
                "agent_role": agent_role,
                "status": status,
                "input": input_json,
            },
        )
        publish_event(
            self.session,
            run_id,
            "step_completed",
            {
                "id": step.id,
                "step_name": step_name,
                "agent_role": agent_role,
                "status": status,
                "output": output_json,
                "error_message": error_message,
            },
        )

    def _save_generated_skill(
        self,
        request: AgentRunRequest,
        task_type: AgentTaskType,
        report_title: str,
        context: dict[str, Any],
    ) -> AgentSkill:
        name, skill_md, config = generate_skill_from_run(request, task_type, report_title, context)
        skill = AgentSkill(
            name=name,
            description=f"由 Agent run 自动保存：{request.user_prompt[:120]}",
            skill_type=str(task_type),
            skill_md=skill_md,
            skill_config_json=_json_dumps(config),
            owner_user_id=request.user_id,
            is_system=False,
        )
        self.session.add(skill)
        self.session.flush()
        return skill

    def _extract_symbols(self, request: AgentRunRequest) -> list[str]:
        symbols: list[str] = []
        # 1) Explicit symbols passed by the caller — always trust these
        for item in request.symbols or []:
            stock = resolve_stock(self.session, item)
            symbols.append(stock.code if stock is not None else item)
        prompt = request.user_prompt
        # 2) 6-digit A-share codes (non-digit boundaries — works with mixed Chinese/English text)
        codes = re.findall(r"(?<!\d)(\d{6})(?!\d)", prompt)
        symbols.extend(codes)
        # 3) Explicit format codes (e.g. 300308.SZ, 00700.HK)
        codes_explicit = re.findall(r"(?<!\d)(\d{5,6}\.[A-Z]{2})(?![A-Za-z0-9_])", prompt.upper())
        symbols.extend(codes_explicit)
        # 4) STOCK_ALIAS_CODES — word-boundary matching, skip short aliases
        upper_prompt = prompt.upper()
        for alias, code in STOCK_ALIAS_CODES.items():
            if len(alias) <= 2:
                continue  # Skip 1-2 char aliases (e.g. HW, AI) to avoid false positives
            if re.search(r'[a-zA-Z]', alias):
                # English alias: require ASCII word boundary match
                if _is_ascii_word_boundary(upper_prompt, alias):
                    symbols.append(code)
            else:
                # Chinese-only alias (e.g. 台积电, 英伟达): substring match OK (3+ chars)
                if alias in prompt:
                    symbols.append(code)
        # 5) DB stock matching — word boundaries for codes, 3+ char names
        stocks = self.session.scalars(select(Stock).where(Stock.is_active.is_(True)).limit(50000)).all()
        for stock in stocks:
            if stock.code and len(stock.code) >= 3 and _is_ascii_word_boundary(prompt, stock.code):
                symbols.append(stock.code)
            if stock.name and len(stock.name) >= 3 and stock.name in prompt:
                symbols.append(stock.code)
        return _dedupe([item for item in symbols if item])

    def _extract_industries(self, request: AgentRunRequest) -> list[str]:
        industries: list[str] = [item.strip() for item in request.industry_keywords or [] if item.strip()]
        prompt = request.user_prompt.replace(" ", "")
        known_terms = ["AI服务器", "AI算力", "光模块", "半导体", "新能源", "机器人", "液冷", "PCB", "算力", "云计算"]
        industries.extend(term for term in known_terms if term in prompt)
        for industry in self.session.scalars(select(Industry).limit(1000)).all():
            if industry.name and industry.name in prompt:
                industries.append(industry.name)
        for keyword in self.session.scalars(select(IndustryKeyword).where(IndustryKeyword.is_active.is_(True)).limit(3000)).all():
            if keyword.keyword and keyword.keyword.replace(" ", "") in prompt:
                industry = self.session.get(Industry, keyword.industry_id)
                industries.append(industry.name if industry else keyword.keyword)
        return _dedupe([item for item in industries if item])

    def _tool_catalog(self) -> dict[str, Any]:
        return {
            "market_tools": market_tools,
            "industry_tools": industry_tools,
            "scoring_tools": scoring_tools,
            "evidence_tools": evidence_tools,
            "report_tools": report_tools,
        }


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(item in text for item in keywords)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _safe_arg(value: Any) -> Any:
    if isinstance(value, Session):
        return "Session"
    if isinstance(value, int | float | str | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        return [_safe_arg(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_arg(item) for key, item in value.items()}
    return value.__class__.__name__


def _sanitize_runtime_content_json(content_json: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    claims = content_json.get("claims")
    if not isinstance(claims, list):
        return {**content_json, "risk_disclaimer": RISK_DISCLAIMER}, []

    warnings: list[str] = []
    sanitized_claims: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            sanitized_claims.append(claim)
            continue
        text, text_warnings = sanitize_financial_text(str(claim.get("text") or ""))
        uncertainty, uncertainty_warnings = sanitize_financial_text(str(claim.get("uncertainty") or ""))
        warnings.extend(text_warnings)
        warnings.extend(uncertainty_warnings)
        sanitized_claims.append({**claim, "text": text, "uncertainty": uncertainty})
    return {**content_json, "claims": sanitized_claims, "risk_disclaimer": RISK_DISCLAIMER}, _dedupe(warnings)


def _dedupe(items: list[str]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        rows.append(item)
    return rows


def _is_ascii_word_boundary(text: str, word: str) -> bool:
    """Check if word appears as a standalone ASCII word (not substring of another word)."""
    return bool(re.search(
        r'(?<![a-zA-Z0-9_])' + re.escape(word) + r'(?![a-zA-Z0-9_])',
        text,
    ))


def _has_clear_stock_code(prompt: str) -> bool:
    """Check if prompt contains clear/unequivocal stock code patterns.

    Returns True when the prompt contains unambiguous stock identifiers like
    6-digit A-share codes or exchange-formatted codes (e.g., 300308.SZ).
    Returns False for ambiguous references like company names or short tickers.
    """
    if re.search(r'(?<!\d)(\d{6})(?!\d)', prompt):
        return True
    if re.search(r'(?<!\d)(\d{5,6}\.[A-Za-z]{2})(?![A-Za-z0-9_])', prompt):
        return True
    return False
