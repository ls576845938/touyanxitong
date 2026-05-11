"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { MetricTile, QualityBanner, RecordList, SectionCard, TonePill, WorkbenchHeader, WorkbenchLink } from "@/components/Workbench";
import { api, type ResearchDataGate, type ResearchUniverse, type TrendPoolRow, type WatchlistTimeline } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";
import { collectQualityFlags, formatPct, observationLevel, toneFromStatus, uniqueTexts } from "@/lib/research-workbench";

export default function ResearchStockPoolPage() {
  const [rows, setRows] = useState<TrendPoolRow[]>([]);
  const [universe, setUniverse] = useState<ResearchUniverse | null>(null);
  const [gate, setGate] = useState<ResearchDataGate | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.allSettled([
      api.trendPool({ researchUniverseOnly: true, limit: 40 }),
      api.researchUniverse(),
      api.researchDataGate({ limit: 80 }),
      api.watchlistTimeline({ limit: 12 })
    ])
      .then(([poolResult, universeResult, gateResult, watchlistResult]) => {
        if (cancelled) return;
        if (poolResult.status === "rejected") {
          setError(`研究股票池读取失败：${poolResult.reason instanceof Error ? poolResult.reason.message : "unknown error"}`);
          return;
        }
        setRows(poolResult.value);
        setUniverse(universeResult.status === "fulfilled" ? universeResult.value : null);
        setGate(gateResult.status === "fulfilled" ? gateResult.value : null);
        setWatchlist(watchlistResult.status === "fulfilled" ? watchlistResult.value : null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const qualityFlags = useMemo(() => collectQualityFlags(gate?.summary.fail_count ? "FAIL" : ""), [gate?.summary.fail_count]);
  const records = useMemo(() => {
    return (watchlist?.timeline ?? []).slice(0, 6).map((item) => ({
      date: item.trade_date,
      title: `观察池变动 ${item.summary.new_count} / ${item.summary.removed_count}`,
      detail: `新进 ${item.summary.new_count}，移出 ${item.summary.removed_count}，上调 ${item.summary.upgraded_count}，降级 ${item.summary.downgraded_count}。`,
      tone: item.summary.downgraded_count > 0 ? ("warn" as const) : ("neutral" as const),
      tags: ["观察池", `${item.summary.latest_watch_count} 只`]
    }));
  }, [watchlist]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载研究股票池" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  const blockedCodes = new Set(gate?.rows.filter((row) => row.status === "FAIL").map((row) => row.code) ?? []);
  const riskItems = uniqueTexts([
    ...rows.filter((row) => !row.research_gate?.passed || blockedCodes.has(row.code)).slice(0, 8).map((row) => `${row.name} ${row.code} 仍需人工复核：${row.explanation}`),
    ...(gate?.rows.filter((row) => row.status === "FAIL").slice(0, 4).flatMap((row) => row.reasons) ?? [])
  ]);

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <WorkbenchHeader
          eyebrow="Research Stock Pool"
          title="研究股票池"
          summary="从研究宇宙和趋势池中筛出需要持续观察的候选标的，先给观察等级，再给证据和风险。这里不输出买卖建议，只输出研究辅助排序。"
          actions={
            <>
              <WorkbenchLink href="/trend" label="趋势池原视图" />
              <WorkbenchLink href="/portfolio/dashboard" label="组合看板" />
            </>
          }
        />

        <QualityBanner flags={qualityFlags} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="结论摘要" value={`${rows.length} 只`} detail={`研究宇宙准入率 ${formatPct(universe?.summary.eligible_ratio, 0)}`} />
          <MetricTile label="重点观察" value={rows.filter((row) => observationLevel(row.final_score, row.confidence?.level) === "重点观察").length} detail="高分且高置信候选" />
          <MetricTile label="待人工复核" value={rows.filter((row) => !row.research_gate?.passed || blockedCodes.has(row.code)).length} tone="warn" detail={`门控 FAIL ${gate?.summary.fail_count ?? 0}`} />
          <MetricTile label="观察池交集" value={watchlist?.latest?.summary.latest_watch_count ?? 0} detail="最近一期观察池规模" />
        </section>

        <SectionCard title="结论摘要" subtitle="优先看当前最值得持续跟踪的研究辅助候选。">
          <div className="grid gap-4">
            {rows.slice(0, 12).map((row) => {
              const blocked = blockedCodes.has(row.code);
              return (
                <Link key={row.code} href={`/research/security/${encodeURIComponent(row.code)}`} className="block rounded-2xl border border-slate-200 p-5 transition-colors hover:border-slate-300">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="text-lg font-bold text-slate-900">{row.name} <span className="text-sm font-semibold text-slate-400">{row.code}</span></div>
                      <div className="text-xs text-slate-500">{marketLabel(row.market)} / {boardLabel(row.board)} / {row.industry}</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <TonePill label={observationLevel(row.final_score, row.confidence?.level)} tone={row.final_score >= 75 ? "pass" : "neutral"} />
                      <TonePill label={blocked ? "DATA FAIL" : row.research_gate?.status ?? "review"} tone={blocked ? "fail" : toneFromStatus(row.research_gate?.status)} />
                      <TonePill label={`score ${row.final_score.toFixed(1)}`} />
                    </div>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{row.explanation}</p>
                </Link>
              );
            })}
          </div>
        </SectionCard>

        <SectionCard title="证据链" subtitle="按分值、置信和门控状态拆开。">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-left">
              <thead>
                <tr className="border-b border-slate-200 text-[10px] font-black uppercase tracking-widest text-slate-400">
                  <th className="pb-3">标的</th>
                  <th className="pb-3">评级</th>
                  <th className="pb-3">分值拆解</th>
                  <th className="pb-3">观察等级</th>
                  <th className="pb-3">风险提示</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.slice(0, 20).map((row) => {
                  const blocked = blockedCodes.has(row.code);
                  return (
                    <tr key={row.code}>
                      <td className="py-4">
                        <Link href={`/research/security/${encodeURIComponent(row.code)}`} className="font-bold text-slate-900 hover:text-slate-700">
                          {row.name} · {row.code}
                        </Link>
                        <div className="mt-1 text-xs text-slate-500">{row.industry_level2}</div>
                      </td>
                      <td className="py-4">
                        <TonePill label={row.rating} tone={row.final_score >= 75 ? "pass" : "neutral"} />
                      </td>
                      <td className="py-4 text-sm text-slate-600">
                        行业 {row.industry_score.toFixed(1)} / 公司 {row.company_score.toFixed(1)} / 趋势 {row.trend_score.toFixed(1)} / 催化 {row.catalyst_score.toFixed(1)}
                      </td>
                      <td className="py-4">
                        <TonePill label={observationLevel(row.final_score, row.confidence?.level)} tone={row.confidence?.level === "high" ? "pass" : "neutral"} />
                      </td>
                      <td className="py-4">
                        <TonePill label={blocked ? "FAIL" : row.research_gate?.status ?? "review"} tone={blocked ? "fail" : toneFromStatus(row.research_gate?.status)} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>

        <SectionCard title="风险提示" subtitle="有 FAIL 或研究门控 review 的标的必须先过这一层。">
          <div className="space-y-3">
            {riskItems.map((item) => (
              <div key={item} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900">
                {item}
              </div>
            ))}
            {riskItems.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">当前前排候选没有显式 FAIL 阻断。</div>}
          </div>
        </SectionCard>

        <SectionCard title="操作记录" subtitle="按观察池快照记录研究动作，不直接映射为交易动作。">
          <RecordList records={records} />
        </SectionCard>
      </div>
    </div>
  );
}
