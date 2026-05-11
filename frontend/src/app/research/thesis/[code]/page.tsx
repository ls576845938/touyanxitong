"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, CheckCircle2, XCircle } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type TenbaggerThesisRow } from "@/lib/api";

export default function ThesisDetailPage() {
  const params = useParams<{ code: string }>();
  const code = decodeURIComponent(params.code);
  const [latest, setLatest] = useState<TenbaggerThesisRow | null>(null);
  const [history, setHistory] = useState<TenbaggerThesisRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.tenbaggerThesis(code)
      .then((payload) => {
        setLatest(payload.latest);
        setHistory(payload.history);
      })
      .catch((err: Error) => setError(`Thesis 明细读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [code]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载 thesis 明细" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!latest) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="暂无 thesis 数据" /></div>;

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <div className="mx-auto max-w-6xl space-y-8">
        <Link href="/research/thesis" className="inline-flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-slate-900">
          <ArrowLeft size={16} /> 返回 Thesis
        </Link>

        <section className="rounded-2xl border border-slate-200 bg-white p-8">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <h1 className="text-4xl font-black text-slate-900">{latest.stock.name}</h1>
              <div className="mt-2 text-sm font-bold text-slate-400">{latest.stock.code} · {latest.stock.industry} · {latest.trade_date}</div>
              <p className="mt-5 max-w-3xl text-base leading-7 text-slate-600">{latest.investment_thesis}</p>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Thesis Score</div>
              <div className="text-5xl font-black text-slate-900">{latest.thesis_score.toFixed(1)}</div>
              <div className="mt-2 text-xs font-black uppercase tracking-widest text-slate-500">{latest.stage} · {latest.data_gate_status}</div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <TextPanel title="Base Case" text={latest.base_case} />
          <TextPanel title="Bull Case" text={latest.bull_case} />
          <TextPanel title="Bear Case" text={latest.bear_case} />
        </section>

        <section className="grid gap-6 lg:grid-cols-2">
          <ListPanel icon="check" title="关键里程碑" items={latest.key_milestones} />
          <ListPanel icon="x" title="证伪条件" items={latest.disconfirming_evidence} />
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-black text-slate-900">历史变化</h2>
          <div className="mt-5 space-y-3">
            {history.map((row) => (
              <div key={row.trade_date} className="grid grid-cols-[120px_1fr_80px] items-center gap-4 rounded-xl bg-slate-50 px-4 py-3">
                <div className="text-xs font-bold text-slate-500">{row.trade_date}</div>
                <div className="h-2 rounded-full bg-slate-200">
                  <div className="h-2 rounded-full bg-indigo-600" style={{ width: `${Math.max(2, Math.min(100, row.thesis_score))}%` }} />
                </div>
                <div className="text-right text-sm font-black text-slate-900">{row.thesis_score.toFixed(1)}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function TextPanel({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{title}</div>
      <p className="mt-3 text-sm leading-6 text-slate-600">{text}</p>
    </div>
  );
}

function ListPanel({ title, items, icon }: { title: string; items: string[]; icon: "check" | "x" }) {
  const Icon = icon === "check" ? CheckCircle2 : XCircle;
  const color = icon === "check" ? "text-emerald-600" : "text-rose-600";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-lg font-black text-slate-900">{title}</h2>
      <div className="mt-4 space-y-3">
        {items.map((item) => (
          <div key={item} className="flex gap-3 text-sm text-slate-600">
            <Icon size={17} className={`mt-0.5 shrink-0 ${color}`} />
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
