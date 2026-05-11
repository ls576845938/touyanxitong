"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Filter, Search, TrendingUp, ShieldCheck, Activity, ChevronRight } from "lucide-react";
import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { api, type TrendPoolRow } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { 
    opacity: 1,
    transition: { staggerChildren: 0.05 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 }
};

export default function TrendPage() {
  const [rows, setRows] = useState<TrendPoolRow[]>([]);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [rating, setRating] = useState("全部");
  const [breakoutOnly, setBreakoutOnly] = useState(false);
  const [rsTopOnly, setRsTopOnly] = useState(false);
  const [researchOnly, setResearchOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.trendPool({ market, board: market === "A" ? board : "all", researchUniverseOnly: researchOnly, limit: 180 })
      .then(setRows)
      .catch((err: Error) => setError(`趋势池读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board, researchOnly]);

  const filtered = useMemo(() => {
    return rows.filter((row) => {
      if (rating !== "全部" && row.rating !== rating) return false;
      if (breakoutOnly && !row.is_breakout_250d) return false;
      if (rsTopOnly && row.relative_strength_rank > Math.max(1, Math.ceil(rows.length * 0.1))) return false;
      return true;
    });
  }, [rows, rating, breakoutOnly, rsTopOnly]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载趋势股票池" /></div>;
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
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">INTELLIGENT SCREENING</div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight">趋势增强股票池</h1>
            <p className="mt-2 text-sm font-medium text-slate-500 max-w-2xl">
              结合产业逻辑、公司质量与股价趋势的综合评分系统，实时追踪高确定性成长标的。
            </p>
          </div>
          <div className="flex gap-4">
            <StatCard label="TOTAL" value={rows.length} />
            <StatCard label="FILTERED" value={filtered.length} highlight />
          </div>
        </div>
      </motion.section>

      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <motion.aside variants={itemVariants} className="space-y-6">
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-6 text-slate-900">
              <Filter size={18} className="text-indigo-600" />
              <span className="text-xs font-black uppercase tracking-widest">Market Selection</span>
            </div>
            
            <div className="space-y-4">
               <div className="space-y-1.5">
                  <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">MARKET</div>
                  <div className="flex flex-wrap gap-1.5">
                    {MARKET_OPTIONS.map((option) => (
                      <button
                        key={option}
                        onClick={() => {
                          setMarket(option);
                          if (option !== "A") setBoard("all");
                        }}
                        className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                          market === option ? "bg-slate-900 text-white shadow-md" : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                        }`}
                      >
                        {marketLabel(option)}
                      </button>
                    ))}
                  </div>
               </div>

               {market === "A" && (
                 <div className="space-y-1.5 pt-2">
                    <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">BOARD</div>
                    <div className="flex flex-wrap gap-1.5">
                      {A_BOARD_OPTIONS.map((option) => (
                        <button
                          key={option}
                          onClick={() => setBoard(option)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                            board === option ? "bg-indigo-600 text-white shadow-md shadow-indigo-200" : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                          }`}
                        >
                          {boardLabel(option)}
                        </button>
                      ))}
                    </div>
                 </div>
               )}
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200">
            <div className="flex items-center gap-2 mb-6 text-slate-900">
              <Search size={18} className="text-indigo-600" />
              <span className="text-xs font-black uppercase tracking-widest">Filters</span>
            </div>

            <div className="space-y-6">
              <div className="space-y-2">
                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">Rating Level</label>
                <select 
                  className="w-full bg-slate-50 border border-slate-100 rounded-xl px-4 py-2.5 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 transition-all"
                  value={rating} 
                  onChange={(e) => setRating(e.target.value)}
                >
                  {["全部", "强观察", "观察", "弱观察", "仅记录", "排除"].map((item) => <option key={item}>{item}</option>)}
                </select>
              </div>

              <div className="space-y-3 pt-2">
                <FilterToggle label="250日新高突破" checked={breakoutOnly} onChange={setBreakoutOnly} />
                <FilterToggle label="相对强度前10%" checked={rsTopOnly} onChange={setRsTopOnly} />
                <FilterToggle label="仅研究股票池" checked={researchOnly} onChange={setResearchOnly} />
              </div>
            </div>
          </div>
        </motion.aside>

        <motion.section variants={itemVariants} className="bg-white rounded-3xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-100/50">
                  <th className="pl-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">STOCK / SECTOR</th>
                  <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">RATING</th>
                  <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">SCORE</th>
                  <th className="px-4 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">COMPONENTS</th>
                  <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">TECHNICALS</th>
                  <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">DATA QUALITY</th>
                  <th className="pr-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">ACTION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((row) => (
                  <tr key={row.code} className="hover:bg-indigo-50/30 even:bg-slate-50/50 transition-all group">
                    <td className="pl-8 py-6">
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center font-black text-slate-400 text-xs group-hover:bg-white group-hover:shadow-sm transition-all">
                          {row.name.substring(0, 1)}
                        </div>
                        <div>
                          <div className="font-black text-slate-900 tracking-tight group-hover:text-indigo-600 transition-colors">{row.name}</div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-tight">{row.code}</span>
                            <span className="w-1 h-1 bg-slate-300 rounded-full" />
                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-tight">{row.industry}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-6 text-center">
                       <ScoreBadge score={row.final_score} rating={row.rating} />
                    </td>
                    <td className="py-6 text-right">
                       <div className="text-lg font-black text-slate-900 font-mono tracking-tighter">{row.final_score.toFixed(1)}</div>
                    </td>
                    <td className="px-4 py-6">
                       <div className="flex items-center justify-center gap-3">
                          <MiniScore label="IND" value={row.industry_score} />
                          <MiniScore label="CPY" value={row.company_score} />
                          <MiniScore label="TRD" value={row.trend_score} />
                          <MiniScore label="RISK" value={row.risk_penalty} isNegative />
                       </div>
                    </td>
                    <td className="py-6">
                      <div className="flex flex-wrap gap-1">
                        <StatusFlag active={row.is_ma_bullish} label="多头" />
                        <StatusFlag active={row.is_breakout_120d} label="120D" />
                        <StatusFlag active={row.is_breakout_250d} label="250D" />
                      </div>
                    </td>
                    <td className="py-6">
                       <div className="space-y-1.5">
                          <ConfidenceBar label="DATA" value={row.confidence?.combined_confidence} />
                          <div className="flex gap-2">
                             <StatusDot active={row.fundamental_summary?.status === "complete"} label="FUND" />
                             <StatusDot active={row.news_evidence_status === "active"} label="NEWS" />
                          </div>
                       </div>
                    </td>
                    <td className="pr-8 py-6 text-right">
                      <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/trend`} className="inline-flex items-center gap-1 text-xs font-black uppercase tracking-widest text-slate-400 hover:text-indigo-600 transition-colors">
                        Terminal <ChevronRight size={14} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="py-20 text-center">
                 <div className="text-slate-300 mb-2 font-black uppercase tracking-[0.2em]">No Matches</div>
                 <p className="text-sm text-slate-400 font-medium">调整筛选条件以查看更多数据。</p>
              </div>
            )}
          </div>
        </motion.section>
      </div>
    </motion.div>
  );
}

