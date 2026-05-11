"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { MetricTile, QualityBanner, RecordList, SectionCard, TonePill, WorkbenchHeader, WorkbenchLink } from "@/components/Workbench";
import { api, type ResearchDataGate, type ResearchHotTerms, type ResearchTasks } from "@/lib/api";
import { collectQualityFlags, formatDate, toneFromStatus, uniqueTexts } from "@/lib/research-workbench";

export default function ResearchEvidencePage() {
  const [tasks, setTasks] = useState<ResearchTasks | null>(null);
  const [hotTerms, setHotTerms] = useState<ResearchHotTerms | null>(null);
  const [gate, setGate] = useState<ResearchDataGate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.allSettled([
      api.researchTasks({ limit: 60 }),
      api.researchHotTerms({ window: "7d", limit: 30 }),
      api.researchDataGate({ limit: 60 })
    ])
      .then(([tasksResult, hotTermsResult, gateResult]) => {
        if (cancelled) return;
        if (tasksResult.status === "rejected") {
          setError(`证据总表读取失败：${tasksResult.reason instanceof Error ? tasksResult.reason.message : "unknown error"}`);
          return;
        }
        setTasks(tasksResult.value);
        setHotTerms(hotTermsResult.status === "fulfilled" ? hotTermsResult.value : null);
        setGate(gateResult.status === "fulfilled" ? gateResult.value : null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const qualityFlags = useMemo(
    () => collectQualityFlags(hotTerms?.summary.data_mode, gate?.summary.fail_count ? "FAIL" : ""),
    [gate?.summary.fail_count, hotTerms?.summary.data_mode]
  );

  const records = useMemo(() => {
    return (tasks?.tasks ?? []).slice(0, 8).map((task) => ({
      date: task.trade_date,
      title: task.title,
      detail: task.detail,
      tone: task.priority === "high" ? ("warn" as const) : ("neutral" as const),
      tags: [task.stock_name, task.priority, task.task_type]
    }));
  }, [tasks]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载研究证据总表" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!tasks) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="暂无证据数据" /></div>;

  const degradedSources = (hotTerms?.sources ?? []).filter((source) => ["degraded", "error", "pending_connector", "connected_empty"].includes(source.status));
  const riskItems = uniqueTexts([
    ...(gate?.rows.filter((row) => row.status === "FAIL").slice(0, 6).flatMap((row) => row.reasons) ?? []),
    ...degradedSources.map((source) => `${source.label} 状态 ${source.status}${source.last_error ? `：${source.last_error}` : ""}`)
  ]);

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <WorkbenchHeader
          eyebrow="Research Evidence"
          title="研究证据总表"
          summary="统一查看任务、热词来源和门控阻断，把分散证据排成可复核链路。这里只输出研究辅助线索和风险提示，不输出确定性买卖建议。"
          actions={
            <>
              <WorkbenchLink href="/research" label="返回研究中心" />
              <WorkbenchLink href="/research/data-quality" label="查看门控详情" />
            </>
          }
        />

        <QualityBanner flags={qualityFlags} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="结论摘要" value={`${tasks.summary.task_count} 条`} detail={`覆盖 ${tasks.summary.stock_count} 只标的 / 日期 ${formatDate(tasks.latest_date)}`} />
          <MetricTile label="证据热词" value={hotTerms?.summary.term_count ?? 0} detail={`来源 ${hotTerms?.summary.source_count ?? 0} / 数据模式 ${hotTerms?.summary.data_mode ?? "--"}`} />
          <MetricTile label="高优先级核验" value={tasks.summary.high_priority_count} tone="warn" detail={`验证事项 ${tasks.summary.question_task_count} / 风险核验 ${tasks.summary.risk_task_count}`} />
          <MetricTile label="门控 FAIL" value={gate?.summary.fail_count ?? 0} tone={(gate?.summary.fail_count ?? 0) > 0 ? "fail" : "pass"} detail={`PASS ${gate?.summary.pass_count ?? 0} / WARN ${gate?.summary.warn_count ?? 0}`} />
        </section>

        <SectionCard title="结论摘要" subtitle="先看当前证据面最密集的信号。">
          <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-3">
              {(hotTerms?.hot_terms ?? []).slice(0, 6).map((term) => (
                <div key={term.term} className="rounded-2xl border border-slate-200 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-bold text-slate-900">{term.term}</div>
                    <TonePill label={`${term.mentions} mentions`} tone={term.score > 70 ? "pass" : "neutral"} />
                  </div>
                  <div className="mt-2 text-sm text-slate-600">
                    {(term.industries ?? []).slice(0, 3).map((item) => item.label).join(" / ") || "暂无行业映射"}
                  </div>
                </div>
              ))}
            </div>
            <div className="rounded-2xl bg-slate-50 p-5">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">热词来源状态</div>
              <div className="mt-4 space-y-3">
                {(hotTerms?.sources ?? []).slice(0, 8).map((source) => (
                  <div key={source.key} className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3">
                    <div>
                      <div className="text-sm font-bold text-slate-900">{source.label}</div>
                      <div className="text-[11px] text-slate-500">{source.article_count} articles</div>
                    </div>
                    <TonePill label={source.status} tone={toneFromStatus(source.status)} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="证据链" subtitle="把来源、任务和标的串起来。">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-3">
              {(tasks.tasks ?? []).slice(0, 10).map((task) => (
                <Link key={task.id} href={`/research/security/${encodeURIComponent(task.stock_code)}`} className="block rounded-2xl border border-slate-200 p-4 transition-colors hover:border-slate-300">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-bold text-slate-900">{task.stock_name} · {task.stock_code}</div>
                    <div className="flex gap-2">
                      <TonePill label={task.priority} tone={task.priority === "high" ? "warn" : "neutral"} />
                      <TonePill label={task.task_type} />
                    </div>
                  </div>
                  <div className="mt-2 text-sm leading-6 text-slate-600">{task.title}</div>
                  <div className="mt-2 text-xs text-slate-500">{task.detail}</div>
                </Link>
              ))}
            </div>
            <div className="space-y-3">
              {(hotTerms?.platform_terms ?? []).slice(0, 6).map((source) => (
                <div key={source.key} className="rounded-2xl border border-slate-200 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-bold text-slate-900">{source.label}</div>
                    <TonePill label={source.status} tone={toneFromStatus(source.status)} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {source.terms.slice(0, 5).map((term) => <TonePill key={term.term} label={term.term} tone="pass" />)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </SectionCard>

        <SectionCard title="风险提示" subtitle="优先暴露数据门控 FAIL 和来源退化。">
          <div className="space-y-3">
            {riskItems.map((item) => (
              <div key={item} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900">
                {item}
              </div>
            ))}
            {riskItems.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">暂无高优先级风险提醒。</div>}
          </div>
        </SectionCard>

        <SectionCard title="操作记录" subtitle="最近待复核动作，按任务流落地。">
          <RecordList records={records} />
        </SectionCard>
      </div>
    </div>
  );
}
