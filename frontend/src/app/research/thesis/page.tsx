"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, ChevronRight, Crosshair, Filter, Radar, ShieldAlert, ShieldCheck, Sigma, Workflow } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type TenbaggerAlternativeSignal, type TenbaggerLogicGate, type TenbaggerThesisList, type TenbaggerThesisRow } from "@/lib/api";
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
  const [logicGate, setLogicGate] = useState("ALL");
  const [contrarianOnly, setContrarianOnly] = useState(false);
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
      logicGateStatus: logicGate,
      contrarianOnly,
      limit: 160
    })
      .then(setPayload)
      .catch((err: Error) => setError(`逻辑狙击工作台读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board, stage, gate, logicGate, contrarianOnly]);

  const rows = useMemo(() => payload?.rows ?? [], [payload]);
  const priorityRows = useMemo(() => rows.slice(0, 5), [rows]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载 Tenbagger 逻辑狙击工作台" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  const summary = payload?.summary;

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
              <Crosshair size={14} /> TENBAGGER LOGIC SNIPER
            </div>
            <h1 className="mt-2 text-4xl font-black tracking-tight text-slate-900">逻辑狙击工作台</h1>
            <p className="mt-3 text-sm leading-6 text-slate-500">
              把十倍股假设拆成可证伪的逻辑门控、替代数据 proxy、TAM 情景、反共识信号和边际变化。这里只输出研究线索、风险和待验证事项。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <TopLink href="/research/ai-big-graph" label="AI大图谱" icon={<Workflow size={16} />} />
            <TopLink href="/trend" label="趋势雷达" icon={<Radar size={16} />} />
            <TopLink href="/research/data-quality" label="数据门控" icon={<ShieldCheck size={16} />} />
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <Metric label="假设数" value={summary?.count ?? 0} />
          <Metric label="平均假设分" value={(summary?.average_thesis_score ?? 0).toFixed(1)} />
          <Metric label="逻辑门控均分" value={(summary?.average_logic_gate_score ?? 0).toFixed(1)} tone={gateToneFromScore(summary?.average_logic_gate_score ?? 0)} />
          <Metric label="反证压力" value={(summary?.average_anti_thesis_score ?? 0).toFixed(1)} tone={(summary?.average_anti_thesis_score ?? 0) >= 55 ? "danger" : "neutral"} />
          <Metric label="反共识队列" value={summary?.contrarian_count ?? 0} tone={(summary?.contrarian_count ?? 0) > 0 ? "warn" : "neutral"} />
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
            <Filter size={16} /> 筛选条件
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Segmented value={market} values={MARKET_OPTIONS} labelFor={marketLabel} onChange={(value) => {
              setMarket(value);
              if (value !== "A") setBoard("all");
            }} />
            {market === "A" && <Segmented value={board} values={A_BOARD_OPTIONS} labelFor={boardLabel} onChange={setBoard} />}
            <Select value={stage} values={STAGES.map((item) => item.value)} labelFor={(value) => STAGES.find((item) => item.value === value)?.label ?? value} onChange={setStage} />
            <Select value={gate} values={GATES} labelFor={(value) => value === "ALL" ? "全部数据门控" : `数据${value}`} onChange={setGate} />
            <Select value={logicGate} values={GATES} labelFor={(value) => value === "ALL" ? "全部逻辑门控" : `逻辑${value}`} onChange={setLogicGate} />
            <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 text-xs font-bold text-slate-600">
              <input type="checkbox" checked={contrarianOnly} onChange={(event) => setContrarianOnly(event.target.checked)} className="size-4 rounded border-slate-300" />
              仅反共识
            </label>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2 text-sm font-black text-slate-900">
              <Sigma size={17} className="text-cyan-700" /> 今日优先验证
            </div>
            <div className="space-y-3">
              {priorityRows.map((row) => (
                <Link key={row.stock_code} href={`/research/thesis/${encodeURIComponent(row.stock_code)}`} className="block rounded-xl border border-slate-100 bg-slate-50 p-4 transition-colors hover:border-cyan-200 hover:bg-cyan-50/40">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-black text-slate-900">{row.stock.name}</div>
                      <div className="mt-1 text-[11px] font-bold text-slate-400">{row.stock.code} · {row.stock.industry}</div>
                    </div>
                    <Badge label={row.logic_gate_status} tone={statusTone(row.logic_gate_status)} />
                  </div>
                  <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-600">{row.sniper_focus[0] ?? row.investment_thesis}</p>
                </Link>
              ))}
              {priorityRows.length === 0 && <EmptyState text="暂无符合条件的验证队列" />}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2 text-sm font-black text-slate-900">
              <ShieldAlert size={17} className="text-rose-600" /> 只看边际变化
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {priorityRows.map((row) => (
                <div key={`${row.stock_code}-change`} className="rounded-xl bg-slate-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-black text-slate-900">{row.stock.name}</div>
                    <span className="text-[11px] font-black text-slate-500">{row.thesis_score.toFixed(1)}</span>
                  </div>
                  <ul className="mt-3 space-y-2">
                    {(row.marginal_changes ?? []).slice(0, 3).map((item) => (
                      <li key={item} className="text-xs leading-5 text-slate-600">{item}</li>
                    ))}
                  </ul>
                </div>
              ))}
              {priorityRows.length === 0 && <EmptyState text="没有边际变化样本" />}
            </div>
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
  const valuation = row.valuation_simulation;
  const scenarios = valuation.scenarios ?? [];
  const focus = row.sniper_focus.length ? row.sniper_focus : row.missing_evidence.slice(0, 4);
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="grid gap-6 xl:grid-cols-[260px_1fr_260px]">
        <div>
          <Link href={`/stocks/${encodeURIComponent(row.stock.code)}?from=/research/thesis`} className="text-xl font-black text-slate-900 hover:text-cyan-700">
            {row.stock.name}
          </Link>
          <div className="mt-1 text-xs font-bold text-slate-400">{row.stock.code} · {marketLabel(row.stock.market)} · {row.stock.industry}</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge label={stageLabel(row.stage)} tone={row.stage === "blocked" ? "danger" : "neutral"} />
            <Badge label={`数据${row.data_gate_status}`} tone={statusTone(row.data_gate_status)} />
            <Badge label={`逻辑${row.logic_gate_status}`} tone={statusTone(row.logic_gate_status)} />
          </div>
          <div className="mt-5 grid grid-cols-2 gap-3">
            <ScoreBox label="假设分" value={row.thesis_score} />
            <ScoreBox label="反证压" value={row.anti_thesis_score} danger={row.anti_thesis_score >= 55} />
            <ScoreBox label="门控分" value={row.logic_gate_score} />
            <ScoreBox label="准备度" value={row.readiness_score} />
          </div>
          <Link href={`/research/thesis/${encodeURIComponent(row.stock.code)}`} className="mt-5 inline-flex items-center gap-1 text-xs font-black uppercase tracking-widest text-cyan-700">
            进入详情 <ChevronRight size={14} />
          </Link>
        </div>

        <div className="space-y-5">
          <p className="text-sm leading-6 text-slate-600">{row.investment_thesis}</p>
          <div className="grid gap-3 md:grid-cols-3">
            <CaseBlock label="TAM/估值" text={valuation.summary ?? row.base_case} tone={valuationTone(valuation.valuation_ceiling_status)} />
            <CaseBlock label="反共识" text={row.contrarian_signal.explanation ?? "暂无明显反共识信号。"} tone={row.contrarian_signal.reversal_watch ? "warn" : "neutral"} />
            <CaseBlock label="反证压力" text={row.anti_thesis_items[0]?.action ?? row.bear_case} tone={row.anti_thesis_score >= 55 ? "danger" : "neutral"} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <div className="mb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">Logic Gates</div>
              <div className="space-y-2">
                {row.logic_gates.slice(0, 5).map((gate) => <GateRow key={gate.id} gate={gate} />)}
              </div>
            </div>
            <div>
              <div className="mb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">Alternative Data Proxy</div>
              <div className="space-y-2">
                {row.alternative_data_signals.slice(0, 4).map((signal) => <SignalRow key={signal.id} signal={signal} />)}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div>
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">狙击焦点</div>
            <div className="mt-3 space-y-2">
              {focus.slice(0, 5).map((item) => (
                <div key={item} className="rounded-xl bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600">{item}</div>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">Valuation Scenarios</div>
            <div className="space-y-2">
              {scenarios.map((scenario) => (
                <div key={scenario.scenario} className="grid grid-cols-[54px_1fr_52px] items-center gap-3 rounded-xl bg-slate-50 px-3 py-2">
                  <div className="text-[10px] font-black uppercase text-slate-500">{scenario.scenario}</div>
                  <div className="h-2 rounded-full bg-white">
                    <div className="h-2 rounded-full bg-cyan-700" style={{ width: `${Math.max(4, Math.min(100, scenario.room_multiple * 18))}%` }} />
                  </div>
                  <div className="text-right text-[11px] font-black text-slate-700">{scenario.room_multiple.toFixed(1)}x</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

function TopLink({ href, label, icon }: { href: string; label: string; icon: React.ReactNode }) {
  return (
    <Link href={href} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-600 hover:border-slate-300 hover:text-slate-900">
      {icon}
      {label}
      <ArrowUpRight size={15} />
    </Link>
  );
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: number | string; tone?: "neutral" | "warn" | "danger" | "pass" }) {
  const cls = tone === "danger" ? "text-rose-600" : tone === "warn" ? "text-amber-600" : tone === "pass" ? "text-emerald-600" : "text-slate-900";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-1 text-3xl font-black ${cls}`}>{value}</div>
    </div>
  );
}

