from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class EvidenceChainResult:
    stock_code: str
    trade_date: date
    summary: str
    industry_logic: str
    company_logic: str
    trend_logic: str
    catalyst_logic: str
    risk_summary: str
    questions_to_verify: list[str]
    source_refs: list[dict[str, str]]


def _article_title(article: Any) -> str:
    return str(article["title"] if isinstance(article, dict) else article.title)


def _article_url(article: Any) -> str:
    return str(article["source_url"] if isinstance(article, dict) else article.source_url)


def _article_field(article: Any, field: str, default: Any = "") -> Any:
    if isinstance(article, dict):
        return article.get(field, default)
    return getattr(article, field, default)


def _field(row: Any, field: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        return row.get(field, default)
    return getattr(row, field, default)


def _fundamental_logic(fundamental: Any | None) -> str:
    if fundamental is None:
        return "基本面证据缺失，需补充财报和公告来源后验证公司质量。"
    return (
        f"最新财报快照（{_field(fundamental, 'period', '')}，{_field(fundamental, 'report_date', '')}，"
        f"来源{_field(fundamental, 'source', 'unknown')}）显示："
        f"营收同比{float(_field(fundamental, 'revenue_growth_yoy', 0.0) or 0.0):.1f}%，"
        f"利润同比{float(_field(fundamental, 'profit_growth_yoy', 0.0) or 0.0):.1f}%，"
        f"毛利率{float(_field(fundamental, 'gross_margin', 0.0) or 0.0) * 100:.1f}%，"
        f"ROE{float(_field(fundamental, 'roe', 0.0) or 0.0) * 100:.1f}%，"
        f"负债率{float(_field(fundamental, 'debt_ratio', 0.0) or 0.0) * 100:.1f}%，"
        f"现金流质量{float(_field(fundamental, 'cashflow_quality', 0.0) or 0.0):.2f}。"
    )


def build_evidence_chain(
    stock: Any,
    score: Any | None,
    trend_signal: Any | None,
    industry_heat: Any | None,
    articles: list[Any],
    trade_date: date,
    fundamental: Any | None = None,
) -> EvidenceChainResult:
    if score is None or trend_signal is None:
        return EvidenceChainResult(
            stock_code=str(getattr(stock, "code")),
            trade_date=trade_date,
            summary="当前证据不足，不能形成有效观察结论。",
            industry_logic="缺少评分或趋势数据。",
            company_logic=_fundamental_logic(fundamental),
            trend_logic="趋势数据不足。",
            catalyst_logic="催化证据不足。",
            risk_summary="证据不足本身就是核心风险。",
            questions_to_verify=["补齐行情、财务和公告数据后重新评估。"],
            source_refs=[],
        )

    rating = str(getattr(score, "rating", "仅记录"))
    industry_name = str(getattr(stock, "industry_level1", ""))
    heat_explanation = str(getattr(industry_heat, "explanation", "产业热度数据不足。")) if industry_heat else "产业热度数据不足。"
    trend_explanation = str(getattr(trend_signal, "explanation", "趋势数据不足。"))
    score_explanation = str(getattr(score, "explanation", "评分解释不足。"))
    article_titles = [_article_title(article) for article in articles[:3]]
    source_refs = [
        {
            "title": _article_title(article),
            "url": _article_url(article),
            "source": str(_article_field(article, "source", "mock")),
            "source_kind": str(_article_field(article, "source_kind", "mock")),
            "source_confidence": str(_article_field(article, "source_confidence", 0.3)),
        }
        for article in articles[:5]
    ]
    if not source_refs:
        source_refs.append(
            {
                "title": "mock 行情与基础库",
                "url": "mock://market",
                "source": "mock",
                "source_kind": "mock",
                "source_confidence": "0.3",
            }
        )
    if fundamental is not None:
        source_refs.append(
            {
                "title": str(_field(fundamental, "report_title", "财务快照")),
                "url": str(_field(fundamental, "source_url", "")),
                "source": str(_field(fundamental, "source", "unknown")),
                "source_kind": "fundamental",
                "source_confidence": "0.8",
            }
        )

    summary = f"{getattr(stock, 'name')}当前评级为{rating}，属于{industry_name}方向，结论仅用于观察池筛选和后续人工研究。"
    catalyst_logic = "；".join(article_titles) if article_titles else "近期文本催化不足，需继续跟踪公告、财报和产业新闻。"
    risk_summary = "需核验估值、订单真实性、业绩兑现节奏、是否蹭概念以及流动性风险。"
    questions = [
        "产业需求是否从主题热度转化为订单和收入？",
        "公司在产业链中是否属于核心环节或关键供应商？",
        "近期股价趋势是否由业绩兑现支撑，而不是单纯情绪推动？",
        "估值、减持、财务质量和公告风险是否可控？",
    ]
    return EvidenceChainResult(
        stock_code=str(getattr(stock, "code")),
        trade_date=trade_date,
        summary=summary,
        industry_logic=heat_explanation,
        company_logic=f"公司基础库显示所属二级行业为{getattr(stock, 'industry_level2', '')}。{_fundamental_logic(fundamental)}",
        trend_logic=trend_explanation,
        catalyst_logic=catalyst_logic,
        risk_summary=f"{risk_summary} {score_explanation}",
        questions_to_verify=questions,
        source_refs=source_refs,
    )


def evidence_to_json(result: EvidenceChainResult) -> dict[str, Any]:
    return {
        "summary": result.summary,
        "industry_logic": result.industry_logic,
        "company_logic": result.company_logic,
        "trend_logic": result.trend_logic,
        "catalyst_logic": result.catalyst_logic,
        "risk_summary": result.risk_summary,
        "questions_to_verify": result.questions_to_verify,
        "source_refs": result.source_refs,
    }
