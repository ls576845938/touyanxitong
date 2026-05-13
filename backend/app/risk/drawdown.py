"""Drawdown (Circuit Breaker) Risk Rules.

Determines risk budget multipliers and plan-creation restrictions based on
the current portfolio drawdown percentage.  Rules are tiered: the deeper the
drawdown, the smaller the allowable risk budget and the tighter the
restrictions on creating new active plans.

Rules are stored as JSON in ``RiskRule.drawdown_rules_json`` and fall back
to ``DEFAULT_DRAWDOWN_RULES`` when no custom rules are configured.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Default drawdown tiers (matching the design spec for MVP 3.2)
# ---------------------------------------------------------------------------

DEFAULT_DRAWDOWN_RULES: list[dict[str, Any]] = [
    {
        "max_drawdown_pct": 3.0,
        "risk_multiplier": 1.0,
        "label": "正常",
        "description": "正常风险预算",
    },
    {
        "max_drawdown_pct": 5.0,
        "risk_multiplier": 0.8,
        "label": "谨慎",
        "description": "提示谨慎，避免随意新增计划",
    },
    {
        "max_drawdown_pct": 8.0,
        "risk_multiplier": 0.5,
        "label": "收缩",
        "description": "单笔风险预算减半",
    },
    {
        "max_drawdown_pct": 10.0,
        "risk_multiplier": 0.3,
        "label": "防御",
        "description": "总风险资产仓位上限降低，不建议新增active plan",
    },
    {
        "max_drawdown_pct": 15.0,
        "risk_multiplier": 0.1,
        "label": "冷静期",
        "description": "处于回撤冷静期，只允许观察，不允许创建active plan",
    },
    {
        "max_drawdown_pct": 999.0,
        "risk_multiplier": 0.05,
        "label": "防守期",
        "description": "严重回撤，只允许观察，不允许任何新计划",
    },
]

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_DRAWDOWN_WARN_THRESHOLD_1 = 8.0
_DRAWDOWN_WARN_THRESHOLD_2 = 10.0
_DRAWDOWN_WARN_THRESHOLD_3 = 15.0


def get_drawdown_multiplier(
    current_drawdown_pct: float,
    rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the risk multiplier and status for the current drawdown level.

    Parameters
    ----------
    current_drawdown_pct:
        The portfolio's current drawdown percentage (e.g. ``5.0`` for 5%).
        Must be a non-negative number.
    rules:
        Optional list of tier dicts.  Each dict must contain at least
        ``max_drawdown_pct``, ``risk_multiplier``, ``label``, and
        ``description``.  Falls back to ``DEFAULT_DRAWDOWN_RULES`` when
        ``None``.

    Returns
    -------
    dict with keys:
        - ``multiplier`` (float): the risk budget multiplier for this tier.
        - ``label`` (str): short human-readable tier name.
        - ``description`` (str): longer explanation of the tier.
        - ``warnings`` (list[str]): contextual warnings for the current
          drawdown level (may be empty).
        - ``current_drawdown_pct`` (float): echoed input.
    """
    rules = rules or DEFAULT_DRAWDOWN_RULES

    # Sort by threshold ascending so the first match is the *most
    # restrictive* tier that still includes the current value.
    sorted_tiers = sorted(rules, key=lambda r: r["max_drawdown_pct"])

    for tier in sorted_tiers:
        if current_drawdown_pct <= tier["max_drawdown_pct"]:
            return _build_result(current_drawdown_pct, tier)

    # Fallback: nothing matched (shouldn't happen with the 999.0 sentinel).
    return {
        "multiplier": 0.05,
        "label": "极端",
        "description": "严重回撤，只允许观察，不允许任何新计划",
        "warnings": ["严重回撤，强烈建议进入防守期。"],
        "current_drawdown_pct": current_drawdown_pct,
    }


def should_block_new_active_plan(current_drawdown_pct: float) -> tuple[bool, str]:
    """Check whether new *active* plans should be blocked due to drawdown.

    Parameters
    ----------
    current_drawdown_pct:
        Portfolio's current drawdown percentage.

    Returns
    -------
    (blocked, reason):
        - ``blocked`` is ``True`` when the drawdown exceeds a threshold
          that warrants blocking.
        - ``reason`` is a human-readable explanation (empty when not
          blocked).
    """
    if current_drawdown_pct > 15.0:
        return True, "当前回撤超过15%，处于防守期。不允许创建新的active plan。"
    if current_drawdown_pct > 10.0:
        return True, (
            "当前回撤超过10%，处于冷静期。"
            "建议只创建draft，待回撤恢复后再考虑activate。"
        )
    return False, ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_result(
    current_drawdown_pct: float,
    tier: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the result dict for a matched tier, including warnings."""
    warnings: list[str] = []

    if current_drawdown_pct >= _DRAWDOWN_WARN_THRESHOLD_1:
        warnings.append("回撤已达8%以上，风险预算已显著降低")
    if current_drawdown_pct >= _DRAWDOWN_WARN_THRESHOLD_2:
        warnings.append("处于回撤冷静期。建议暂停创建新的active计划，仅保留draft。")
    if current_drawdown_pct > _DRAWDOWN_WARN_THRESHOLD_3:
        warnings.append("严重回撤，强烈建议进入防守期。")

    return {
        "multiplier": tier["risk_multiplier"],
        "label": tier["label"],
        "description": tier["description"],
        "warnings": warnings,
        "current_drawdown_pct": current_drawdown_pct,
    }
