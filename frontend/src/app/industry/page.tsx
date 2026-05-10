"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { IndustryHeatChart } from "@/components/IndustryHeatChart";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type IndustryRadarRow } from "@/lib/api";
import { MARKET_OPTIONS, marketLabel } from "@/lib/markets";

export default function IndustryPage() {
  const [rows, setRows] = useState<IndustryRadarRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [market, setMarket] = useState("ALL");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.industryRadar({ market })
      .then(setRows)
      .catch((err: Error) => setError(`产业雷达读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market]);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载产业雷达" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="label">Industry Radar</div>
            <h1 className="mt-2 text-2xl font-semibold">产业热度雷达</h1>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              综合热度不是买卖建议，也不是单纯新闻分；它把资讯热度、行情覆盖、关联股票和观察池数量合成赛道研究线索。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/industry/chain" className="rounded-md border border-line px-4 py-2 text-sm hover:border-mint">查看产业链地图</Link>
            <Link href="/industry/review" className="rounded-md border border-line px-4 py-2 text-sm hover:border-mint">查看赛道复盘</Link>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {MARKET_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMarket(option)}
              className={`rounded-md border px-3 py-2 text-sm ${
                market === option ? "border-mint bg-mint text-white" : "border-line bg-white hover:border-mint"
              }`}
            >
              {marketLabel(option)}
            </button>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <IndustryHeatChart rows={rows} />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((row) => (
          <article key={row.industry_id} className="panel p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link href={`/industry/${row.industry_id}${market === "ALL" ? "" : `?market=${market}`}`} className="text-lg font-semibold hover:text-mint">{row.name}</Link>
                <div className="label mt-1">{row.market_label} / {row.trade_date ?? "-"}</div>
              </div>
              <div className="text-right">
                <div className="label mb-1">综合热度</div>
                <div className={`mono rounded-md px-3 py-1 text-sm font-semibold ${heatScoreClass(row)}`}>{formatNumber(row.heat_score)}</div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className={`rounded-md px-2 py-1 text-xs font-semibold ${evidenceStatusClass(row)}`}>
                {evidenceStatusLabel(row)}
              </span>
              {row.heat_score === 0 ? (
                <span className="text-xs text-slate-600">{heatZeroReason(row)}</span>
              ) : null}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 text-sm lg:grid-cols-4">
              <MiniMetric label="综合热度" value={formatNumber(row.heat_score)} />
              <MiniMetric label="资讯热度" value={formatNumber(newsHeat(row))} />
              <MiniMetric label="结构热度" value={formatNumber(row.structure_heat_score)} />
              <MiniMetric label="趋势宽度" value={formatRatio(row.trend_breadth)} />
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-sm lg:grid-cols-4">
              <MiniMetric label="关联股票" value={formatCount(row.related_stock_count)} />
              <MiniMetric label="观察池数量" value={formatCount(row.watch_stock_count)} />
              <MiniMetric label="突破宽度" value={formatRatio(row.breakout_breadth)} />
              <MiniMetric label="已评分股票" value={formatCount(row.scored_stock_count)} />
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <MiniMetric label="1日资讯" value={formatNumber(row.heat_1d)} />
              <MiniMetric label="7日资讯" value={formatNumber(row.heat_7d)} />
              <MiniMetric label="30日资讯" value={formatNumber(row.heat_30d)} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {row.top_keywords.map((keyword) => (
                <span key={keyword} className="rounded-md border border-line px-2 py-1 text-xs text-slate-700">{keyword}</span>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <MiniMetric label="7日变化" value={formatSigned(row.heat_change_7d)} />
              <MiniMetric label="30日变化" value={formatSigned(row.heat_change_30d)} />
              <MiniMetric label={row.market === "ALL" ? "全市场基准" : "全市场热度"} value={formatNumber(globalHeat(row))} />
            </div>
            {row.market !== "ALL" && (
              <div className="label mt-3">当前综合热度已按 {row.market_label} 的关联股票和观察池数量调整；全市场资讯热度 {formatNumber(globalHeat(row))}。</div>
            )}
            {row.heat_score === 0 ? (
              <p className="mt-4 rounded-md border border-line bg-slate-50 p-3 text-sm leading-6 text-slate-600">{heatZeroReason(row)}</p>
            ) : (
              <p className="mt-4 text-sm leading-6 text-slate-600">{row.explanation}</p>
            )}
          </article>
        ))}
      </section>
    </div>
  );
}

function globalHeat(row: IndustryRadarRow) {
  return isFiniteNumber(row.global_heat_score) ? row.global_heat_score : row.heat_score;
}

function newsHeat(row: IndustryRadarRow) {
  return isFiniteNumber(row.news_heat_score) ? row.news_heat_score : globalHeat(row);
}

function evidenceStatusLabel(row: IndustryRadarRow) {
  const status = normalizeEvidenceStatus(row);
  if (status === "news_active") return "资讯活跃";
  if (status === "structure_active") return "结构活跃";
  if (status === "mapped_only") return "仅有映射";
  return "无证据";
}

function evidenceStatusClass(row: IndustryRadarRow) {
  const status = normalizeEvidenceStatus(row);
  if (status === "news_active") return "bg-mint text-white";
  if (status === "structure_active") return "bg-slate-900 text-white";
  if (status === "mapped_only") return "bg-amber text-white";
  return "bg-slate-100 text-slate-600";
}

function heatScoreClass(row: IndustryRadarRow) {
  return row.heat_score === 0 ? "bg-slate-100 text-slate-600" : "bg-mint text-white";
}

function normalizeEvidenceStatus(row: IndustryRadarRow) {
  const status = row.evidence_status;
  if (status === "资讯活跃" || status === "news_active") return "news_active";
  if (status === "结构活跃" || status === "structure_active") return "structure_active";
  if (status === "仅有映射" || status === "mapped_only") return "mapped_only";
  if (status === "无证据" || status === "no_evidence") return "no_evidence";
  if (row.heat_score === 0) return row.related_stock_count > 0 ? "mapped_only" : "no_evidence";
  if (isFiniteNumber(newsHeat(row)) && newsHeat(row) > 0) return "news_active";
  return "structure_active";
}

function heatZeroReason(row: IndustryRadarRow) {
  if (row.zero_heat_reason) return row.zero_heat_reason;
  if (row.related_stock_count > 0) return `当前没有资讯、观察池或趋势突破证据，仅保留 ${row.related_stock_count} 只关联股票映射。`;
  return "当前没有资讯、结构化趋势、观察池或关联股票证据。";
}

function formatNumber(value: number | null | undefined) {
  return isFiniteNumber(value) ? value.toFixed(1) : "-";
}

function formatRatio(value: number | null | undefined) {
  return isFiniteNumber(value) ? `${Math.round(value * 100)}%` : "-";
}

function formatCount(value: number | null | undefined) {
  return isFiniteNumber(value) ? String(value) : "-";
}

function formatSigned(value: number | null | undefined) {
  if (!isFiniteNumber(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{value}</div>
    </div>
  );
}
