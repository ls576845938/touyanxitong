"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type DailyReport, type ReportSummary } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

export default function ReportPage() {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.latestReport(), api.reports()])
      .then(([latest, reportRows]) => {
        setReport(latest);
        setReports(reportRows);
      })
      .catch((err: Error) => setError(`日报读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载每日简报" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;
  if (!report) return <div className="page-shell"><ErrorState message="日报为空" /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="label">Report Archive</div>
            <h2 className="mt-1 text-lg font-semibold">历史日报</h2>
          </div>
          <div className="label">共 {reports.length} 份</div>
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {reports.map((item) => (
            <button
              key={item.report_date}
              type="button"
              onClick={() => api.reportByDate(item.report_date).then(setReport).catch((err: Error) => setError(`日报读取失败：${err.message}`))}
              className={`h-10 shrink-0 rounded-md border px-3 text-sm ${
                report.report_date === item.report_date ? "border-mint bg-mint text-white" : "border-line bg-white text-ink hover:border-mint"
              }`}
            >
              {item.report_date}
            </button>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="label">Daily Report</div>
        <h1 className="mt-2 text-2xl font-semibold">{report.title}</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">{report.market_summary}</p>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <StatusCard label="数据质量" value={report.data_quality.status} detail={`FAIL ${report.data_quality.summary.fail_count} / WARN ${report.data_quality.summary.warn_count}`} />
        <StatusCard label="研究股票池" value={`${report.research_universe.summary.eligible_count}/${report.research_universe.summary.stock_count}`} detail={`准入率 ${Math.round(report.research_universe.summary.eligible_ratio * 100)}%`} />
        <StatusCard label="评分可信度" value={averageConfidence(report.top_trend_stocks)} detail={`研究准入 ${report.top_trend_stocks.filter((row) => row.research_gate?.passed).length}/${report.top_trend_stocks.length}`} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="panel p-5">
          <h2 className="text-lg font-semibold">观察池变化</h2>
          <div className="mt-4 space-y-3">
            {report.watchlist_changes.new_entries.slice(0, 8).map((item) => (
              <Link key={`new-${item.code}`} href={`/stocks/${encodeURIComponent(item.code)}?from=/report`} className="block rounded-md border border-line p-3 hover:border-mint">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{item.name}<span className="label ml-2">{item.code}</span></div>
                  <div className="mono text-sm font-semibold text-mint">{item.final_score?.toFixed(1) ?? "-"}</div>
                </div>
                <div className="label mt-1">{marketLabel(item.market)} / {boardLabel(item.board)} / {item.rating ?? "-"}</div>
              </Link>
            ))}
            {report.watchlist_changes.new_entries.length === 0 ? <div className="text-sm text-slate-600">今日没有新进观察池。</div> : null}
          </div>
        </div>
        <div className="panel p-5">
          <h2 className="text-lg font-semibold">研究准入与数据质量</h2>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            {report.research_universe.segments.slice(0, 6).map((segment) => (
              <div key={`${segment.market}-${segment.board}`} className="rounded-md border border-line bg-slate-50 p-3">
                <div className="font-medium">{marketLabel(segment.market)} / {boardLabel(segment.board)}</div>
                <div className="label mt-1">{segment.eligible_count}/{segment.stock_count} 可研究，准入率 {Math.round(segment.eligible_ratio * 100)}%</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="panel p-5">
          <h2 className="text-lg font-semibold">观察池候选</h2>
          <div className="mt-4 space-y-3">
            {report.new_watchlist_stocks.slice(0, 10).map((item) => (
              <Link key={item.code} href={`/stocks/${encodeURIComponent(item.code)}?from=/report`} className="block rounded-md border border-line p-3 hover:border-mint">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{item.name}<span className="label ml-2">{item.code}</span></div>
                  <div className="mono text-sm font-semibold text-mint">{Number(item.final_score).toFixed(1)}</div>
                </div>
                <div className="label mt-1">{item.industry} / {item.rating} / 可信度 {formatPct(item.confidence?.combined_confidence)} / 资讯 {newsStatusLabel(item.news_evidence_status)}</div>
              </Link>
            ))}
          </div>
        </div>
        <div className="panel p-5">
          <h2 className="text-lg font-semibold">风险预警</h2>
          <div className="mt-4 space-y-3">
            {report.risk_alerts.length ? report.risk_alerts.map((alert) => (
              <div key={alert} className="rounded-md border border-rose/30 bg-rose/5 p-3 text-sm leading-6 text-slate-700">{alert}</div>
            )) : <div className="text-sm text-slate-600">今日没有高风险扣分样本，但仍需人工核验。</div>}
          </div>
        </div>
      </section>

      <section className="panel p-5">
        <h2 className="text-lg font-semibold">完整简报</h2>
        <pre className="mt-4 whitespace-pre-wrap rounded-md bg-slate-50 p-4 text-sm leading-7 text-slate-800">
          {report.full_markdown}
        </pre>
      </section>
    </div>
  );
}

function StatusCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="panel p-5">
      <div className="label">{label}</div>
      <div className="mono mt-2 text-2xl font-semibold">{value}</div>
      <div className="mt-2 text-sm text-slate-600">{detail}</div>
    </div>
  );
}

function averageConfidence(rows: DailyReport["top_trend_stocks"]) {
  const values = rows
    .map((row) => row.confidence?.combined_confidence)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!values.length) return "-";
  return `${Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100)}%`;
}

function formatPct(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "-";
}

function newsStatusLabel(status: string | null | undefined) {
  if (status === "active") return "活跃";
  if (status === "partial") return "部分";
  return "缺失";
}
