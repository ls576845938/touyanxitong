"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { MetricTile, QualityBanner, RecordList, SectionCard, TonePill, WorkbenchHeader, WorkbenchLink } from "@/components/Workbench";
import { api, type DailyReport, type TrendPoolRow, type WatchlistTimeline } from "@/lib/api";
import { collectQualityFlags, formatDate, formatPct, observationLevel, toneFromStatus, uniqueTexts } from "@/lib/research-workbench";

export default function PortfolioDashboardPage() {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistTimeline | null>(null);
  const [pool, setPool] = useState<TrendPoolRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.allSettled([api.latestReport(), api.watchlistTimeline({ limit: 8 }), api.trendPool({ researchUniverseOnly: true, limit: 20 })])
      .then(([reportResult, watchlistResult, poolResult]) => {
        if (cancelled) return;
        if (reportResult.status === "rejected") {
          setError(`组合看板读取失败：${reportResult.reason instanceof Error ? reportResult.reason.message : "unknown error"}`);
          return;
        }
        setReport(reportResult.value);
        setWatchlist(watchlistResult.status === "fulfilled" ? watchlistResult.value : null);
        setPool(poolResult.status === "fulfilled" ? poolResult.value : []);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const flags = useMemo(() => collectQualityFlags(report?.data_quality.status, report?.full_markdown), [report?.data_quality.status, report?.full_markdown]);
  const records = useMemo(() => {
    return (watchlist?.timeline ?? []).slice(0, 6).map((item) => ({
      date: item.trade_date,
      title: `观察组合快照 ${item.summary.latest_watch_count} 只`,
      detail: `新进 ${item.summary.new_count} / 上调 ${item.summary.upgraded_count} / 降级 ${item.summary.downgraded_count} / 移出 ${item.summary.removed_count}`,
      tone: item.summary.downgraded_count > 0 || item.summary.removed_count > 0 ? ("warn" as const) : ("neutral" as const),
      tags: ["观察组合", item.summary.new_count > 0 ? "有新增" : "无新增"]
    }));
  }, [watchlist]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载组合观察看板" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!report) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="暂无组合看板数据" /></div>;

  const avgScore = pool.length ? pool.reduce((sum, row) => sum + row.final_score, 0) / pool.length : 0;
  const topIndustries = buildIndustrySummary(pool);
  const riskItems = uniqueTexts([
    ...report.risk_alerts,
    ...report.data_quality.issues.filter((issue) => issue.severity === "FAIL").slice(0, 4).map((issue) => `${issue.name} ${issue.code}：${issue.message}`)
  ]);

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <WorkbenchHeader
          eyebrow="Portfolio Dashboard"
          title="组合观察看板"
          summary="这是研究辅助视角下的组合观察板，不代表实盘持仓指令。先看摘要，再回到证据链、风险与观察记录。"
          actions={
            <>
              <WorkbenchLink href="/portfolio/trade-journal" label="观察日志" />
              <WorkbenchLink href="/research/stock-pool" label="研究股票池" />
            </>
          }
        />

        <QualityBanner flags={flags} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="结论摘要" value={report.title} detail={`报告日 ${formatDate(report.report_date)}`} />
          <MetricTile label="观察规模" value={watchlist?.latest?.summary.latest_watch_count ?? 0} detail="最新观察池规模" />
          <MetricTile label="平均分" value={avgScore ? avgScore.toFixed(1) : "--"} detail={`研究宇宙准入 ${report.research_universe.summary.eligible_count} / ${report.research_universe.summary.stock_count}`} />
          <MetricTile label="数据门控" value={report.data_quality.status} tone={toneFromStatus(report.data_quality.status)} detail={`FAIL ${report.data_quality.summary.fail_count} / WARN ${report.data_quality.summary.warn_count}`} />
        </section>

        <SectionCard title="结论摘要" subtitle="先给观察组合的当前重点。">
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <div className="rounded-2xl bg-slate-50 p-5">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">市场摘要</div>
              <p className="mt-3 text-sm leading-7 text-slate-700">{report.market_summary}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                {topIndustries.map((item) => <TonePill key={item.label} label={`${item.label} ${item.count}`} tone="pass" />)}
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 p-5">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">观察偏向</div>
              <div className="mt-4 space-y-3">
                <Info label="高等级观察" value={String(pool.filter((row) => observationLevel(row.final_score, row.confidence?.level) === "重点观察").length)} />
                <Info label="新增观察" value={String(watchlist?.latest?.summary.new_count ?? 0)} />
                <Info label="风险提醒" value={String(report.risk_alerts.length)} />
                <Info label="正式通过率" value={formatPct(report.research_universe.summary.eligible_ratio, 0)} />
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="证据链" subtitle="组合观察来自趋势池、观察池和日报交叉验证。">
          <div className="grid gap-4">
            {pool.slice(0, 10).map((row) => (
              <Link key={row.code} href={`/research/security/${encodeURIComponent(row.code)}`} className="block rounded-2xl border border-slate-200 p-5 transition-colors hover:border-slate-300">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-lg font-bold text-slate-900">{row.name} <span className="text-sm font-semibold text-slate-400">{row.code}</span></div>
                    <div className="mt-1 text-xs text-slate-500">{row.industry} / {row.industry_level2}</div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <TonePill label={row.rating} tone={row.final_score >= 75 ? "pass" : "neutral"} />
                    <TonePill label={observationLevel(row.final_score, row.confidence?.level)} tone={row.confidence?.level === "high" ? "pass" : "neutral"} />
                  </div>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-600">{row.explanation}</p>
              </Link>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="风险提示" subtitle="任何数据质量 FAIL 和日报风险提醒都必须前置。">
          <div className="space-y-3">
            {riskItems.map((item) => (
              <div key={item} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900">
                {item}
              </div>
            ))}
            {riskItems.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">暂无组合级风险提醒。</div>}
          </div>
        </SectionCard>

        <SectionCard title="操作记录" subtitle="记录观察池变化，不映射为确定性调仓建议。">
          <RecordList records={records} />
        </SectionCard>
      </div>
    </div>
  );
}

function buildIndustrySummary(rows: TrendPoolRow[]) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    counts.set(row.industry, (counts.get(row.industry) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3 last:border-b-0 last:pb-0">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}
