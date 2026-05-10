"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowUpRight, CalendarDays, Flame, Hash, Newspaper, RadioTower, RefreshCcw } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type ResearchHotIndustry, type ResearchHotTerm, type ResearchHotTerms } from "@/lib/api";

type HotWindow = "1d" | "7d";

const WINDOWS: Array<{ key: HotWindow; label: string }> = [
  { key: "1d", label: "今日" },
  { key: "7d", label: "近一周" }
];

export default function HotTermsPage() {
  const [windowKey, setWindowKey] = useState<HotWindow>("1d");
  const [payload, setPayload] = useState<ResearchHotTerms | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api.researchHotTerms({ window: windowKey, limit: 80 })
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`热词雷达读取失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [windowKey]);

  const summary = useMemo(() => {
    return [
      { label: "热门板块", value: payload?.summary.industry_count ?? 0, tone: "amber" as const },
      { label: "热词数量", value: payload?.summary.term_count ?? 0, tone: "orange" as const },
      { label: "资讯条目", value: payload?.summary.article_count ?? 0, tone: "red" as const },
      { label: "活跃来源", value: payload?.summary.source_count ?? 0, tone: "amber" as const }
    ];
  }, [payload]);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载资讯平台热词雷达" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;
  if (!payload) return <div className="page-shell"><ErrorState message="热词雷达数据为空" /></div>;

  return (
    <div className="page-shell space-y-5 bg-white">
      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="label">Research Hot Terms</div>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">资讯平台热词雷达</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
              聚合本地资讯库、产业热度和关键词映射，按今日与近一周识别正在升温的产业板块；外部平台未入库时明确显示为待接入。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/industry/chain" className="inline-flex h-10 items-center gap-2 rounded-md border border-[#f2dfd2] px-4 text-sm hover:border-orange-300">
              <Flame size={16} /> 产业链地图
            </Link>
            <Link href="/research/brief" className="inline-flex h-10 items-center gap-2 rounded-md border border-[#f2dfd2] px-4 text-sm hover:border-orange-300">
              <Newspaper size={16} /> 每日工作单
            </Link>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          {WINDOWS.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setWindowKey(item.key)}
              className={`h-10 rounded-md border px-4 text-sm transition ${
                windowKey === item.key ? "border-orange-500 bg-orange-500 text-white" : "border-[#f2dfd2] bg-white text-slate-700 hover:border-orange-300"
              }`}
            >
              {item.label}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
            <RefreshCcw size={14} className="text-orange-600" />
            快照 {payload.latest_date ?? "-"} / 更新 {formatShortDate(payload.updated_at)}
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-4">
        {summary.map((item) => (
          <Metric key={item.label} label={item.label} value={item.value} tone={item.tone} />
        ))}
      </section>

      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <RadioTower size={16} className="text-orange-600" />
          数据源状态
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
          {payload.sources.map((source) => (
            <div key={source.key} className="rounded-md border border-[#f2dfd2] bg-[#fffaf5] p-3">
              <div className="font-medium text-slate-900">{source.label}</div>
              <div className="mt-2">
                <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${sourceStatusClass(source.status)}`}>
                  {sourceStatusLabel(source.status)}
                </span>
              </div>
              <div className="mono mt-3 text-xs text-slate-500">{source.article_count} 条</div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.08fr_0.92fr]">
        <Panel title="热门产业板块" icon={<CalendarDays size={16} />} count={payload.hot_industries.length}>
          <div className="space-y-3">
            {payload.hot_industries.slice(0, 14).map((item) => (
              <IndustryRow key={item.industry} item={item} />
            ))}
            {payload.hot_industries.length === 0 ? <EmptyHint label="当前窗口暂无热门产业板块" /> : null}
          </div>
        </Panel>

        <Panel title="平台热词" icon={<Hash size={16} />} count={payload.hot_terms.length}>
          <div className="grid gap-3 sm:grid-cols-2">
            {payload.hot_terms.slice(0, 20).map((item) => (
              <TermCard key={item.term} item={item} />
            ))}
            {payload.hot_terms.length === 0 ? <EmptyHint label="当前窗口暂无平台热词" /> : null}
          </div>
        </Panel>
      </section>

      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-950">
          <Flame size={18} className="text-orange-600" />
          分平台热词矩阵
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {payload.platform_terms.map((source) => (
            <div key={source.key} className="rounded-lg border border-[#f2dfd2] bg-[#fffaf5] p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold text-slate-900">{source.label}</div>
                  <div className="mt-1 text-xs text-slate-500">{source.kind}</div>
                </div>
                <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${sourceStatusClass(source.status)}`}>
                  {sourceStatusLabel(source.status)}
                </span>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {source.terms.length ? source.terms.slice(0, 10).map((term) => (
                  <span key={term.term} className="rounded-md border border-[#f2dfd2] bg-white px-2 py-1 text-xs text-slate-700">
                    {term.term}
                  </span>
                )) : <span className="text-xs text-slate-500">暂无入库热词</span>}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Panel({ title, icon, count, children }: { title: string; icon: ReactNode; count: number; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
          <span className="text-orange-600">{icon}</span>
          {title}
        </div>
        <div className="mono text-sm font-semibold text-orange-700">{count}</div>
      </div>
      {children}
    </section>
  );
}

function IndustryRow({ item }: { item: ResearchHotIndustry }) {
  const color = heatColor(item.intensity);
  return (
    <article className="rounded-lg border border-[#f2dfd2] bg-[#fffdf9] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-base font-semibold text-slate-950">{item.industry}</div>
          <div className="mt-1 text-xs text-slate-500">{item.mentions} 次命中 / {formatShortDate(item.latest_at)}</div>
        </div>
        <div className="mono text-right text-sm font-semibold" style={{ color }}>
          {item.score.toFixed(1)}
        </div>
      </div>
      <div className="mt-3 h-2 rounded-full bg-[#ffedd5]">
        <div className="h-full rounded-full" style={{ width: `${Math.max(item.intensity * 100, 8)}%`, backgroundColor: color }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {item.top_terms.slice(0, 5).map((term) => (
          <span key={term.term} className="rounded-md bg-white px-2 py-1 text-xs text-slate-700 ring-1 ring-[#f2dfd2]">
            {term.term}
          </span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.sources.slice(0, 4).map((source) => (
          <span key={source.key} className="rounded-full bg-[#fff4e6] px-2 py-0.5 text-[11px] text-orange-800">
            {source.label} {source.count}
          </span>
        ))}
      </div>
    </article>
  );
}

function TermCard({ item }: { item: ResearchHotTerm }) {
  const color = heatColor(item.intensity);
  return (
    <article className="rounded-lg border border-[#f2dfd2] bg-[#fffdf9] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-slate-950">{item.term}</div>
          <div className="mt-1 text-xs text-slate-500">{item.mentions} 次命中</div>
        </div>
        <div className="mono text-right text-sm font-semibold" style={{ color }}>
          {item.score.toFixed(1)}
        </div>
      </div>
      <div className="mt-3 h-2 rounded-full bg-[#ffedd5]">
        <div className="h-full rounded-full" style={{ width: `${Math.max(item.intensity * 100, 8)}%`, backgroundColor: color }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.industries.slice(0, 4).map((industry) => (
          <span key={industry.key} className="rounded-md bg-white px-2 py-1 text-xs text-slate-700 ring-1 ring-[#f2dfd2]">
            {industry.label}
          </span>
        ))}
      </div>
      {item.examples[0]?.url ? (
        <a href={item.examples[0].url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-orange-700">
          来源样本 <ArrowUpRight size={12} />
        </a>
      ) : null}
    </article>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone: "amber" | "orange" | "red" }) {
  return (
    <div className="rounded-lg border border-[#f2dfd2] bg-white p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mono mt-2 text-2xl font-semibold ${metricToneClass(tone)}`}>{value}</div>
    </div>
  );
}

