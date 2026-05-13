"""Report export utilities with markdown-it-py for proper HTML rendering.

Provides chart-aware, print-optimized HTML generation for Alpha Radar
research reports.  Uses the already-installed ``markdown-it-py`` package
(no new dependencies) for correct handling of tables, code blocks, and
other markdown constructs.
"""

from __future__ import annotations

import json
import re
from html import escape, unescape
from typing import Any


def render_markdown_to_html(content_md: str) -> str:
    """Render markdown to HTML using markdown-it-py.

    Handles tables, code blocks, headings, lists, blockquotes, etc.
    """
    from markdown_it import MarkdownIt

    md = MarkdownIt()
    return md.render(content_md)


def _replace_chart_tags(html: str) -> str:
    """Replace rendered chart-tag paragraphs with descriptive placeholders.

    ``markdown-it-py`` renders ``:::chart {...}:::`` as
    ``<p>:::chart {...}:::</p>``.  This function locates those paragraphs
    and swaps them for styled ``<div class="chart-placeholder">`` elements
    that describe the chart that would appear in the interactive UI.
    """
    pattern = re.compile(r'<p>:::chart\s+(\{.*?\})\s*:::</p>', re.DOTALL)

    def _replace_match(m: re.Match) -> str:
        raw_json = unescape(m.group(1))
        try:
            config = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            return _chart_placeholder_html("图表", {}, "图表配置解析失败")

        chart_type = config.get("type", "")
        symbol = config.get("symbol", "")
        stock_name = config.get("stock_name", "")

        if chart_type == "candle" and symbol:
            name_part = f" ({stock_name})" if stock_name else ""
            return _chart_placeholder_html(
                f"K线图 - {symbol}{name_part}",
                {"标的代码": symbol, "数据来源": "daily_bar"},
                "此图表为交互式 K 线图，在交互式页面中动态渲染。导出版本以数据摘要替代。",
            )
        elif chart_type == "industry_heat":
            period = config.get("period", "7日")
            return _chart_placeholder_html(
                f"行业热度图 ({period})",
                {"数据来源": "industry_heat", "更新频率": "每日"},
                "此图表展示各行业的热度评分分布，在交互式页面中动态渲染。导出版本以数据摘要替代。",
            )
        elif chart_type == "candle":
            return _chart_placeholder_html(
                "K线图",
                {"数据来源": "daily_bar"},
                "此图表为交互式 K 线图，在交互式页面中动态渲染。导出版本以数据摘要替代。",
            )
        elif chart_type == "industry_sankey":
            return _chart_placeholder_html(
                "产业链桑基图",
                {"数据来源": "chain_analysis"},
                "此图表展示产业链上下游关系与热度传导路径。",
            )
        elif chart_type == "trend_pool":
            return _chart_placeholder_html(
                "趋势股票池",
                {"数据来源": "trend_signal"},
                "此表展示趋势评分靠前的候选股票池。",
            )
        elif chart_type == "tenbagger":
            return _chart_placeholder_html(
                "十倍股评估",
                {"数据来源": "tenbagger_thesis"},
                "此图表展示十倍股早期特征的评分雷达图。",
            )
        elif chart_type == "market_brief":
            return _chart_placeholder_html(
                "市场简报",
                {"数据来源": "market_overview"},
                "此图表展示市场整体概况与热点板块。",
            )
        else:
            label = chart_type or "图表"
            return _chart_placeholder_html(f"{label}", {}, "")

    return pattern.sub(_replace_match, html)


def _chart_placeholder_html(
    title: str,
    metadata: dict[str, str] | None = None,
    description: str = "",
) -> str:
    """Build a styled chart placeholder div with title, metadata, and description."""
    md_rows = ""
    if metadata:
        for key, value in metadata.items():
            md_rows += (
                f'<tr>'
                f'<td class="chart-meta-key">{escape(key)}</td>'
                f'<td class="chart-meta-value">{escape(value)}</td>'
                f'</tr>\n'
            )

    desc_block = (
        f'<p class="chart-desc">{escape(description)}</p>' if description else ""
    )

    return (
        f'<div class="chart-placeholder">\n'
        f'  <div class="chart-placeholder-icon">&#x1F4CA;</div>\n'
        f'  <div class="chart-placeholder-title">{escape(title)}</div>\n'
        f'  {desc_block}\n'
        f'  <table class="chart-meta-table">\n'
        f"    {md_rows}"
        f'  </table>\n'
        f'</div>'
    )

    return pattern.sub(_replace_match, html)