function CaseBlock({ label, text, tone = "neutral" }: { label: string; text: string; tone?: "neutral" | "warn" | "danger" | "pass" }) {
  const cls = tone === "danger" ? "border-rose-100 bg-rose-50" : tone === "warn" ? "border-amber-100 bg-amber-50" : tone === "pass" ? "border-emerald-100 bg-emerald-50" : "border-slate-100 bg-slate-50";
  return (
    <div className={`rounded-xl border p-3 ${cls}`}>
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className="mt-1 text-xs leading-5 text-slate-600">{text}</div>
    </div>
  );
}

function GateRow({ gate }: { gate: TenbaggerLogicGate }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-black text-slate-800">{gate.title}</div>
        <Badge label={gate.status} tone={gateStatusTone(gate.status)} />
      </div>
      <div className="mt-1 text-[11px] leading-4 text-slate-500">{gate.metric}</div>
    </div>
  );
}

function SignalRow({ signal }: { signal: TenbaggerAlternativeSignal }) {
  return (
    <div className="grid grid-cols-[1fr_44px] items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
      <div>
        <div className="text-xs font-black text-slate-800">{signal.label}</div>
        <div className="mt-1 text-[10px] font-bold text-slate-400">{signal.coverage_status}</div>
      </div>
      <div className="text-right text-xs font-black text-cyan-700">{signal.score.toFixed(0)}</div>
    </div>
  );
}

