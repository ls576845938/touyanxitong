"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Filter, FlaskConical, ShieldCheck } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type TenbaggerThesisList, type TenbaggerThesisRow } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

const STAGES = [
  { value: "all", label: "全部阶段" },
  { value: "candidate", label: "候选" },
  { value: "verification", label: "验证" },
  { value: "discovery", label: "发现" },
  { value: "blocked", label: "阻断" }
];

const GATES = ["ALL", "PASS", "WARN", "FAIL"];

export default function ThesisPage() {
  const [payload, setPayload] = useState<TenbaggerThesisList | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [stage, setStage] = useState("all");
  const [gate, setGate] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.tenbaggerTheses({
      market,
      board: market === "A" ? board : "all",
      stage,
      dataGateStatus: gate,
      limit: 160
    })
      .then(setPayload)
      .catch((err: Error) => setError(`假设池读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board, stage, gate]);

  const rows = useMemo(() => payload?.rows ?? [], [payload]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载十倍股研究假设" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <section className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
              <FlaskConical size={14} /> THESIS ENGINE
            </div>
            <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900">十倍股研究假设</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-500">
              将趋势评分升级为“空间、成长、质量、估值、证据、风险”的可证伪研究假设。
            </p>
          </div>
          <Link href="/research/data-quality" className="inline-flex h-11 items-center gap-2 rounded-xl bg-slate-900 px-4 text-sm font-bold text-white">
            <ShieldCheck size={17} /> 数据门控
          </Link>
        </section>

        <section className="grid gap-4 md:grid-cols-5">
          <Metric label="假设数" value={payload?.summary.count ?? 0} />
          <Metric label="平均分" value={(payload?.summary.average_thesis_score ?? 0).toFixed(1)} />
          <Metric label="候选" value={payload?.summary.candidate_count ?? 0} />
          <Metric label="验证" value={payload?.summary.verification_count ?? 0} />
          <Metric label="阻断" value={payload?.summary.blocked_count ?? 0} danger />
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
            <Filter size={16} /> 筛选条件
          </div>
          <div className="flex flex-wrap gap-3">
            <Segmented value={market} values={MARKET_OPTIONS} labelFor={marketLabel} onChange={(value) => {
              setMarket(value);
              if (value !== "A") setBoard("all");
            }} />
            {market === "A" && <Segmented value={board} values={A_BOARD_OPTIONS} labelFor={boardLabel} onChange={setBoard} />}
            <Select value={stage} values={STAGES.map((item) => item.value)} labelFor={(value) => STAGES.find((item) => item.value === value)?.label ?? value} onChange={setStage} />
            <Select value={gate} values={GATES} labelFor={(value) => value === "ALL" ? "全部门控" : value} onChange={setGate} />
          </div>
        </section>

        <section className="space-y-4">
          {rows.map((row) => <ThesisCard key={row.stock_code} row={row} />)}
          {rows.length === 0 && (
            <div className="rounded-2xl border-2 border-dashed border-slate-200 p-12 text-center text-sm text-slate-400">
              暂无假设数据，请先运行 daily pipeline。
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ThesisCard({ row }: { row: TenbaggerThesisRow }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="grid gap-6 lg:grid-cols-[280px_1fr_220px]">
        <div>
          <Link href={`/stocks/${encodeURIComponent(row.stock.code)}?from=/research/thesis`} className="text-xl font-black text-slate-900 hover:text-indigo-600">
            {row.stock.name}
          </Link>
          <div className="mt-1 text-xs font-bold text-slate-400">{row.stock.code} · {marketLabel(row.stock.market)} · {row.stock.industry}</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge label={stageLabel(row.stage)} tone={row.stage === "blocked" ? "danger" : "neutral"} />
            <Badge label={row.data_gate_status} tone={row.data_gate_status === "FAIL" ? "danger" : row.data_gate_status === "PASS" ? "pass" : "warn"} />
          </div>
        </div>
        <div className="space-y-4">
          <p className="text-sm leading-6 text-slate-600">{row.investment_thesis}</p>
          <div className="grid gap-3 md:grid-cols-3">
            <CaseBlock label="基准情景" text={row.base_case} />
            <CaseBlock label="乐观情景" text={row.bull_case} />
            <CaseBlock label="悲观情景" text={row.bear_case} />
          </div>
          <div className="flex flex-wrap gap-2">
            {row.missing_evidence.slice(0, 4).map((item) => <Badge key={item} label={item} tone="warn" />)}
          </div>
        </div>
        <div className="space-y-3">
          <div className="text-right">
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">假设评分</div>
            <div className="text-4xl font-black tracking-tight text-slate-900">{row.thesis_score.toFixed(1)}</div>
          </div>
          <ScoreLine label="空间" value={row.opportunity_score} />
          <ScoreLine label="成长" value={row.growth_score} />
          <ScoreLine label="质量" value={row.quality_score} />
          <ScoreLine label="估值" value={row.valuation_score} />
          <Link href={`/research/thesis/${encodeURIComponent(row.stock.code)}`} className="inline-flex w-full items-center justify-end gap-1 text-xs font-black uppercase tracking-widest text-indigo-600">
            查看详情 <ChevronRight size={14} />
          </Link>
        </div>
      </div>
    </article>
  );
}

function Metric({ label, value, danger = false }: { label: string; value: number | string; danger?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-1 text-3xl font-black ${danger ? "text-rose-600" : "text-slate-900"}`}>{value}</div>
    </div>
  );
}

function CaseBlock({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className="mt-1 text-xs leading-5 text-slate-600">{text}</div>
    </div>
  );
}

function ScoreLine({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-[10px] font-bold text-slate-500">
        <span>{label}</span><span>{value.toFixed(0)}</span>
      </div>
      <div className="h-2 rounded-full bg-slate-100">
        <div className="h-2 rounded-full bg-indigo-600" style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: "neutral" | "warn" | "danger" | "pass" }) {
  const cls = tone === "danger" ? "bg-rose-50 text-rose-700" : tone === "warn" ? "bg-amber-50 text-amber-700" : tone === "pass" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600";
  return <span className={`rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wide ${cls}`}>{label}</span>;
}

function Segmented({ value, values, labelFor, onChange }: { value: string; values: string[]; labelFor: (value: string) => string; onChange: (value: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1 rounded-xl bg-slate-50 p-1">
      {values.map((item) => (
        <button key={item} type="button" onClick={() => onChange(item)} className={`h-8 rounded-lg px-3 text-xs font-bold ${value === item ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-white"}`}>
          {labelFor(item)}
        </button>
      ))}
    </div>
  );
}

function Select({ value, values, labelFor, onChange }: { value: string; values: string[]; labelFor: (value: string) => string; onChange: (value: string) => void }) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600">
      {values.map((item) => <option key={item} value={item}>{labelFor(item)}</option>)}
    </select>
  );
}

function stageLabel(stage: string) {
  return ({ candidate: "候选", verification: "验证", discovery: "发现", blocked: "阻断" } as Record<string, string>)[stage] ?? stage;
}
