from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.engines.risk_engine import assess_stock_risk


@dataclass(frozen=True)
class StockScoreMetrics:
    stock_code: str
    trade_date: date
    industry_score: float
    company_score: float
    trend_score: float
    catalyst_score: float
    risk_penalty: float
    raw_score: float
    source_confidence: float
    data_confidence: float
    fundamental_confidence: float
    news_confidence: float
    evidence_confidence: float
    confidence_level: str
    confidence_reasons: list[str]
    final_score: float
    rating: str
    explanation: str


def rating_for_score(score: float) -> str:
    if score >= 85:
        return "强观察"
    if score >= 70:
        return "观察"
    if score >= 55:
        return "弱观察"
    if score >= 40:
        return "仅记录"
    return "排除"


def _cap_rating_for_confidence(rating: str, confidence: float) -> str:
    if confidence < 0.45 and rating in {"强观察", "观察", "弱观察"}:
        return "仅记录"
    if confidence < 0.65 and rating in {"强观察", "观察"}:
        return "弱观察"
    return rating


def _confidence_level(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.6:
        return "medium"
    if confidence >= 0.4:
        return "low"
    return "insufficient"


def _metric_score(value: float, low: float, high: float, points: float, reverse: bool = False) -> float:
    if high <= low:
        return 0.0
    normalized = (value - low) / (high - low)
    if reverse:
        normalized = 1 - normalized
    return max(0.0, min(points, normalized * points))


def _company_score(stock: Any, fundamental: Any | None) -> float:
    if getattr(stock, "is_st", False) or not getattr(stock, "is_active", True):
        return 5.0
    if fundamental is None:
        market_cap = float(getattr(stock, "market_cap", 0.0) or 0.0)
        float_market_cap = float(getattr(stock, "float_market_cap", 0.0) or 0.0)
        scale_score = min(10.0, market_cap / 500)
        float_score = min(5.0, float_market_cap / 700)
        listing_bonus = 3.0 if getattr(stock, "listing_date", None) else 0.0
        return round(min(18.0, scale_score + float_score + listing_bonus), 2)

    revenue_growth = float(getattr(fundamental, "revenue_growth_yoy", 0.0) or 0.0)
    profit_growth = float(getattr(fundamental, "profit_growth_yoy", 0.0) or 0.0)
    gross_margin = float(getattr(fundamental, "gross_margin", 0.0) or 0.0)
    roe = float(getattr(fundamental, "roe", 0.0) or 0.0)
    debt_ratio = float(getattr(fundamental, "debt_ratio", 0.0) or 0.0)
    cashflow_quality = float(getattr(fundamental, "cashflow_quality", 0.0) or 0.0)
    score = (
        _metric_score(revenue_growth, -10, 35, 5)
        + _metric_score(profit_growth, -15, 35, 5)
        + _metric_score(gross_margin, 0.12, 0.55, 4)
        + _metric_score(roe, 0.02, 0.22, 4)
        + _metric_score(debt_ratio, 0.25, 0.85, 3, reverse=True)
        + _metric_score(cashflow_quality, 0.35, 1.35, 4)
    )
    return round(min(25.0, score), 2)


def _fundamental_summary(fundamental: Any | None) -> str:
    if fundamental is None:
        return "基本面数据缺失"
    return (
        f"{getattr(fundamental, 'period', '')}（{getattr(fundamental, 'report_date', '')}，"
        f"来源{getattr(fundamental, 'source', 'unknown')}），"
        f"营收同比{float(getattr(fundamental, 'revenue_growth_yoy', 0.0) or 0.0):.1f}%，"
        f"利润同比{float(getattr(fundamental, 'profit_growth_yoy', 0.0) or 0.0):.1f}%，"
        f"毛利率{float(getattr(fundamental, 'gross_margin', 0.0) or 0.0) * 100:.1f}%，"
        f"ROE{float(getattr(fundamental, 'roe', 0.0) or 0.0) * 100:.1f}%，"
        f"负债率{float(getattr(fundamental, 'debt_ratio', 0.0) or 0.0) * 100:.1f}%，"
        f"现金流质量{float(getattr(fundamental, 'cashflow_quality', 0.0) or 0.0):.2f}"
    )


def _catalyst_score(stock_code: str, articles_by_stock: dict[str, list[Any]]) -> float:
    article_count = len(articles_by_stock.get(stock_code, []))
    return round(min(10.0, article_count * 3.0 + (2.0 if article_count else 0.0)), 2)


def _score_confidence(
    stock: Any,
    trend: Any | None,
    heat: Any | None,
    article_count: int,
    fundamental: Any | None,
) -> tuple[float, float, float, float, float, list[str]]:
    reasons: list[str] = []

    source_confidence = 0.15
    data_confidence = 0.2
    if trend is None:
        reasons.append("行情趋势数据不足")
    else:
        source_confidence += 0.65
        data_confidence += 0.65
        if float(getattr(trend, "trend_score", 0.0) or 0.0) <= 0:
            source_confidence -= 0.1
            data_confidence -= 0.15
            reasons.append("趋势信号较弱或不可用")

    fundamental_confidence = 0.0
    if float(getattr(stock, "market_cap", 0.0) or 0.0) > 0:
        fundamental_confidence += 0.25
        data_confidence += 0.1
    else:
        reasons.append("市值数据缺失")
    if float(getattr(stock, "float_market_cap", 0.0) or 0.0) > 0:
        fundamental_confidence += 0.2
    else:
        reasons.append("流通市值数据缺失")
    if getattr(stock, "listing_date", None):
        fundamental_confidence += 0.15
        data_confidence += 0.05
    else:
        reasons.append("上市日期缺失")
    if fundamental is None:
        if fundamental_confidence < 0.6:
            reasons.append("基本面数据缺失")
        else:
            reasons.append("财报基本面数据缺失，使用市值和上市状态降级评分")
    else:
        fundamental_confidence = 1.0
        data_confidence += 0.15

    news_confidence = 0.0
    evidence_confidence = 0.0
    if heat is None:
        reasons.append("所属行业热度证据缺失")
    elif float(getattr(heat, "heat_score", 0.0) or 0.0) <= 0:
        evidence_confidence += 0.15
        reasons.append("所属行业近期热度为0")
    else:
        evidence_confidence += 0.45

    if article_count <= 0:
        reasons.append("个股资讯证据不足")
    else:
        news_confidence = min(1.0, article_count / 3)
        evidence_confidence += min(0.55, news_confidence * 0.55)

    return (
        round(max(0.0, min(1.0, source_confidence)), 2),
        round(max(0.0, min(1.0, data_confidence)), 2),
        round(max(0.0, min(1.0, fundamental_confidence)), 2),
        round(max(0.0, min(1.0, news_confidence)), 2),
        round(max(0.0, min(1.0, evidence_confidence)), 2),
        reasons,
    )


def calculate_stock_scores(
    stocks: list[Any],
    latest_trend_by_code: dict[str, Any],
    latest_heat_by_industry_name: dict[str, Any],
    articles_by_stock: dict[str, list[Any]],
    trade_date: date,
    latest_fundamental_by_code: dict[str, Any] | None = None,
) -> list[StockScoreMetrics]:
    results: list[StockScoreMetrics] = []
    fundamental_by_code = latest_fundamental_by_code or {}
    for stock in stocks:
        code = str(getattr(stock, "code"))
        industry_name = str(getattr(stock, "industry_level1", ""))
        trend = latest_trend_by_code.get(code)
        heat = latest_heat_by_industry_name.get(industry_name)
        industry_score = min(30.0, float(getattr(heat, "heat_score", 0.0) or 0.0))
        trend_score = min(25.0, float(getattr(trend, "trend_score", 0.0) or 0.0))
        fundamental = fundamental_by_code.get(code)
        company_score = _company_score(stock, fundamental)
        article_count = len(articles_by_stock.get(code, []))
        catalyst_score = _catalyst_score(code, articles_by_stock)
        risk = assess_stock_risk(stock, trend)
        raw_score = round(industry_score + company_score + trend_score + catalyst_score - risk.penalty, 2)
        source_confidence, data_confidence, fundamental_confidence, news_confidence, evidence_confidence, confidence_reasons = _score_confidence(
            stock, trend, heat, article_count, fundamental
        )
        combined_confidence = round(
            source_confidence * 0.2 + data_confidence * 0.3 + fundamental_confidence * 0.25 + news_confidence * 0.25,
            2,
        )
        confidence_weight = 0.65 + combined_confidence * 0.35
        final_score = round(raw_score * confidence_weight, 2)
        final_score = max(0.0, min(100.0, final_score))
        rating = _cap_rating_for_confidence(rating_for_score(final_score), combined_confidence)
        confidence_level = _confidence_level(combined_confidence)
        reason_text = "、".join(confidence_reasons) if confidence_reasons else "数据和证据覆盖正常"
        explanation = (
            f"产业趋势分{industry_score:.1f}，公司质量分{company_score:.1f}，"
            f"趋势分{trend_score:.1f}，信息催化分{catalyst_score:.1f}，风险扣分{risk.penalty:.1f}。"
            f"基本面：{_fundamental_summary(fundamental)}。"
            f"原始分{raw_score:.1f}，置信度加权后{final_score:.1f}；"
            f"数据源置信度{source_confidence:.2f}，数据置信度{data_confidence:.2f}，"
            f"基本面置信度{fundamental_confidence:.2f}，资讯置信度{news_confidence:.2f}，"
            f"证据置信度{evidence_confidence:.2f}，"
            f"综合置信度{combined_confidence:.2f}（{confidence_level}），原因：{reason_text}。"
            f"风险说明：{risk.explanation}"
        )
        if confidence_level in {"low", "insufficient"}:
            explanation += " 当前证据不足，不能形成有效观察结论。"
        results.append(
            StockScoreMetrics(
                stock_code=code,
                trade_date=trade_date,
                industry_score=round(industry_score, 2),
                company_score=round(company_score, 2),
                trend_score=round(trend_score, 2),
                catalyst_score=round(catalyst_score, 2),
                risk_penalty=risk.penalty,
                raw_score=raw_score,
                source_confidence=source_confidence,
                data_confidence=data_confidence,
                fundamental_confidence=fundamental_confidence,
                news_confidence=news_confidence,
                evidence_confidence=evidence_confidence,
                confidence_level=confidence_level,
                confidence_reasons=confidence_reasons,
                final_score=final_score,
                rating=rating,
                explanation=explanation,
            )
        )
    return results
