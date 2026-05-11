"use client";

import { useEffect, useMemo, useState } from "react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { MetricTile, QualityBanner, RecordList, SectionCard, TonePill, WorkbenchHeader, WorkbenchLink } from "@/components/Workbench";
import { api, type ResearchBrief, type WatchlistTimeline, type WatchlistTimelineItem } from "@/lib/api";
import { collectQualityFlags, formatDate, uniqueTexts } from "@/lib/research-workbench";

export default function PortfolioTradeJournalPage() {
  const [timeline, setTimeline] = useState<WatchlistTimeline | null>(null);
  const [brief, setBrief] = useState<ResearchBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.allSettled([api.watchlistTimeline({ limit: 20 }), api.researchBrief({ limit: 40 })])
      .then(([timelineResult, briefResult]) => {
        if (cancelled) return;
        if (timelineResult.status === "rejected") {
          setError(`观察日志读取失败：${timelineResult.reason instanceof Error ? timelineResult.reason.message : "unknown error"}`);
          return;
        }
        setTimeline(timelineResult.value);
        setBrief(briefResult.status === "fulfilled" ? briefResult.value : null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const entries = useMemo(() => buildJournalEntries(timeline?.timeline ?? [], brief), [timeline, brief]);
  const flags = useMemo(() => collectQualityFlags(...entries.flatMap((entry) => entry.tags ?? [])), [entries]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载组合观察日志" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  const riskItems = uniqueTexts([
    ...(timeline?.timeline ?? []).slice(0, 4).flatMap((item) => item.downgraded.map((row) => `${row.name} ${row.code} 评级下调`)),
    ...(brief?.top_tasks ?? []).filter((task) => task.task_type === "risk_review").slice(0, 4).map((task) => `${task.stock_name} ${task.stock_code}：${task.title}`)
  ]);

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <WorkbenchHeader
          eyebrow="Portfolio Journal"
          title="组合观察日志"
          summary="这里记录的是研究辅助意义上的观察动作、复核动作和评级变化，不代表成交、建仓或减仓指令。"
          actions={
            <>
              <WorkbenchLink href="/portfolio/dashboard" label="返回组合看板" />
              <WorkbenchLink href="/research/brief" label="今日工作单" />
            </>
          }
        />

        <QualityBanner flags={flags} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="日志起点" value={formatDate(timeline?.timeline[0]?.trade_date ?? null)} detail="最近观察快照日期" />
          <MetricTile label="日志条数" value={entries.length} detail="观察动作与复核动作合并展示" />
          <MetricTile label="风险复核" value={brief?.summary.risk_task_count ?? 0} tone="warn" detail={`验证事项 ${brief?.summary.question_task_count ?? 0}`} />
          <MetricTile label="新增观察" value={timeline?.latest?.summary.new_count ?? 0} detail={`最新观察池 ${timeline?.latest?.summary.latest_watch_count ?? 0} 只`} />
        </section>

        <SectionCard title="结论摘要" subtitle="最近观察动作的总体判断。">
          <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
            <div className="rounded-2xl bg-slate-50 p-5">
              <p className="text-sm leading-7 text-slate-700">
                最近日志以观察池快照变化和研究工作单为主。新增与上调记录代表研究注意力抬升，降级与移出代表风险或证据不足。所有记录都需要回到证据页和原始信源复核。
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 p-5">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">日志标签</div>
              <div className="mt-4 flex flex-wrap gap-2">
                <TonePill label="观察动作" tone="pass" />
                <TonePill label="风险复核" tone="warn" />
                <TonePill label="人工确认" />
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="证据链" subtitle="日志背后的观察快照与研究任务。">
          <RecordList records={entries.slice(0, 12)} />
        </SectionCard>

        <SectionCard title="风险提示" subtitle="优先看降级、移出和风险复核任务。">
          <div className="space-y-3">
            {riskItems.map((item) => (
              <div key={item} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900">
                {item}
              </div>
            ))}
            {riskItems.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">暂无高优先级风险日志。</div>}
          </div>
        </SectionCard>

        <SectionCard title="操作记录" subtitle="完整日志，按时间逆序记录。">
          <RecordList records={entries} />
        </SectionCard>
      </div>
    </div>
  );
}

function buildJournalEntries(timeline: WatchlistTimelineItem[], brief: ResearchBrief | null) {
  const watchlistEntries = timeline.flatMap((item) => {
    const results = [];
    if (item.new_entries.length > 0) {
      results.push({
        date: item.trade_date,
        title: `新增观察 ${item.new_entries.length} 只`,
        detail: item.new_entries.slice(0, 3).map((row) => `${row.name} ${row.code}`).join("，"),
        tone: "pass" as const,
        tags: ["观察动作"]
      });
    }
    if (item.downgraded.length > 0 || item.removed_entries.length > 0) {
      results.push({
        date: item.trade_date,
        title: `降级/移出 ${item.downgraded.length + item.removed_entries.length} 只`,
        detail: [...item.downgraded, ...item.removed_entries].slice(0, 3).map((row) => `${row.name} ${row.code}`).join("，"),
        tone: "warn" as const,
        tags: ["风险复核"]
      });
    }
    return results;
  });

  const briefEntries = (brief?.top_tasks ?? []).slice(0, 8).map((task) => ({
    date: task.trade_date,
    title: task.title,
    detail: `${task.stock_name} ${task.stock_code}：${task.detail}`,
    tone: task.task_type === "risk_review" ? ("warn" as const) : ("neutral" as const),
    tags: [task.task_type === "risk_review" ? "风险复核" : "观察动作"]
  }));

  return [...watchlistEntries, ...briefEntries].sort((a, b) => String(b.date).localeCompare(String(a.date)));
}
