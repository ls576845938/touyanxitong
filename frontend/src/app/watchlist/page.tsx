"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, CalendarDays, Repeat2, TrendingUp, Filter, ChevronRight, Activity, Clock } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { api, type WatchlistChangeRow, type WatchlistTimeline, type WatchlistTimelineItem, type WatchlistTopRow } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { 
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 }
};

export default function WatchlistPage() {
  const [timeline, setTimeline] = useState<WatchlistTimeline | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.watchlistTimeline({ market, board: market === "A" ? board : "all", limit: 30 })
      .then((payload) => {
        setTimeline(payload);
        setSelectedDate(payload.latest?.trade_date ?? null);
      })
      .catch((err: Error) => setError(`观察池复盘读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board]);

  const selected = useMemo(() => {
    if (!timeline?.timeline.length) return null;
    return timeline.timeline.find((item) => item.trade_date === selectedDate) ?? timeline.timeline[0];
  }, [timeline, selectedDate]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载观察池复盘" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  return (
    <motion.div 
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="min-h-screen bg-slate-50 px-6 py-8 space-y-6"
    >
      <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">WATCHLIST INTELLIGENCE</div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight">观察池复盘工作台</h1>
            <p className="mt-2 text-sm font-medium text-slate-500 max-w-2xl">
              按交易日追踪观察池的变动逻辑，聚焦高分跃迁与评级上调的核心标的。
            </p>
          </div>
          <div className="flex bg-slate-100 rounded-2xl p-1">
            {MARKET_OPTIONS.map((option) => (
              <button
                key={option}
                onClick={() => {
                  setMarket(option);
                  if (option !== "A") setBoard("all");
                }}
                className={`px-5 py-2 rounded-xl text-xs font-black uppercase transition-all ${
                  market === option ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {marketLabel(option)}
              </button>
            ))}
          </div>
        </div>

        {market === "A" && (
          <div className="mt-4 flex flex-wrap gap-1.5 border-t border-slate-50 pt-4">
            {A_BOARD_OPTIONS.map((option) => (
              <button
                key={option}
                onClick={() => setBoard(option)}
                className={`px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-tighter transition-all ${
                  board === option ? "bg-indigo-50 text-indigo-700 border border-indigo-100 shadow-sm shadow-indigo-50" : "text-slate-400 hover:bg-slate-50"
                }`}
              >
                {boardLabel(option)}
              </button>
            ))}
          </div>
        )}
      </motion.section>

      {selected ? (
        <>
          <motion.section variants={itemVariants} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <MetricCard label="复盘日期" value={selected.trade_date} icon={<CalendarDays className="text-indigo-600" size={16} />} />
            <MetricCard label="当前观察" value={selected.summary.latest_watch_count} icon={<Activity className="text-slate-600" size={16} />} />
            <MetricCard label="新进标的" value={selected.summary.new_count} icon={<ArrowUpRight className="text-emerald-600" size={16} />} />
            <MetricCard label="移出标的" value={selected.summary.removed_count} icon={<ArrowDownRight className="text-rose-600" size={16} />} />
            <MetricCard label="评分变动" value={selected.summary.upgraded_count + selected.summary.downgraded_count} icon={<Repeat2 className="text-amber-600" size={16} />} />
          </motion.section>

          <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
            <motion.aside variants={itemVariants} className="bg-white rounded-3xl p-6 shadow-sm border border-slate-200 h-fit">
              <div className="flex items-center gap-2 mb-6 text-slate-900">
                <Clock size={18} className="text-indigo-600" />
                <span className="text-xs font-black uppercase tracking-widest">Snapshot History</span>
              </div>
              <div className="space-y-2 max-h-[600px] overflow-y-auto pr-2 scrollbar-hide">
                {(timeline?.timeline ?? []).map((item) => (
                  <button
                    key={item.trade_date}
                    onClick={() => setSelectedDate(item.trade_date)}
                    className={`w-full text-left p-4 rounded-2xl border transition-all group ${
                      selected.trade_date === item.trade_date 
                        ? "bg-slate-900 border-slate-900 shadow-lg shadow-slate-200" 
                        : "bg-white border-slate-100 hover:border-indigo-200 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className={`text-sm font-black font-mono ${selected.trade_date === item.trade_date ? "text-white" : "text-slate-900"}`}>
                        {item.trade_date}
                      </div>
                      <div className={`text-[9px] font-black uppercase tracking-tighter ${selected.trade_date === item.trade_date ? "text-indigo-400" : "text-slate-400"}`}>
                        {item.summary.latest_watch_count} WATCHING
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                       <MiniSnapshotStat label="NEW" value={item.summary.new_count} active={selected.trade_date === item.trade_date} />
                       <MiniSnapshotStat label="GAIN" value={item.summary.score_gainer_count} active={selected.trade_date === item.trade_date} />
                    </div>
                  </button>
                ))}
              </div>
            </motion.aside>

            <motion.div variants={itemVariants} className="space-y-6">
              <section className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
                <div className="flex flex-wrap items-start justify-between gap-6 mb-8 border-b border-slate-50 pb-6">
                  <div>
                    <h2 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
                       当日动态变化 <span className="text-xs font-bold text-slate-400 font-mono ml-2">{selected.previous_date} → {selected.trade_date}</span>
                    </h2>
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-1">DAILY WATCHLIST DYNAMICS</div>
                  </div>
                  <div className="flex gap-4">
                     <SummaryPill label="BULLISH" value={selected.summary.score_gainer_count} color="emerald" />
                     <SummaryPill label="BEARISH" value={selected.summary.score_loser_count} color="rose" />
                  </div>
                </div>

                <div className="grid gap-6 md:grid-cols-2">
                  <ChangeGroup title="新进观察" rows={selected.new_entries} color="indigo" />
                  <ChangeGroup title="评级上调" rows={selected.upgraded} color="emerald" />
                  <ChangeGroup title="评分大幅上升" rows={selected.score_gainers} color="indigo" showDelta />
                  <ChangeGroup title="移出或降级" rows={[...selected.removed_entries, ...selected.downgraded]} color="rose" showDelta />
                </div>
              </section>

              <section className="bg-white rounded-3xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="p-8 border-b border-slate-100 flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-black text-slate-900 tracking-tight">当前观察池 TOP 标的</h2>
                    <p className="mt-1 text-xs font-medium text-slate-500 uppercase tracking-widest">RANKED BY FINAL SCORE TERMINAL</p>
                  </div>
                  <TrendingUp className="text-indigo-600" size={24} />
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-slate-100/50 border-b border-slate-200">
                        <th className="pl-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">STOCK / MARKET</th>
                        <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">SECTOR</th>
                        <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">RATING</th>
                        <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">SCORE</th>
                        <th className="px-6 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">FUND / TREND / RISK</th>
                        <th className="pr-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">ACTION</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {selected.watchlist_top.map((row) => (
                        <tr key={row.code} className="hover:bg-indigo-50/30 even:bg-slate-50/50 transition-all group">
                          <td className="pl-8 py-5">
                            <div>
                              <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/watchlist`} className="font-black text-slate-900 hover:text-indigo-600 transition-colors tracking-tight">
                                {row.name}
                              </Link>
                              <div className="flex items-center gap-1.5 mt-0.5">
                                <span className="text-[10px] font-mono font-bold text-slate-400">{row.code}</span>
                                <span className="w-1 h-1 bg-slate-200 rounded-full" />
                                <span className="text-[10px] font-bold text-slate-500 uppercase">{marketLabel(row.market)}</span>
                              </div>
                            </div>
                          </td>
                          <td className="py-5">
                            <span className="text-[11px] font-bold text-slate-600">{row.industry}</span>
                          </td>
                          <td className="py-5 text-center">
                             <ScoreBadge score={row.final_score} rating={row.rating} />
                          </td>
                          <td className="py-5 text-right font-mono text-sm font-black text-slate-900">
                             {row.final_score.toFixed(1)}
                          </td>
                          <td className="px-6 py-5">
                            <div className="flex items-center justify-center gap-4">
                               <MiniValue label="CPY" value={row.company_score} />
                               <MiniValue label="TRD" value={row.trend_score} />
                               <MiniValue label="RISK" value={row.risk_penalty} isNegative />
                            </div>
                          </td>
                          <td className="pr-8 py-5 text-right">
                             <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/watchlist`} className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-indigo-600 transition-colors">
                               Terminal <ChevronRight size={12} />
                             </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </motion.div>
          </div>
        </>
      ) : (
        <motion.section variants={itemVariants} className="bg-white rounded-3xl p-12 text-center shadow-sm border border-slate-200">
           <div className="text-slate-300 font-black uppercase tracking-[0.2em] mb-2">No Review Data</div>
           <p className="text-sm text-slate-500 font-medium">当前筛选条件下暂无复盘记录，请选择其他市场。</p>
        </motion.section>
      )}
    </motion.div>
  );
}

function MetricCard({ label, value, icon }: { label: string; value: string | number; icon: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 group hover:border-indigo-100 transition-all">
      <div className="flex items-center gap-2 mb-3">
        <div className="p-1.5 bg-slate-50 rounded-lg group-hover:bg-indigo-50 transition-colors">{icon}</div>
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</span>
      </div>
      <div className="text-xl font-black text-slate-900 font-mono tracking-tighter">{value}</div>
    </div>
  );
}

function MiniSnapshotStat({ label, value, active }: { label: string; value: number; active: boolean }) {
  return (
    <div className={`p-1.5 rounded-lg border text-center ${active ? "bg-slate-800 border-slate-700" : "bg-slate-50 border-slate-100"}`}>
       <div className={`text-[8px] font-black uppercase tracking-tighter mb-0.5 ${active ? "text-slate-500" : "text-slate-400"}`}>{label}</div>
       <div className={`text-[10px] font-black font-mono ${active ? "text-white" : "text-slate-700"}`}>{value}</div>
    </div>
  );
}

function SummaryPill({ label, value, color }: { label: string; value: number; color: "emerald" | "rose" }) {
  const colors = {
    emerald: "bg-emerald-50 text-emerald-600 border-emerald-100",
    rose: "bg-rose-50 text-rose-600 border-rose-100"
  };
  return (
    <div className={`px-4 py-2 rounded-xl border flex items-center gap-3 ${colors[color]}`}>
       <span className="text-[10px] font-black uppercase tracking-widest">{label}</span>
       <span className="text-lg font-black font-mono">{value}</span>
    </div>
  );
}

function ChangeGroup({ title, rows, color, showDelta = false }: { title: string; rows: WatchlistChangeRow[]; color: "indigo" | "emerald" | "rose"; showDelta?: boolean }) {
  const colorClasses = {
    indigo: "text-indigo-600 bg-indigo-50",
    emerald: "text-emerald-600 bg-emerald-50",
    rose: "text-rose-600 bg-rose-50"
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
         <div className={`w-1 h-4 rounded-full ${color === 'indigo' ? 'bg-indigo-600' : color === 'emerald' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
         <h3 className="text-xs font-black uppercase tracking-widest text-slate-900">{title}</h3>
         <span className="text-[10px] font-bold text-slate-400 font-mono">{rows.length} ITEMS</span>
      </div>
      <div className="space-y-2">
        {rows.slice(0, 5).map((row, i) => (
          <Link key={i} href={`/stocks/${encodeURIComponent(row.code)}?from=/watchlist`} className="block bg-slate-50 hover:bg-white border border-transparent hover:border-slate-100 hover:shadow-sm p-4 rounded-2xl transition-all group">
            <div className="flex justify-between items-start mb-2">
               <div>
                  <div className="text-sm font-black text-slate-900 group-hover:text-indigo-600 transition-colors">{row.name}</div>
                  <div className="text-[10px] font-mono font-bold text-slate-400">{row.code}</div>
               </div>
               <div className="text-right">
                  <div className="text-xs font-black font-mono text-slate-900">{formatScore(row.final_score ?? row.previous_score)}</div>
                  {showDelta && <div className={`text-[10px] font-black ${row.score_delta && row.score_delta > 0 ? "text-emerald-500" : "text-rose-500"}`}>{formatDelta(row.score_delta)}</div>}
               </div>
            </div>
            <div className="flex items-center gap-2">
               <span className="text-[9px] font-black uppercase tracking-tighter text-slate-400 px-1.5 py-0.5 bg-white border border-slate-100 rounded-md">
                 {row.previous_rating ?? "-"} → {row.rating ?? "-"}
               </span>
            </div>
          </Link>
        ))}
        {rows.length === 0 && <div className="text-[10px] font-bold text-slate-300 uppercase tracking-widest text-center py-4">No changes detected</div>}
      </div>
    </div>
  );
}

function MiniValue({ label, value, isNegative = false }: { label: string; value: number; isNegative?: boolean }) {
  const color = isNegative ? (value > 0 ? "text-rose-500" : "text-slate-300") : "text-slate-600";
  return (
    <div className="text-center">
       <div className="text-[8px] font-black text-slate-400 uppercase tracking-tighter mb-0.5">{label}</div>
       <div className={`text-[10px] font-black font-mono ${color}`}>{value.toFixed(1)}</div>
    </div>
  );
}

function formatScore(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : value.toFixed(1);
}

function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return "NEW";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}
