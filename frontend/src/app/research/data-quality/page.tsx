"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Database, ShieldCheck } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type DataQuality, type DataStatus, type ResearchDataGate } from "@/lib/api";

export default function ResearchDataQualityPage() {
  const [quality, setQuality] = useState<DataQuality | null>(null);
  const [status, setStatus] = useState<DataStatus | null>(null);
  const [gate, setGate] = useState<ResearchDataGate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.researchDataGate({ limit: 50 })
      .then(setGate)
      .catch((err: Error) => setError(`数据门控读取失败：${err.message}`))
      .finally(() => setLoading(false));

    void Promise.allSettled([api.dataQuality(), api.dataStatus({ includeSourceCoverage: true })])
      .then(([qualityPayload, statusPayload]) => {
        setQuality(qualityPayload.status === "fulfilled" ? qualityPayload.value : null);
        setStatus(statusPayload.status === "fulfilled" ? statusPayload.value : null);
      });
  }, []);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载正式数据门控" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  const sourceRows = status?.source_coverage ?? [];

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <section className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
              <ShieldCheck size={14} /> Formal Research Gate
            </div>
            <h1 className="mt-2 text-4xl font-bold tracking-tight text-slate-900">正式研究数据门控</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-500">
              将 mock/fallback、低置信行情、基本面缺口和证据不足统一拦截在 thesis 之前。
            </p>
          </div>
          <Link href="/research/thesis" className="inline-flex h-11 items-center gap-2 rounded-xl bg-slate-900 px-4 text-sm font-bold text-white">
            Thesis Engine
          </Link>
        </section>

        <section className="grid gap-4 md:grid-cols-5">
          <Metric label="质量门" value={quality?.status ?? "-"} tone={quality?.status} />
          <Metric label="FAIL" value={quality?.summary.fail_count ?? 0} tone="FAIL" />
          <Metric label="WARN" value={quality?.summary.warn_count ?? 0} tone="WARN" />
          <Metric label="正式通过" value={gate?.summary.pass_count ?? 0} tone="PASS" />
          <Metric label="通过率" value={`${((gate?.summary.formal_ready_ratio ?? 0) * 100).toFixed(1)}%`} />
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="flex items-center gap-2 text-lg font-black text-slate-900"><Database size={18} /> 市场覆盖</h2>
            <div className="mt-5 space-y-3">
              {(quality?.segments ?? []).map((segment) => (
                <div key={`${segment.market}-${segment.board}`} className="rounded-xl bg-slate-50 p-4">
                  <div className="flex items-center justify-between text-sm">
                    <div className="font-black text-slate-900">{segment.market_label} / {segment.board_label}</div>
                    <StatusPill status={segment.status} />
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-3 text-xs text-slate-500">
                    <span>覆盖 {(segment.coverage_ratio * 100).toFixed(1)}%</span>
                    <span>真实 {((segment.real_coverage_ratio ?? 0) * 100).toFixed(1)}%</span>
                    <span>长期 {(segment.preferred_history_ratio * 100).toFixed(1)}%</span>
                  </div>
                </div>
              ))}
              {(!quality || quality.segments.length === 0) && (
                <div className="rounded-xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">
                  市场覆盖明细后台加载中
                </div>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6">
            <h2 className="text-lg font-black text-slate-900">来源结构</h2>
            <div className="mt-5 space-y-3">
              {sourceRows.map((row) => (
                <div key={`${row.source_kind}-${row.source}`} className="grid grid-cols-[90px_1fr_90px] items-center gap-3 rounded-xl bg-slate-50 p-4 text-sm">
                  <StatusPill status={row.source_kind.toUpperCase()} />
                  <div className="font-bold text-slate-700">{row.source}</div>
                  <div className="text-right text-xs font-bold text-slate-500">{row.stocks_with_bars} 只</div>
                </div>
              ))}
              {sourceRows.length === 0 && <div className="text-sm text-slate-400">暂无来源覆盖数据</div>}
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-black text-slate-900">正式研究阻断样本</h2>
          <div className="mt-5 divide-y divide-slate-100">
            {(gate?.rows ?? []).map((row) => (
              <div key={row.code} className="grid gap-4 py-4 lg:grid-cols-[260px_120px_1fr]">
                <div>
                  <div className="font-black text-slate-900">{row.name}</div>
                  <div className="text-xs font-bold text-slate-400">{row.code} · {row.industry}</div>
                </div>
                <div><StatusPill status={row.status} /></div>
                <div className="text-sm text-slate-600">{row.reasons.slice(0, 3).join("；")}</div>
              </div>
            ))}
            {(gate?.rows ?? []).length === 0 && <div className="py-8 text-sm text-slate-400">暂无门控样本</div>}
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  const color = tone === "FAIL" ? "text-rose-600" : tone === "WARN" ? "text-amber-600" : tone === "PASS" ? "text-emerald-600" : "text-slate-900";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-1 text-3xl font-black ${color}`}>{value}</div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  const cls = normalized === "FAIL" || normalized === "MOCK" || normalized === "FALLBACK"
    ? "bg-rose-50 text-rose-700"
    : normalized === "WARN" || normalized === "UNKNOWN"
      ? "bg-amber-50 text-amber-700"
      : "bg-emerald-50 text-emerald-700";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${cls}`}>{status}</span>;
}
