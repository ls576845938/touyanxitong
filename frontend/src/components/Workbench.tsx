"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { type QualityFlag, type WorkbenchTone, riskPrompt } from "@/lib/research-workbench";

export function WorkbenchHeader({
  eyebrow,
  title,
  summary,
  actions
}: {
  eyebrow: string;
  title: string;
  summary: string;
  actions?: React.ReactNode;
}) {
  return (
    <section className="flex flex-wrap items-end justify-between gap-6">
      <div className="max-w-3xl space-y-2">
        <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{eyebrow}</div>
        <h1 className="text-3xl font-black tracking-tight text-slate-900 lg:text-4xl">{title}</h1>
        <p className="text-sm leading-6 text-slate-500">{summary}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
    </section>
  );
}

export function WorkbenchLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 text-sm font-bold text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900"
    >
      {label}
      <ArrowRight size={16} />
    </Link>
  );
}

export function QualityBanner({ flags, fallbackLabel }: { flags: QualityFlag[]; fallbackLabel?: string }) {
  if (!flags.length && !fallbackLabel) return null;
  const tone = flags.length ? "fail" : "warn";
  return (
    <div
      className={cn(
        "flex flex-wrap items-start gap-3 rounded-2xl border px-5 py-4 text-sm",
        tone === "fail" ? "border-rose-200 bg-rose-50 text-rose-900" : "border-amber-200 bg-amber-50 text-amber-900"
      )}
    >
      <div className={cn("mt-0.5 flex h-8 w-8 items-center justify-center rounded-xl", tone === "fail" ? "bg-rose-100" : "bg-amber-100")}>
        {tone === "fail" ? <ShieldAlert size={18} /> : <AlertTriangle size={18} />}
      </div>
      <div className="space-y-1">
        <div className="text-[10px] font-black uppercase tracking-widest">
          {flags.length ? flags.join(" / ") : "FALLBACK"}
        </div>
        <p>{flags.length ? riskPrompt(flags) : fallbackLabel}</p>
      </div>
    </div>
  );
}

export function SectionCard({
  title,
  subtitle,
  children
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm lg:p-7">
      <div className="mb-5">
        <h2 className="text-lg font-black tracking-tight text-slate-900">{title}</h2>
        {subtitle ? <p className="mt-1 text-xs text-slate-500">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function MetricTile({
  label,
  value,
  detail,
  tone = "neutral"
}: {
  label: string;
  value: string | number;
  detail?: string;
  tone?: WorkbenchTone;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div
        className={cn(
          "mt-2 text-2xl font-black tracking-tight",
          tone === "fail"
            ? "text-rose-600"
            : tone === "warn"
              ? "text-amber-600"
              : tone === "pass"
                ? "text-emerald-600"
                : "text-slate-900"
        )}
      >
        {value}
      </div>
      {detail ? <div className="mt-2 text-xs leading-5 text-slate-500">{detail}</div> : null}
    </div>
  );
}

export function TonePill({ label, tone = "neutral" }: { label: string; tone?: WorkbenchTone }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wider",
        tone === "fail"
          ? "bg-rose-50 text-rose-700"
          : tone === "warn"
            ? "bg-amber-50 text-amber-700"
            : tone === "pass"
              ? "bg-emerald-50 text-emerald-700"
              : "bg-slate-100 text-slate-600"
      )}
    >
      {label}
    </span>
  );
}

export function RecordList({ records }: { records: Array<{ date: string | null; title: string; detail: string; tone?: WorkbenchTone; tags?: string[] }> }) {
  return (
    <div className="space-y-3">
      {records.map((record) => (
        <div key={`${record.date ?? "na"}-${record.title}`} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm font-bold text-slate-900">{record.title}</div>
            <div className="flex flex-wrap items-center gap-2">
              {record.tags?.map((tag) => <TonePill key={tag} label={tag} tone={record.tone} />)}
              <div className="text-[11px] font-bold text-slate-400">{record.date ?? "--"}</div>
            </div>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-600">{record.detail}</p>
        </div>
      ))}
      {records.length === 0 ? <div className="rounded-2xl border border-dashed border-slate-200 p-5 text-sm text-slate-400">暂无操作记录</div> : null}
    </div>
  );
}