def _build_evidence_section(
    evidence_refs: list[dict[str, Any]],
    risk_disclaimer: str,
) -> str:
    """Build the evidence references table and risk disclaimer HTML."""
    parts: list[str] = []

    if evidence_refs:
        parts.append('<section class="evidence-section">')
        parts.append('<h2>参考来源与证据</h2>')
        parts.append('<table class="evidence-table">')
        parts.append(
            "<thead><tr><th>ID</th><th>标题</th><th>来源</th><th>置信度</th></tr></thead>"
        )
        parts.append("<tbody>")
        for ref in evidence_refs[:20]:
            if not isinstance(ref, dict):
                continue
            ref_id = escape(str(ref.get("id", "")))
            ref_title = escape(
                str(ref.get("title") or ref.get("source") or "未命名来源")
            )
            ref_source = escape(
                str(ref.get("source") or ref.get("tool_name") or "-")
            )
            confidence = escape(
                str(ref.get("confidence") or ref.get("source_confidence") or "-")
            )
            parts.append(
                f"<tr>"
                f'<td class="ref-id">[{ref_id}]</td>'
                f"<td>{ref_title}</td>"
                f'<td class="ref-source">{ref_source}</td>'
                f'<td class="ref-confidence">{confidence}</td>'
                f"</tr>"
            )
        parts.append("</tbody></table>")
        parts.append("</section>")

    # Risk disclaimer
    parts.append("<hr />")
    parts.append(
        f'<div class="risk-disclaimer">{escape(risk_disclaimer)}</div>'
    )

    return "\n".join(parts)


