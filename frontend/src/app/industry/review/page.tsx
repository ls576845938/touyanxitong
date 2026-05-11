"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowDownRight, ArrowUpRight, CalendarDays, Flame, BarChart3, TrendingUp, TrendingDown, History } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { IndustryTimelineChart } from "@/components/IndustryTimelineChart";
import { LoadingState } from "@/components/LoadingState";
import { api, type IndustryTimeline, type IndustryTimelineItem, type IndustryTimelineRow } from "@/lib/api";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

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

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载赛道复盘" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  return (
    <motion.div 
      className="min-h-screen bg-slate-50 p-6 lg:p-10 space-y-8"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <motion.section variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-10 shadow-sm relative overflow-hidden">
        <div className="absolute top-0 right-0 p-12 opacity-[0.03] pointer-events-none">
          <History size={200} />
        </div>
        <div className="relative z-10 max-w-3xl">
          <div className="flex items-center gap-2 mb-4">
            <div className="bg-slate-900 p-2 rounded-xl text-white">
              <BarChart3 size={20} />
            </div>
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Industry Cycle Analysis</span>
          </div>
          <h1 className="text-4xl font-black text-slate-900 tracking-tight">赛道热度变化复盘</h1>
          <p className="mt-4 text-base leading-relaxed text-slate-500 font-medium">
            跟踪产业热度的持续性、扩散度和降温风险。
            <span className="block mt-1 text-slate-400 text-sm italic">热度趋势是市场情绪的镜像，辅助判断观察池背后的赛道逻辑强度。</span>
          </p>
        </div>
      </motion.section>

      {selected ? (
        <div className="space-y-8">
          <motion.section variants={itemVariants} className="grid gap-4 md:grid-cols-5">
            <Metric label="复盘日期" value={selected.trade_date} icon={<CalendarDays size={14}/>} />
            <Metric label="赛道数量" value={selected.summary.industry_count} />
            <Metric label="热赛道" value={selected.summary.hot_industry_count} highlight />
            <Metric label="升温赛道" value={selected.summary.rising_count} />
            <Metric label="降温赛道" value={selected.summary.cooling_count} />
          </motion.section>

          <div className="grid gap-8 lg:grid-cols-[0.3fr_0.7fr]">
            <motion.div variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-6 shadow-sm">
              <div className="mb-6 flex items-center gap-2 px-2">
                <History size={16} className="text-indigo-600" />
                <h2 className="text-[11px] font-black text-slate-400 uppercase tracking-widest">Historical Snapshots</h2>
              </div>
              <div className="space-y-2 max-h-[800px] overflow-y-auto pr-2 custom-scrollbar">
                {(timeline?.timeline ?? []).map((item) => (
                  <TimelineButton 
                    key={item.trade_date} 
                    item={item} 
                    active={item.trade_date === selected.trade_date} 
                    onClick={() => setSelectedDate(item.trade_date)} 
                  />
                ))}
              </div>
            </motion.div>

            <div className="space-y-8">
              <motion.section variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-8 shadow-sm">
                <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2 text-xl font-black text-slate-900">
                      <Flame size={20} className="text-orange-500" />
                      全市场热度总览
                    </div>
                    <p className="mt-1 text-sm text-slate-500 font-medium tracking-tight">Aggregated Market Heat & Momentum Distribution</p>
                  </div>
                  <div className="flex gap-4">
                    <MiniStat label="总热度" value={selected.summary.total_heat_score.toFixed(1)} />
                    <MiniStat label="平均热度" value={selected.summary.average_heat_score.toFixed(1)} />
                  </div>
                </div>
                <div className="h-[360px]">
                  <IndustryTimelineChart rows={timeline?.timeline ?? []} />
                </div>
              </motion.section>

              <div className="grid gap-8 lg:grid-cols-2">
                <IndustryList title="核心升温赛道" icon="up" rows={selected.rising_industries} />
                <IndustryList title="显著降温赛道" icon="down" rows={selected.cooling_industries} />
              </div>

              <motion.section variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] overflow-hidden shadow-sm">
                <div className="border-b border-slate-100 p-8">
                  <h2 className="text-2xl font-black text-slate-900">当日赛道热度全景</h2>
                  <p className="mt-1 text-sm text-slate-500 font-medium">Daily Industry Heatmap & Alpha Signals</p>
                </div>
                <IndustryTable rows={selected.industries} />
              </motion.section>
            </div>
          </div>
        </div>
      ) : (
        <motion.section variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-10 text-center shadow-sm">
          <p className="text-slate-400 font-bold italic">当前没有产业热度复盘记录。</p>
        </motion.section>
      )}
    </motion.div>
  );
}

