"use client";

import { useEffect, useState } from "react";
import { BarChart3, Play } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type SignalBacktestLatest, type SignalBacktestRun } from "@/lib/api";
import { MARKET_OPTIONS, marketLabel } from "@/lib/markets";

export default function BacktestPage() {
  const [payload, setPayload] = useState<SignalBacktestLatest | null>(null);
  const [market, setMarket] = useState("ALL");
  const [horizon, setHorizon] = useState(120);
  const [minScore, setMinScore] = useState(0);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    api.latestBacktest()
      .then(setPayload)
      .catch((err: Error) => setError(`回测结果读取失败：${err.message}`))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const run = () => {
    setRunning(true);
    setError("");
    api.runBacktest({ horizon_days: horizon, min_score: minScore, market })
      .then(() => api.latestBacktest())
      .then(setPayload)
      .catch((err: Error) => setError(`回测运行失败：${err.message}`))
      .finally(() => setRunning(false));
  };

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载信号校准" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  const latest = payload?.latest ?? null;

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <section className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
              <BarChart3 size={14} /> Signal Calibration
            </div>
            <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900">信号回测与校准</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-500">按 as-of 信号日计算未来收益，只用于规则校准和样本检验。</p>
          </div>
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              市场
              <select value={market} onChange={(event) => setMarket(event.target.value)} className="mt-1 block h-10 rounded-xl bg-slate-50 px-3 text-xs font-bold text-slate-600">
                {MARKET_OPTIONS.map((item) => <option key={item} value={item}>{marketLabel(item)}</option>)}
              </select>
            </label>
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              周期
              <input value={horizon} onChange={(event) => setHorizon(Number(event.target.value) || 120)} type="number" min={20} max={500} className="mt-1 block h-10 w-24 rounded-xl bg-slate-50 px-3 text-xs font-bold text-slate-600" />
            </label>
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              最低分
              <input value={minScore} onChange={(event) => setMinScore(Number(event.target.value) || 0)} type="number" min={0} max={100} className="mt-1 block h-10 w-24 rounded-xl bg-slate-50 px-3 text-xs font-bold text-slate-600" />
            </label>
            <button type="button" onClick={run} disabled={running} className="inline-flex h-10 items-center gap-2 rounded-xl bg-slate-900 px-4 text-xs font-black uppercase tracking-widest text-white disabled:opacity-50">
              <Play size={14} /> {running ? "运行中" : "运行校准"}
            </button>
          </div>
        </section>

        {latest ? (
          <>
            <section className="grid gap-4 md:grid-cols-5">
              <Metric label="样本数" value={latest.sample_count} />
              <Metric label="平均收益" value={pct(latest.average_forward_return)} />
              <Metric label="中位收益" value={pct(latest.median_forward_return)} />
              <Metric label="最大收益均值" value={pct(latest.average_max_return)} />
              <Metric label="2x 命中率" value={pct(latest.hit_rate_2x)} />
            </section>
            <section className="rounded-2xl border border-slate-200 bg-white p-6">
              <div className="text-sm text-slate-600">{latest.explanation}</div>
              <div className="mt-2 text-xs font-bold text-slate-400">{latest.run_key}</div>
            </section>
            <section className="grid gap-6 lg:grid-cols-3">
              <SummaryTable title="按分数分层" rows={latest.bucket_summary} />
              <SummaryTable title="按评级分层" rows={latest.rating_summary} />
              <SummaryTable title="按置信度分层" rows={latest.confidence_summary} />
            </section>
          </>
        ) : (
          <div className="rounded-2xl border-2 border-dashed border-slate-200 p-12 text-center text-sm text-slate-400">
            暂无回测结果，运行一次校准任务。
          </div>
        )}

        {(payload?.runs ?? []).length > 0 && (
          <section className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="text-lg font-black text-slate-900">最近运行</h2>
            <div className="mt-4 divide-y divide-slate-100">
              {(payload?.runs ?? []).map((run) => <RunRow key={run.run_key} run={run} />)}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className="mt-1 text-3xl font-black text-slate-900">{value}</div>
    </div>
  );
}

function SummaryTable({ title, rows }: { title: string; rows: SignalBacktestRun["bucket_summary"] }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-black uppercase tracking-widest text-slate-500">{title}</h2>
      <div className="mt-4 space-y-3">
        {rows.map((row) => (
          <div key={row.bucket} className="grid grid-cols-[70px_1fr_70px] items-center gap-3 text-xs">
            <div className="font-black text-slate-700">{row.bucket}</div>
            <div className="h-2 rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-indigo-600" style={{ width: `${Math.max(2, Math.min(100, row.hit_rate_2x * 100))}%` }} />
            </div>
            <div className="text-right font-bold text-slate-500">{row.sample_count} / {pct(row.average_forward_return)}</div>
          </div>
        ))}
        {rows.length === 0 && <div className="text-sm text-slate-400">暂无样本</div>}
      </div>
    </div>
  );
}

function RunRow({ run }: { run: SignalBacktestRun }) {
  return (
    <div className="grid gap-3 py-3 text-sm md:grid-cols-[1fr_90px_90px_90px]">
      <div>
        <div className="font-bold text-slate-900">{run.run_key}</div>
        <div className="text-xs text-slate-400">{run.explanation}</div>
      </div>
      <div className="font-bold text-slate-600">{run.sample_count} 样本</div>
      <div className="font-bold text-slate-600">{pct(run.average_forward_return)}</div>
      <div className="font-bold text-slate-600">{pct(run.hit_rate_2x)} 2x</div>
    </div>
  );
}

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}
