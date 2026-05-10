"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, CalendarDays, Flame } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { IndustryTimelineChart } from "@/components/IndustryTimelineChart";
import { LoadingState } from "@/components/LoadingState";
import { api, type IndustryTimeline, type IndustryTimelineItem, type IndustryTimelineRow } from "@/lib/api";

export default function IndustryReviewPage() {
  const [timeline, setTimeline] = useState<IndustryTimeline | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.industryTimeline(60)
      .then((payload) => {
        setTimeline(payload);
        setSelectedDate(payload.latest?.trade_date ?? null);
      })
      .catch((err: Error) => setError(`赛道复盘读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(() => {
    if (!timeline?.timeline.length) return null;
    return timeline.timeline.find((item) => item.trade_date === selectedDate) ?? timeline.timeline[0];
  }, [timeline, selectedDate]);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载赛道复盘" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="label">Industry Review</div>
        <h1 className="mt-2 text-2xl font-semibold">赛道热度变化复盘</h1>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
          跟踪产业热度的持续性、扩散度和降温风险。这里不输出交易建议，只帮助你判断观察池背后的赛道逻辑是否仍在增强。
        </p>
      </section>

      {selected ? (
        <>
          <section className="grid gap-3 md:grid-cols-5">
            <Metric label="复盘日期" value={selected.trade_date} />
            <Metric label="赛道数量" value={selected.summary.industry_count} />
            <Metric label="热赛道" value={selected.summary.hot_industry_count} />
            <Metric label="升温" value={selected.summary.rising_count} />
            <Metric label="降温" value={selected.summary.cooling_count} />
          </section>

          <section className="grid gap-4 lg:grid-cols-[0.78fr_1.22fr]">
            <div className="panel p-4">
              <div className="mb-3 flex items-center gap-2 font-semibold"><CalendarDays size={18} />历史快照</div>
              <div className="space-y-2">
                {(timeline?.timeline ?? []).map((item) => (
                  <TimelineButton key={item.trade_date} item={item} active={item.trade_date === selected.trade_date} onClick={() => setSelectedDate(item.trade_date)} />
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <section className="panel p-5">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-lg font-semibold"><Flame size={18} />热度总览</div>
                    <p className="mt-1 text-sm text-slate-600">总热度、升温赛道数和降温赛道数，用于观察产业热度是否持续扩散。</p>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-right text-sm">
                    <MiniStat label="总热度" value={selected.summary.total_heat_score.toFixed(1)} />
                    <MiniStat label="平均热度" value={selected.summary.average_heat_score.toFixed(1)} />
                  </div>
                </div>
                <IndustryTimelineChart rows={timeline?.timeline ?? []} />
              </section>

              <section className="grid gap-4 lg:grid-cols-2">
                <IndustryList title="升温赛道" icon="up" rows={selected.rising_industries} />
                <IndustryList title="降温赛道" icon="down" rows={selected.cooling_industries} />
              </section>

              <section className="panel overflow-hidden">
                <div className="border-b border-line p-5">
                  <h2 className="text-lg font-semibold">当日赛道热度表</h2>
                  <p className="mt-1 text-sm text-slate-600">按热度分排序，保留核心关键词和热度变化，方便后续关联观察池股票。</p>
                </div>
                <IndustryTable rows={selected.industries} />
              </section>
            </div>
          </section>
        </>
      ) : (
        <section className="panel p-5 text-sm text-slate-600">当前没有产业热度复盘记录。</section>
      )}
    </div>
  );
}

function TimelineButton({ item, active, onClick }: { item: IndustryTimelineItem; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-md border p-3 text-left ${active ? "border-mint bg-mint/10" : "border-line bg-white hover:border-mint"}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="mono font-semibold">{item.trade_date}</div>
        <div className="label">{item.previous_date ?? "首日"} 对比</div>
      </div>
      <div className="mt-2 grid grid-cols-4 gap-2 text-xs">
        <MiniStat label="热度" value={item.summary.total_heat_score.toFixed(1)} />
        <MiniStat label="热赛道" value={item.summary.hot_industry_count} />
        <MiniStat label="升温" value={item.summary.rising_count} />
        <MiniStat label="降温" value={item.summary.cooling_count} />
      </div>
    </button>
  );
}

function IndustryList({ title, rows, icon }: { title: string; rows: IndustryTimelineRow[]; icon: "up" | "down" }) {
  const Icon = icon === "up" ? ArrowUpRight : ArrowDownRight;
  return (
    <div className="panel p-5">
      <div className="mb-3 flex items-center gap-2 text-lg font-semibold"><Icon size={18} />{title}</div>
      <div className="space-y-3">
        {rows.slice(0, 8).map((row) => (
          <div key={`${title}-${row.industry_id}`} className="rounded-md border border-line bg-slate-50 p-3">
            <div className="flex items-center justify-between gap-3">
            <Link href={`/industry/${row.industry_id}`} className="font-medium hover:text-mint">{row.name}</Link>
              <div className={`mono font-semibold ${icon === "up" ? "text-emerald-700" : "text-rose"}`}>{formatDelta(row.heat_score_delta)}</div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {row.top_keywords.slice(0, 5).map((keyword) => <span key={keyword} className="rounded-md border border-line bg-white px-2 py-1 text-xs">{keyword}</span>)}
            </div>
            <p className="mt-3 line-clamp-2 text-xs leading-5 text-slate-600">{row.explanation}</p>
          </div>
        ))}
        {rows.length === 0 ? <div className="rounded-md border border-line bg-slate-50 p-3 text-sm text-slate-600">暂无明显变化。</div> : null}
      </div>
    </div>
  );
}

function IndustryTable({ rows }: { rows: IndustryTimelineRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[980px] text-left text-sm">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-4 py-3">赛道</th>
            <th className="px-4 py-3 text-right">热度分</th>
            <th className="px-4 py-3 text-right">变化</th>
            <th className="px-4 py-3 text-right">1日</th>
            <th className="px-4 py-3 text-right">7日</th>
            <th className="px-4 py-3 text-right">30日</th>
            <th className="px-4 py-3">关键词</th>
            <th className="px-4 py-3">摘要</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.industry_id} className="border-t border-line align-top">
              <td className="px-4 py-3 font-medium"><Link href={`/industry/${row.industry_id}`} className="hover:text-mint">{row.name}</Link></td>
              <td className="mono px-4 py-3 text-right font-semibold">{row.heat_score.toFixed(1)}</td>
              <td className={`mono px-4 py-3 text-right ${deltaClass(row.heat_score_delta)}`}>{formatDelta(row.heat_score_delta)}</td>
              <td className="mono px-4 py-3 text-right">{row.heat_1d.toFixed(1)}</td>
              <td className="mono px-4 py-3 text-right">{row.heat_7d.toFixed(1)}</td>
              <td className="mono px-4 py-3 text-right">{row.heat_30d.toFixed(1)}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1.5">
                  {row.top_keywords.slice(0, 5).map((keyword) => <span key={keyword} className="rounded-md border border-line px-2 py-1 text-xs">{keyword}</span>)}
                </div>
              </td>
              <td className="px-4 py-3 text-slate-600"><div className="line-clamp-2">{row.explanation}</div></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="panel p-4">
      <div className="label">{label}</div>
      <div className="mono mt-2 text-xl font-semibold">{value}</div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-line bg-white px-2 py-1">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{value}</div>
    </div>
  );
}

function formatDelta(value: number | null) {
  if (value === null) return "new";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function deltaClass(value: number | null) {
  if (value === null) return "text-slate-500";
  if (value > 0) return "text-emerald-700";
  if (value < 0) return "text-rose";
  return "text-slate-600";
}