function ScoreBox({ label, value, danger = false }: { label: string; value: number; danger?: boolean }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-1 text-lg font-black ${danger ? "text-rose-600" : "text-slate-900"}`}>{value.toFixed(1)}</div>
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

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">{text}</div>;
}

function stageLabel(stage: string) {
  return ({ candidate: "候选", verification: "验证", discovery: "发现", blocked: "阻断" } as Record<string, string>)[stage] ?? stage;
}

function statusTone(status: string): "neutral" | "warn" | "danger" | "pass" {
  if (status === "PASS") return "pass";
  if (status === "FAIL") return "danger";
  if (status === "WARN") return "warn";
  return "neutral";
}

function gateStatusTone(status: string): "neutral" | "warn" | "danger" | "pass" {
  if (status === "pass") return "pass";
  if (status === "fail") return "danger";
  if (status === "watch" || status === "pending") return "warn";
  return "neutral";
}

function valuationTone(status?: string): "neutral" | "warn" | "danger" | "pass" {
  if (status === "room") return "pass";
  if (status === "balanced") return "warn";
  if (status === "stretched") return "danger";
  return "neutral";
}

function gateToneFromScore(score: number): "neutral" | "warn" | "danger" | "pass" {
  if (score >= 76) return "pass";
  if (score >= 45) return "warn";
  if (score > 0) return "danger";
  return "neutral";
}
