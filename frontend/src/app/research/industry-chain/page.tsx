"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { MetricTile, QualityBanner, RecordList, SectionCard, TonePill, WorkbenchHeader, WorkbenchLink } from "@/components/Workbench";
import { api, type ChainNode, type ChainNodeDetail, type ChainOverview, type ChainTimeline } from "@/lib/api";
import { collectQualityFlags, formatDate, formatSigned, toneFromStatus } from "@/lib/research-workbench";

export default function ResearchIndustryChainWorkbenchPage() {
  const [overview, setOverview] = useState<ChainOverview | null>(null);
  const [detail, setDetail] = useState<ChainNodeDetail | null>(null);
  const [timeline, setTimeline] = useState<ChainTimeline | null>(null);
  const [selectedNode, setSelectedNode] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api.chainOverview()
      .then((payload) => {
        if (cancelled) return;
        setOverview(payload);
        setSelectedNode(payload.default_focus_node_key ?? payload.nodes[0]?.node_key ?? "");
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`产业链研究页读取失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedNode) return;
    let cancelled = false;
    Promise.allSettled([api.chainNode(selectedNode), api.chainTimeline({ nodeKey: selectedNode, limit: 8 })]).then(([detailResult, timelineResult]) => {
      if (cancelled) return;
      setDetail(detailResult.status === "fulfilled" ? detailResult.value : null);
      setTimeline(timelineResult.status === "fulfilled" ? timelineResult.value : null);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedNode]);

  const focus = useMemo(() => detail?.node ?? overview?.nodes.find((node) => node.node_key === selectedNode) ?? null, [detail, overview, selectedNode]);
  const topNodes = useMemo(() => [...(overview?.nodes ?? [])].sort((a, b) => normalizeHeat(b) - normalizeHeat(a)).slice(0, 8), [overview]);
  const flags = useMemo(() => collectQualityFlags(...(detail?.heat_explanation ?? []), ...(timeline?.timeline.map((item) => item.summary ?? "") ?? [])), [detail?.heat_explanation, timeline?.timeline]);
  const records = useMemo(() => {
    return (timeline?.timeline ?? []).slice(0, 6).map((item) => ({
      date: item.trade_date ?? item.date ?? null,
      title: item.label ?? "热度快照",
      detail: item.summary ?? "暂无摘要",
      tone: toneFromStatus(item.summary),
      tags: [
        `heat ${normalizeHeat(item.heat).toFixed(1)}`,
        `mom ${formatSigned(item.momentum, 1)}`
      ]
    }));
  }, [timeline]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载产业链研究工作台" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!overview || !focus) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="暂无产业链研究数据" /></div>;

  const focusMapped = (detail?.mapped_industries ?? []).slice(0, 6);
  const focusLeaders = (detail?.leader_stocks ?? []).slice(0, 6);

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <WorkbenchHeader
          eyebrow="Research Industry Chain"
          title="产业链研究工作台"
          summary="先给链路结论，再落到映射行业、龙头样本、风险和观察记录。这里只做研究辅助，热度和节点关系不能直接等同交易结论。"
          actions={
            <>
              <WorkbenchLink href="/industry/chain" label="图谱视图" />
              <WorkbenchLink href="/research/evidence" label="证据总表" />
            </>
          }
        />

        <QualityBanner flags={flags} fallbackLabel={!detail ? "节点详情暂未返回，当前只展示 overview 快照。" : undefined} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="结论摘要" value={focus.name} detail={focus.description ?? "暂无节点说明"} />
          <MetricTile label="观察等级" value={normalizeHeat(focus).toFixed(1)} detail={`节点热度 / 动量 ${formatSigned(focus.momentum, 1)}`} />
          <MetricTile label="映射行业" value={focusMapped.length} detail={`上游 ${detail?.upstream.length ?? 0} / 下游 ${detail?.downstream.length ?? 0}`} />
          <MetricTile label="样本覆盖" value={overview.summary.node_count ?? 0} detail={`边 ${overview.summary.edge_count ?? 0} / 快照 ${formatDate(overview.summary.snapshot_date)}`} />
        </section>

        <SectionCard title="结论摘要" subtitle="当前聚焦节点与链路观察。">
          <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
            <div className="rounded-2xl border border-slate-200 p-4">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">聚焦节点</div>
              <div className="mt-3 space-y-2">
                {topNodes.map((node) => (
                  <button
                    key={node.node_key}
                    type="button"
                    onClick={() => setSelectedNode(node.node_key)}
                    className={`flex w-full items-center justify-between rounded-2xl px-4 py-3 text-left transition-colors ${
                      node.node_key === focus.node_key ? "bg-slate-900 text-white" : "bg-slate-50 text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <div>
                      <div className="text-sm font-bold">{node.name}</div>
                      <div className={`text-[10px] ${node.node_key === focus.node_key ? "text-slate-300" : "text-slate-400"}`}>{node.layer}</div>
                    </div>
                    <div className="text-sm font-black">{normalizeHeat(node).toFixed(1)}</div>
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl bg-slate-50 p-5">
                <div className="mb-2 flex items-center gap-2">
                  <TonePill label={focus.layer} />
                  {(focus.industry_names ?? []).slice(0, 2).map((name) => <TonePill key={name} label={name} tone="pass" />)}
                </div>
                <p className="text-sm leading-7 text-slate-700">{detail?.heat_explanation?.[0] ?? focus.description ?? "暂无链路摘要"}</p>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <MiniFact label="上游节点" value={String(detail?.upstream.length ?? 0)} />
                <MiniFact label="下游节点" value={String(detail?.downstream.length ?? 0)} />
                <MiniFact label="区域映射" value={String(detail?.regions?.length ?? 0)} />
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="证据链" subtitle="从产业节点映射到行业和个股样本。">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="space-y-3">
              {focusMapped.map((item, index) => {
                const name = typeof item === "string" ? item : item.name;
                const heat = typeof item === "string" ? null : item.heat;
                return (
                  <div key={`${name}-${index}`} className="rounded-2xl border border-slate-200 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-bold text-slate-900">{name}</div>
                      <TonePill label={heat === null || heat === undefined ? "映射" : `heat ${heat.toFixed(1)}`} tone={heat && heat > 70 ? "pass" : "neutral"} />
                    </div>
                  </div>
                );
              })}
              {focusMapped.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">暂无映射行业样本</div>}
            </div>
            <div className="space-y-3">
              {focusLeaders.map((stock) => (
                <LinkRow
                  key={stock.code}
                  href={`/research/security/${encodeURIComponent(stock.code)}`}
                  title={`${stock.name} · ${stock.code}`}
                  subtitle={stock.reason || stock.industry_level2 || "龙头样本"}
                  pill={stock.final_score !== null && stock.final_score !== undefined ? `score ${stock.final_score.toFixed(1)}` : "观察样本"}
                />
              ))}
              {focusLeaders.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">暂无龙头样本</div>}
            </div>
          </div>
        </SectionCard>

        <SectionCard title="风险提示" subtitle="聚焦链路断点、说明缺口和热度回落。">
          <div className="space-y-3">
            {(detail?.heat_explanation ?? []).slice(1, 5).map((item) => (
              <div key={item} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900">
                {item}
              </div>
            ))}
            {detail?.leader_stocks?.length === 0 ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900">
                当前节点缺少龙头样本映射，链路热度需要回看原始图谱和个股映射逻辑。
              </div>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard title="操作记录" subtitle="记录最近链路热度变化和观察动作。">
          <RecordList records={records} />
        </SectionCard>
      </div>
    </div>
  );
}

function normalizeHeat(value: ChainNode | number | null | undefined): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  return value?.heat ?? value?.intensity ?? 0;
}

function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className="mt-2 text-lg font-black text-slate-900">{value}</div>
    </div>
  );
}

function LinkRow({ href, title, subtitle, pill }: { href: string; title: string; subtitle: string; pill: string }) {
  return (
    <Link href={href} className="block rounded-2xl border border-slate-200 p-4 transition-colors hover:border-slate-300">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-bold text-slate-900">{title}</div>
        <TonePill label={pill} />
      </div>
      <div className="mt-2 text-sm text-slate-600">{subtitle}</div>
    </Link>
  );
}