function StatCard({ label, value, highlight = false }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={`px-6 py-3 rounded-2xl border ${highlight ? 'bg-indigo-600 border-indigo-500 shadow-lg shadow-indigo-100' : 'bg-slate-50 border-slate-100'}`}>
      <div className={`text-[9px] font-black uppercase tracking-widest mb-0.5 ${highlight ? 'text-indigo-200' : 'text-slate-400'}`}>{label}</div>
      <div className={`text-2xl font-black font-mono tracking-tight ${highlight ? 'text-white' : 'text-slate-900'}`}>{value}</div>
    </div>
  );
}

function FilterToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between cursor-pointer group">
       <span className="text-xs font-bold text-slate-500 group-hover:text-slate-900 transition-colors">{label}</span>
       <div 
         onClick={() => onChange(!checked)}
         className={`w-9 h-5 rounded-full relative transition-all ${checked ? 'bg-indigo-600' : 'bg-slate-200'}`}
       >
         <motion.div 
           animate={{ x: checked ? 18 : 2 }}
           className="w-3.5 h-3.5 bg-white rounded-full absolute top-0.5"
         />
       </div>
    </label>
  );
}

function MiniScore({ label, value, isNegative = false }: { label: string; value: number; isNegative?: boolean }) {
  const color = isNegative ? (value > 0 ? "text-rose-500" : "text-slate-300") : (value > 15 ? "text-indigo-600" : "text-slate-600");
  return (
    <div className="text-center">
       <div className="text-[8px] font-black text-slate-400 uppercase tracking-tighter mb-0.5">{label}</div>
       <div className={`text-[10px] font-black font-mono ${color}`}>{value.toFixed(1)}</div>
    </div>
  );
}

function StatusFlag({ active, label }: { active: boolean; label: string }) {
  return (
    <span className={`px-2 py-0.5 rounded-md text-[9px] font-black uppercase tracking-tighter border transition-colors ${
      active ? "bg-indigo-50 text-indigo-700 border-indigo-100" : "bg-white text-slate-300 border-slate-100"
    }`}>
      {label}
    </span>
  );
}

function ConfidenceBar({ label, value }: { label: string; value: number | null | undefined }) {
  const pct = Math.round((value ?? 0) * 100);
  return (
    <div className="flex items-center gap-2">
       <div className="text-[8px] font-black text-slate-400 uppercase w-7">{label}</div>
       <div className="flex-1 h-1 bg-slate-100 rounded-full overflow-hidden w-16">
          <div className="h-full bg-slate-900 rounded-full" style={{ width: `${pct}%` }} />
       </div>
       <div className="text-[9px] font-black font-mono text-slate-500">{pct}%</div>
    </div>
  );
}

function StatusDot({ active, label }: { active: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1">
       <div className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-emerald-500 shadow-sm shadow-emerald-200' : 'bg-slate-200'}`} />
       <span className="text-[8px] font-black text-slate-400 uppercase tracking-widest">{label}</span>
    </div>
  );
}