def build_print_html(
    title: str,
    content_md: str,
    evidence_refs: list[dict[str, Any]],
    risk_disclaimer: str,
    created_at: str,
    summary: str = "",
) -> str:
    """Build a complete, self-contained HTML page optimized for printing.

    Uses ``markdown-it-py`` to render the report body, replaces chart tags
    with descriptive text placeholders, and wraps everything in a
    print-optimised layout.

    Open this HTML in a browser and use **Ctrl+P** / **Cmd+P** to save as
    PDF.  No external CSS or JS is required -- the page is fully
    self-contained.
    """
    # Render markdown body
    html_body = render_markdown_to_html(content_md)

    # Replace chart placeholders
    html_body = _replace_chart_tags(html_body)

    # Build evidence + disclaimer footer
    footer_html = _build_evidence_section(evidence_refs, risk_disclaimer)

    safe_title = escape(title)
    safe_summary = escape(summary)
    safe_created = escape(created_at)

    summary_block = (
        f'<div class="report-summary">{safe_summary}</div>\n'
        if summary
        else ""
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8" />\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f"<title>{safe_title} - Alpha Radar 投研报告</title>\n"
        "<style>\n"
        "/* ---- Reset & Base ---- */\n"
        "*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }\n"
        "html { font-size: 16px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }\n"
        "body {\n"
        "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,\n"
        "    'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;\n"
        "  color: #1e293b;\n"
        "  line-height: 1.8;\n"
        "  max-width: 210mm;\n"
        "  margin: 0 auto;\n"
        "  padding: 2em;\n"
        "}\n"
        "\n"
        "/* ---- Report Header ---- */\n"
        ".report-header { margin-bottom: 2em; }\n"
        ".report-meta {\n"
        "  display: flex;\n"
        "  justify-content: space-between;\n"
        "  align-items: center;\n"
        "  font-size: 0.8rem;\n"
        "  color: #64748b;\n"
        "  margin-bottom: 1em;\n"
        "  padding-bottom: 0.5em;\n"
        "  border-bottom: 1px solid #e2e8f0;\n"
        "}\n"
        ".report-summary {\n"
        "  background-color: #f8fafc;\n"
        "  border: 1px solid #e2e8f0;\n"
        "  border-radius: 8px;\n"
        "  padding: 1em 1.2em;\n"
        "  margin-bottom: 1.5em;\n"
        "  font-size: 0.95rem;\n"
        "  color: #475569;\n"
        "  line-height: 1.7;\n"
        "}\n"
        "\n"
        "/* ---- Typography ---- */\n"
        "h1 { font-size: 1.8rem; font-weight: 800; margin-top: 0; margin-bottom: 0.5em; border-bottom: 2px solid #1e293b; padding-bottom: 0.3em; }\n"
        "h2 { font-size: 1.35rem; font-weight: 700; margin-top: 1.5em; margin-bottom: 0.5em; color: #0f172a; }\n"
        "h3 { font-size: 1.1rem; font-weight: 700; margin-top: 1.2em; margin-bottom: 0.4em; color: #334155; }\n"
        "h4 { font-size: 1rem; font-weight: 700; margin-top: 1em; margin-bottom: 0.3em; }\n"
        "p { margin-bottom: 0.8em; }\n"
        "strong { font-weight: 700; }\n"
        "em { font-style: italic; }\n"
        "\n"
        "/* ---- Lists ---- */\n"
        "ul, ol { margin: 0.5em 0 0.8em 1.8em; }\n"
        "li { margin-bottom: 0.3em; }\n"
        "\n"
        "/* ---- Tables ---- */\n"
        "table {\n"
        "  width: 100%;\n"
        "  border-collapse: collapse;\n"
        "  margin: 1em 0;\n"
        "  font-size: 0.9rem;\n"
        "}\n"
        "th, td {\n"
        "  border: 1px solid #cbd5e1;\n"
        "  padding: 0.5em 0.75em;\n"
        "  text-align: left;\n"
        "  vertical-align: top;\n"
        "}\n"
        "th {\n"
        "  background-color: #f1f5f9;\n"
        "  font-weight: 700;\n"
        "  color: #0f172a;\n"
        "}\n"
        "tr:nth-child(even) { background-color: #f8fafc; }\n"
        "\n"
        "/* ---- Code ---- */\n"
        "code {\n"
        "  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;\n"
        "  font-size: 0.85em;\n"
        "  background-color: #f1f5f9;\n"
        "  padding: 0.15em 0.4em;\n"
        "  border-radius: 3px;\n"
        "}\n"
        "pre {\n"
        "  background-color: #f8fafc;\n"
        "  border: 1px solid #e2e8f0;\n"
        "  border-radius: 6px;\n"
        "  padding: 1em;\n"
        "  overflow-x: auto;\n"
        "  margin: 0.8em 0;\n"
        "}\n"
        "pre code { background: none; padding: 0; border-radius: 0; }\n"
        "\n"
        "/* ---- Blockquote ---- */\n"
        "blockquote {\n"
        "  border-left: 4px solid #3b82f6;\n"
        "  padding: 0.5em 1em;\n"
        "  margin: 0.8em 0;\n"
        "  background-color: #f8fafc;\n"
        "  color: #475569;\n"
        "}\n"
        "\n"
        "/* ---- Horizontal Rule ---- */\n"
        "hr { border: none; border-top: 1px solid #e2e8f0; margin: 1.5em 0; }\n"
        "\n"
        "/* ---- Chart Placeholder ---- */\n"
        ".chart-placeholder {\n"
        "  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);\n"
        "  border: 1.5px solid #cbd5e1;\n"
        "  border-radius: 10px;\n"
        "  padding: 1.5em 1.2em;\n"
        "  text-align: center;\n"
        "  color: #334155;\n"
        "  margin: 1.2em 0;\n"
        "  box-shadow: 0 1px 3px rgba(0,0,0,0.04);\n"
        "}\n"
        ".chart-placeholder-icon { font-size: 1.8rem; margin-bottom: 0.3em; }\n"
        ".chart-placeholder-title {\n"
        "  font-size: 1.05rem;\n"
        "  font-weight: 700;\n"
        "  color: #0f172a;\n"
        "  margin-bottom: 0.4em;\n"
        "}\n"
        ".chart-desc {\n"
        "  font-size: 0.85rem;\n"
        "  color: #64748b;\n"
        "  margin-bottom: 0.6em;\n"
        "  line-height: 1.5;\n"
        "}\n"
        ".chart-meta-table {\n"
        "  width: auto;\n"
        "  margin: 0 auto;\n"
        "  border-collapse: collapse;\n"
        "  font-size: 0.8rem;\n"
        "}\n"
        ".chart-meta-table td {\n"
        "  border: none;\n"
        "  padding: 0.15em 0.8em;\n"
        "}\n"
        ".chart-meta-key {\n"
        "  font-weight: 700;\n"
        "  color: #475569;\n"
        "  text-align: right;\n"
        "}\n"
        ".chart-meta-value {\n"
        "  font-weight: 600;\n"
        "  color: #64748b;\n"
        "  text-align: left;\n"
        "}\n"
        "\n"
        "/* ---- Evidence Table ---- */\n"
        ".evidence-section { margin-top: 2em; }\n"
        ".evidence-table { width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 0.85rem; }\n"
        ".evidence-table th { background-color: #1e293b; color: #ffffff; font-weight: 700; padding: 0.4em 0.6em; }\n"
        ".evidence-table td { padding: 0.4em 0.6em; border: 1px solid #cbd5e1; }\n"
        ".evidence-table .ref-id { font-weight: 700; color: #334155; white-space: nowrap; }\n"
        ".evidence-table .ref-source { color: #64748b; font-size: 0.8rem; }\n"
        ".evidence-table .ref-confidence { color: #64748b; font-size: 0.8rem; }\n"
        "\n"
        "/* ---- Risk Disclaimer ---- */\n"
        ".risk-disclaimer {\n"
        "  font-size: 0.8rem;\n"
        "  color: #64748b;\n"
        "  text-align: center;\n"
        "  margin-top: 2em;\n"
        "  padding: 1em;\n"
        "  border: 1px solid #e2e8f0;\n"
        "  border-radius: 6px;\n"
        "  background-color: #fafafa;\n"
        "}\n"
        "\n"
        "/* ---- Print Styles ---- */\n"
        "@media print {\n"
        "  @page {\n"
        "    margin: 15mm 20mm;\n"
        "    size: A4;\n"
        "  }\n"
        "  html { font-size: 12pt; }\n"
        "  body {\n"
        "    padding: 0;\n"
        "    max-width: none;\n"
        "    color: #000;\n"
        "  }\n"
        "  h1 { font-size: 18pt; border-bottom-color: #000; }\n"
        "  h2 { font-size: 14pt; }\n"
        "  h3 { font-size: 12pt; }\n"
        "  p, li { font-size: 10.5pt; line-height: 1.6; }\n"
        "  table { font-size: 9pt; }\n"
        "  .chart-placeholder {\n"
        "    border: 1px solid #94a3b8;\n"
        "    background: #f1f5f9;\n"
        "    -webkit-print-color-adjust: exact;\n"
        "    print-color-adjust: exact;\n"
        "    box-shadow: none;\n"
        "  }\n"
        "  .chart-placeholder-icon { font-size: 18pt; }\n"
        "  .chart-placeholder-title { font-size: 11pt; }\n"
        "  .chart-desc { font-size: 9pt; }\n"
        "  .chart-meta-table td { font-size: 8pt; padding: 0.1em 0.6em; }\n"
        "  .evidence-table th {\n"
        "    background-color: #1e293b !important;\n"
        "    -webkit-print-color-adjust: exact;\n"
        "    print-color-adjust: exact;\n"
        "  }\n"
        "  .report-summary {\n"
        "    border: 1px solid #cbd5e1;\n"
        "    background: #f8fafc;\n"
        "  }\n"
        "  tr:nth-child(even) {\n"
        "    background-color: #f8fafc !important;\n"
        "    -webkit-print-color-adjust: exact;\n"
        "    print-color-adjust: exact;\n"
        "  }\n"
        "  .risk-disclaimer {\n"
        "    border: 1px solid #cbd5e1;\n"
        "  }\n"
        "  a { color: inherit; text-decoration: none; }\n"
        "  pre {\n"
        "    white-space: pre-wrap;\n"
        "    word-break: break-all;\n"
        "    border: 1px solid #cbd5e1;\n"
        "  }\n"
        "  blockquote { border-left-color: #3b82f6; }\n"
        "  .report-meta { border-bottom-color: #94a3b8; }\n"
        "}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="report-header">\n'
        f"  <h1>{safe_title}</h1>\n"
        '  <div class="report-meta">\n'
        "    <span>Alpha Radar 投研报告</span>\n"
        f"    <span>{safe_created}</span>\n"
        "  </div>\n"
        f"{summary_block}"
        "</div>\n"
        '<div class="report-body">\n'
        f"{html_body}\n"
        "</div>\n"
        '<div class="report-footer">\n'
        f"{footer_html}\n"
        "</div>\n"
        "</body>\n"
        "</html>"
    )