function EmptyHint({ label }: { label: string }) {
  return <div className="rounded-md border border-dashed border-[#f2dfd2] px-3 py-3 text-sm text-slate-500">{label}</div>;
}

function sourceStatusLabel(status: string) {
  if (status === "active") return "有数据";
  if (status === "pending_connector") return "待接入";
  if (status === "internal_ready") return "待生成";
  return status;
}

function sourceStatusClass(status: string) {
  if (status === "active") return "bg-red-50 text-red-700 ring-1 ring-red-200";
  if (status === "pending_connector") return "bg-slate-100 text-slate-500 ring-1 ring-slate-200";
  if (status === "internal_ready") return "bg-amber-50 text-amber-700 ring-1 ring-amber-200";
  return "bg-slate-100 text-slate-700 ring-1 ring-slate-200";
}

function metricToneClass(tone: "amber" | "orange" | "red") {
  if (tone === "amber") return "text-amber-600";
  if (tone === "orange") return "text-orange-600";
  return "text-red-600";
}

function heatColor(intensity: number) {
  if (!Number.isFinite(intensity) || intensity <= 0.24) return "#facc15";
  if (intensity <= 0.5) return "#f59e0b";
  if (intensity <= 0.78) return "#f97316";
  return "#dc2626";
}

function formatShortDate(value: string | null | undefined) {
  if (!value) return "-";
  return value.slice(0, 10);
}