function TimelineButton({ item, active, onClick }: { item: IndustryTimelineItem; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-2xl border p-4 text-left transition-all group ${
        active 
        ? "border-indigo-600 bg-indigo-50 shadow-md shadow-indigo-100" 
        : "border-slate-100 bg-white hover:border-indigo-300 hover:shadow-sm"
      }`}
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className={`text-sm font-black italic tabular-nums ${active ? 'text-indigo-700' : 'text-slate-900'}`}>
          {item.trade_date}
        </div>
        <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest">
          {item.previous_date ? "Comparison" : "Initial"}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col">
          <span className="text-[9px] font-black text-slate-400 uppercase tracking-tighter">Heat</span>
          <span className="text-xs font-black text-slate-700">{item.summary.total_heat_score.toFixed(0)}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-[9px] font-black text-slate-400 uppercase tracking-tighter">Hot</span>
          <span className="text-xs font-black text-slate-700">{item.summary.hot_industry_count}</span>
        </div>
      </div>
    </button>
  );
}

function IndustryList({ title, rows, icon }: { title: string; rows: IndustryTimelineRow[]; icon: "up" | "down" }) {
  const Icon = icon === "up" ? TrendingUp : TrendingDown;
  const accentColor = icon === "up" ? "text-emerald-500" : "text-rose-500";
  const bgColor = icon === "up" ? "bg-emerald-50/50" : "bg-rose-50/50";
  
  return (
    <motion.div variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-8 shadow-sm">
      <div className="mb-6 flex items-center gap-3">
        <div className={`p-2 rounded-xl ${icon === 'up' ? 'bg-emerald-500' : 'bg-rose-500'} text-white`}>
          <Icon size={18} />
        </div>
        <h3 className="text-xl font-black text-slate-900">{title}</h3>
      </div>
      <div className="space-y-4">
        {rows.slice(0, 6).map((row) => (
          <div key={`${title}-${row.industry_id}`} className={`group relative rounded-3xl border border-slate-100 ${bgColor} p-5 hover:bg-white hover:shadow-lg hover:shadow-slate-200/40 transition-all duration-300`}>
            <div className="flex items-center justify-between gap-3 mb-3">
              <Link href={`/industry/${row.industry_id}`} className="text-base font-black text-slate-900 group-hover:text-indigo-600 transition-colors">
                {row.name}
              </Link>
              <div className={`tabular-nums text-sm font-black italic ${accentColor}`}>
                {formatDelta(row.heat_score_delta)}
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5 mb-4">
              {row.top_keywords.slice(0, 3).map((keyword) => (
                <span key={keyword} className="rounded-lg bg-white border border-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-500 shadow-sm">
                  {keyword}
                </span>
              ))}
            </div>
            <p className="line-clamp-2 text-xs leading-relaxed text-slate-500 font-medium italic">
              {row.explanation}
            </p>
          </div>
        ))}
        {rows.length === 0 ? <div className="rounded-3xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400 font-medium italic">暂无明显趋势变化。</div> : null}
      </div>
    </motion.div>
  );
}

function IndustryTable({ rows }: { rows: IndustryTimelineRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[980px] text-left text-sm">
        <thead>
          <tr className="bg-slate-50 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
            <th className="px-8 py-5">Industry Sector</th>
            <th className="px-4 py-5 text-right">Heat Score</th>
            <th className="px-4 py-5 text-right">Delta</th>
            <th className="px-4 py-5 text-right">1D Impact</th>
            <th className="px-4 py-5 text-right">7D Mom.</th>
            <th className="px-4 py-5 text-right">30D Vol.</th>
            <th className="px-4 py-5">Contextual Keywords</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {rows.map((row) => (
            <tr key={row.industry_id} className="hover:bg-slate-50/50 transition-colors group">
              <td className="px-8 py-5">
                <Link href={`/industry/${row.industry_id}`} className="text-base font-black text-slate-900 group-hover:text-indigo-600 transition-colors">
                  {row.name}
                </Link>
                <div className="text-[10px] font-bold text-slate-400 mt-1 line-clamp-1 italic max-w-xs">{row.explanation}</div>
              </td>
              <td className="px-4 py-5 text-right">
                <span className={`inline-block tabular-nums text-sm font-black px-3 py-1 rounded-xl shadow-sm ${heatClass(row.heat_score)}`}>
                  {row.heat_score.toFixed(1)}
                </span>
              </td>
              <td className={`px-4 py-5 text-right tabular-nums text-sm font-black italic ${deltaClass(row.heat_score_delta)}`}>
                {formatDelta(row.heat_score_delta)}
              </td>
              <td className="px-4 py-5 text-right tabular-nums text-sm font-bold text-slate-600">{row.heat_1d.toFixed(1)}</td>
              <td className="px-4 py-5 text-right tabular-nums text-sm font-bold text-slate-600">{row.heat_7d.toFixed(1)}</td>
              <td className="px-4 py-5 text-right tabular-nums text-sm font-bold text-slate-600">{row.heat_30d.toFixed(1)}</td>
              <td className="px-4 py-5">
                <div className="flex flex-wrap gap-1.5">
                  {row.top_keywords.slice(0, 4).map((keyword) => (
                    <span key={keyword} className="rounded-lg bg-white border border-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-400 shadow-sm">
                      {keyword}
                    </span>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metric({ label, value, highlight, icon }: { label: string; value: string | number; highlight?: boolean; icon?: React.ReactNode }) {
  return (
    <div className="bg-white border border-slate-200 rounded-[2rem] p-6 shadow-sm group hover:border-indigo-200 transition-colors">
      <div className="flex items-center gap-1.5 mb-2">
        {icon && <span className="text-slate-400">{icon}</span>}
        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{label}</div>
      </div>
      <div className={`text-2xl font-black italic tabular-nums ${highlight ? 'text-indigo-600' : 'text-slate-900'}`}>
        {value}
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-slate-50 border border-slate-100 rounded-2xl px-4 py-2 text-right">
      <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter mb-0.5">{label}</div>
      <div className="text-sm font-black text-slate-900 tabular-nums">{value}</div>
    </div>
  );
}

function formatDelta(value: number | null) {
  if (value === null) return "NEW";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function deltaClass(value: number | null) {
  if (value === null) return "text-slate-400";
  if (value > 0) return "text-emerald-500";
  if (value < 0) return "text-rose-500";
  return "text-slate-400";
}

function heatClass(score: number) {
  if (score >= 80) return "bg-red-500 text-white";
  if (score >= 50) return "bg-orange-500 text-white";
  if (score >= 25) return "bg-amber-500 text-white";
  return "bg-slate-100 text-slate-500";
}
