"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Filter } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { api, type TrendPoolRow } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

export default function TrendPage() {
  const [rows, setRows] = useState<TrendPoolRow[]>([]);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [rating, setRating] = useState("全部");
  const [breakoutOnly, setBreakoutOnly] = useState(false);
  const [rsTopOnly, setRsTopOnly] = useState(false);
  const [researchOnly, setResearchOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.trendPool({ market, board: market === "A" ? board : "all", researchUniverseOnly: researchOnly, limit: 500 })
      .then(setRows)
      .catch((err: Error) => setError(`趋势池读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board, researchOnly]);

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      if (rating !== "全部" && row.rating !== rating) return false;
      if (breakoutOnly && !row.is_breakout_250d) return false;
      if (rsTopOnly && row.relative_strength_rank > Math.max(1, Math.ceil(rows.length * 0.1))) return false;
      return true;
    });
  }, [rows, rating, breakoutOnly, rsTopOnly]);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载趋势股票池" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="label">Trend Pool</div>
        <h1 className="mt-2 text-2xl font-semibold">趋势增强股票池</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          按最终评分、产业分、趋势分和风险扣分筛选观察候选，不构成任何交易建议。
        </p>
      </section>

      <section className="panel p-4">
        <div className="flex flex-wrap items-center gap-2">
          {MARKET_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setMarket(option);
                if (option !== "A") setBoard("all");
              }}
              className={`h-10 rounded-md border px-4 text-sm ${
                market === option ? "border-mint bg-mint text-white" : "border-line bg-white text-ink hover:border-mint"
              }`}
            >
              {marketLabel(option)}
            </button>
          ))}
        </div>
        {market === "A" ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {A_BOARD_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setBoard(option)}
                className={`h-9 rounded-md border px-3 text-sm ${
                  board === option ? "border-amber bg-amber text-white" : "border-line bg-white text-ink hover:border-amber"
                }`}
              >
                {boardLabel(option)}
              </button>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><Filter size={16} />筛选器</div>
          <select className="h-10 rounded-md border border-line bg-white px-3 text-sm" value={rating} onChange={(event) => setRating(event.target.value)}>
            {["全部", "强观察", "观察", "弱观察", "仅记录", "排除"].map((item) => <option key={item}>{item}</option>)}
          </select>
          <label className="flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm">
            <input type="checkbox" checked={breakoutOnly} onChange={(event) => setBreakoutOnly(event.target.checked)} />
            只看突破250日新高
          </label>
          <label className="flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm">
            <input type="checkbox" checked={rsTopOnly} onChange={(event) => setRsTopOnly(event.target.checked)} />
            相对强度前10%
          </label>
          <label className="flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm">
            <input type="checkbox" checked={researchOnly} onChange={(event) => setResearchOnly(event.target.checked)} />
            仅研究股票池
          </label>
          <div className="label ml-auto">当前 {filtered.length} / {rows.length}</div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1240px] text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3">股票</th>
                <th className="px-4 py-3">市场</th>
                <th className="px-4 py-3">产业</th>
                <th className="px-4 py-3">最终评分</th>
                <th className="px-4 py-3">产业</th>
                <th className="px-4 py-3">公司</th>
                <th className="px-4 py-3">趋势</th>
                <th className="px-4 py-3">催化</th>
                <th className="px-4 py-3">风险</th>
                <th className="px-4 py-3">形态</th>
                <th className="px-4 py-3">准入</th>
                <th className="px-4 py-3">可信度</th>
                <th className="px-4 py-3">证据状态</th>
                <th className="px-4 py-3">证据链</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr key={row.code} className="border-t border-line align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium">{row.name}</div>
                    <div className="label">{row.code}</div>
                  </td>
                  <td className="px-4 py-3">{marketLabel(row.market)}<div className="label">{boardLabel(row.board)} / {row.exchange}</div></td>
                  <td className="px-4 py-3">{row.industry}<div className="label">{row.industry_level2}</div></td>
                  <td className="px-4 py-3"><ScoreBadge score={row.final_score} rating={row.rating} /></td>
                  <td className="mono px-4 py-3">{row.industry_score.toFixed(1)}</td>
                  <td className="mono px-4 py-3">{row.company_score.toFixed(1)}</td>
                  <td className="mono px-4 py-3">{row.trend_score.toFixed(1)}</td>
                  <td className="mono px-4 py-3">{row.catalyst_score.toFixed(1)}</td>
                  <td className="mono px-4 py-3">{row.risk_penalty.toFixed(1)}</td>
                  <td className="px-4 py-3">
                    <div className="space-y-1">
                      <Flag active={row.is_ma_bullish} label="多头" />
                      <Flag active={row.is_breakout_120d} label="120新高" />
                      <Flag active={row.is_breakout_250d} label="250新高" />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Flag active={row.research_gate?.passed ?? row.research_eligible} label={row.research_gate?.passed ?? row.research_eligible ? "通过" : "复核"} />
                    <div className="mt-1 max-w-[160px] text-xs leading-5 text-slate-500">{(row.research_gate?.reasons ?? []).slice(0, 1).join("")}</div>
                  </td>
                  <td className="px-4 py-3">
                    <ConfidenceStack row={row} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="space-y-1 text-xs">
                      <StatusPill label={`数据源 ${formatPct(row.confidence?.source_confidence)}`} active={(row.confidence?.source_confidence ?? 0) >= 0.6} />
                      <StatusPill label={`基本面 ${fundamentalLabel(row)}`} active={row.fundamental_summary?.status === "complete"} />
                      <StatusPill label={`资讯 ${newsStatusLabel(row.news_evidence_status)}`} active={row.news_evidence_status === "active"} />
                    </div>
                  </td>
                  <td className="px-4 py-3"><Link href={`/stocks/${encodeURIComponent(row.code)}?from=/trend`} className="text-mint">查看</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Flag({ active, label }: { active: boolean; label: string }) {
  return (
    <span className={`inline-flex rounded-md px-2 py-1 text-xs ${active ? "bg-mint text-white" : "bg-slate-100 text-slate-500"}`}>
      {label}
    </span>
  );
}

function ConfidenceStack({ row }: { row: TrendPoolRow }) {
  const confidence = row.confidence;
  return (
    <div className="space-y-1 text-xs">
      <div className="font-semibold">{confidence?.level ?? "unknown"} / {formatPct(confidence?.combined_confidence)}</div>
      <div className="text-slate-500">data {formatPct(confidence?.data_confidence)} / news {formatPct(confidence?.news_confidence)}</div>
    </div>
  );
}

function StatusPill({ active, label }: { active: boolean; label: string }) {
  return <div className={`inline-flex rounded px-2 py-1 ${active ? "bg-mint/15 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{label}</div>;
}

function formatPct(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "-";
}

function fundamentalLabel(row: TrendPoolRow) {
  if (!row.fundamental_summary) return "-";
  if (row.fundamental_summary.status === "complete") return `完整 ${formatPct(row.fundamental_summary.confidence)}`;
  return `${row.fundamental_summary.missing_items.join("/") || "待补"} ${formatPct(row.fundamental_summary.confidence)}`;
}

function newsStatusLabel(status: TrendPoolRow["news_evidence_status"]) {
  if (status === "active") return "活跃";
  if (status === "partial") return "部分";
  return "缺失";
}
