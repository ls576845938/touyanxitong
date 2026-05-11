"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { MetricTile, QualityBanner, RecordList, SectionCard, TonePill, WorkbenchHeader, WorkbenchLink } from "@/components/Workbench";
import { api, type ResearchDataGate, type StockEvidence, type StockHistory, type TenbaggerThesisRow } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";
import {
  collectQualityFlags,
  formatDate,
  formatPct,
  observationLevel,
  toneFromFlags,
  toneFromStatus,
  uniqueTexts
} from "@/lib/research-workbench";

export default function ResearchSecurityDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [evidence, setEvidence] = useState<StockEvidence | null>(null);
  const [history, setHistory] = useState<StockHistory | null>(null);
  const [gate, setGate] = useState<ResearchDataGate | null>(null);
  const [thesis, setThesis] = useState<TenbaggerThesisRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.allSettled([
      api.stockEvidence(symbol),
      api.stockHistory(symbol),
      api.researchDataGate({ limit: 300 }),
      api.tenbaggerThesis(symbol)
    ])
      .then(([evidenceResult, historyResult, gateResult, thesisResult]) => {
        if (cancelled) return;
        if (evidenceResult.status === "rejected") {
          setError(`证券研究页读取失败：${evidenceResult.reason instanceof Error ? evidenceResult.reason.message : "unknown error"}`);
          return;
        }
        setEvidence(evidenceResult.value);
        setHistory(historyResult.status === "fulfilled" ? historyResult.value : null);
        setGate(gateResult.status === "fulfilled" ? gateResult.value : null);
        setThesis(thesisResult.status === "fulfilled" ? thesisResult.value.latest : null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const gateRow = useMemo(() => gate?.rows.find((row) => row.code === symbol) ?? null, [gate, symbol]);
  const qualityFlags = useMemo(() => collectQualityFlags(gateRow?.status, thesis?.data_gate_status, evidence?.evidence.summary), [evidence, gateRow?.status, thesis?.data_gate_status]);
  const operationRecords = useMemo(() => {
    return (history?.history ?? []).slice(0, 6).map((row) => ({
      date: row.trade_date,
      title: `${row.rating} / 分值 ${row.final_score.toFixed(1)}`,
      detail: `${row.summary} 风险提示：${row.risk_summary}`,
      tone: toneFromStatus(row.news_evidence_status),
      tags: [
        row.is_breakout_120d ? "120D突破" : "区间内",
        row.is_ma_bullish ? "均线多头" : "均线待确认"
      ]
    }));
  }, [history]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载证券研究工作台" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!evidence) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="暂无证券研究数据" /></div>;

  const summaryTone = gateRow ? toneFromStatus(gateRow.status) : evidence.score.research_gate.passed ? "pass" : "warn";
  const level = observationLevel(evidence.score.final_score, evidence.score.confidence.level);
  const riskItems = uniqueTexts([
    evidence.evidence.risk_summary,
    ...(gateRow?.reasons ?? []),
    ...(thesis?.disconfirming_evidence ?? []),
    ...evidence.evidence.questions_to_verify
  ]);
  const sourceRefs = evidence.evidence.source_refs.slice(0, 8);

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <WorkbenchHeader
          eyebrow="Research Security"
          title={`${evidence.stock.name} · ${evidence.stock.code}`}
          summary={`研究辅助页，聚焦 ${marketLabel(evidence.stock.market)} / ${boardLabel(evidence.stock.board)} 的结论摘要、证据链与风险复核。页面只提供观察等级和复核事项，不构成确定性买卖建议。`}
          actions={
            <>
              <WorkbenchLink href={`/stocks/${encodeURIComponent(evidence.stock.code)}?from=/research/security/${encodeURIComponent(evidence.stock.code)}`} label="原始证据终端" />
              <WorkbenchLink href="/research/stock-pool" label="返回研究股票池" />
            </>
          }
        />

        <QualityBanner flags={qualityFlags} />

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricTile label="观察等级" value={level} tone={summaryTone} detail={`综合分 ${evidence.score.final_score?.toFixed(1) ?? "--"} / 置信度 ${evidence.score.confidence.level}`} />
          <MetricTile label="研究辅助结论" value={evidence.score.rating ?? "待评估"} detail={evidence.score.explanation} />
          <MetricTile label="数据门控" value={gateRow?.status ?? (evidence.score.research_gate.passed ? "PASS" : "REVIEW")} tone={summaryTone} detail={(gateRow?.reasons ?? evidence.score.research_gate.reasons).slice(0, 2).join("；") || "需要人工复核"} />
          <MetricTile label="Thesis 准备度" value={thesis ? thesis.stage : "未生成"} tone={toneFromFlags(qualityFlags)} detail={thesis ? `readiness ${thesis.readiness_score.toFixed(1)} / evidence ${thesis.evidence_score.toFixed(1)}` : "暂无 thesis 快照"} />
        </section>

        <SectionCard title="结论摘要" subtitle="先给出研究辅助结论，再展开证据和风险。">
          <div className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
            <div className="space-y-4">
              <div className="rounded-2xl bg-slate-50 p-5">
                <div className="mb-2 flex items-center gap-2">
                  <TonePill label={level} tone={summaryTone} />
                  <TonePill label={evidence.score.news_evidence_status} tone={toneFromStatus(evidence.score.news_evidence_status)} />
                </div>
                <p className="text-sm leading-7 text-slate-700">{evidence.evidence.summary}</p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <SummaryLine label="行业逻辑" text={evidence.evidence.industry_logic} />
                <SummaryLine label="公司逻辑" text={evidence.evidence.company_logic} />
                <SummaryLine label="趋势逻辑" text={evidence.evidence.trend_logic} />
                <SummaryLine label="催化逻辑" text={evidence.evidence.catalyst_logic} />
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 p-5">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">观测快照</div>
              <div className="mt-4 space-y-3 text-sm text-slate-600">
                <InfoRow label="交易日期" value={formatDate(evidence.evidence.trade_date)} />
                <InfoRow label="市场/板块" value={`${marketLabel(evidence.stock.market)} / ${boardLabel(evidence.stock.board)}`} />
                <InfoRow label="相对强弱" value={String(evidence.trend.relative_strength_rank ?? "--")} />
                <InfoRow label="数据置信" value={formatPct(evidence.score.confidence.data_confidence, 0)} />
                <InfoRow label="资讯置信" value={formatPct(evidence.score.confidence.news_confidence, 0)} />
                <InfoRow label="基本面置信" value={formatPct(evidence.score.confidence.fundamental_confidence, 0)} />
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="证据链" subtitle="把摘要拆回来源、问题和待验证项。">
          <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="space-y-3">
              {evidence.evidence.questions_to_verify.map((question) => (
                <div key={question} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">待验证</div>
                  <div className="mt-2 text-sm leading-6 text-slate-700">{question}</div>
                </div>
              ))}
              {evidence.evidence.questions_to_verify.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-4 text-sm text-slate-400">当前没有额外待验证问题</div>}
            </div>
            <div className="space-y-3">
              {sourceRefs.map((source) => (
                <a
                  key={`${source.source}-${source.title}`}
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block rounded-2xl border border-slate-200 p-4 transition-colors hover:border-slate-300"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-bold text-slate-900">{source.title}</div>
                    <TonePill label={source.source} />
                  </div>
                  <div className="mt-2 text-xs text-slate-500">外部信源，仅作研究辅助，请回看原文和披露时间。</div>
                </a>
              ))}
            </div>
          </div>
        </SectionCard>

        <SectionCard title="风险提示" subtitle="任何 FAIL、证伪条件和证据缺口都优先展示。">
          <div className="space-y-3">
            {riskItems.map((item) => (
              <div key={item} className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm leading-6 text-rose-900">
                {item}
              </div>
            ))}
            {riskItems.length === 0 && <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">暂无显式风险条目，仍需人工复核。</div>}
          </div>
        </SectionCard>

        <SectionCard title="操作记录" subtitle="仅记录研究动作与观察变化，不输出交易指令。">
          <RecordList records={operationRecords} />
        </SectionCard>
      </div>
    </div>
  );
}

function SummaryLine({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <p className="mt-2 text-sm leading-6 text-slate-700">{text}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3 last:border-b-0 last:pb-0">
      <div className="text-slate-500">{label}</div>
      <div className="text-right font-semibold text-slate-900">{value}</div>
    </div>
  );
}
