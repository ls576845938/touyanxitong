"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileText, Calendar, ShieldCheck, Activity, BarChart3, ChevronRight, AlertTriangle, Database } from "lucide-react";
import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type DailyReport, type ReportSummary } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

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

export default function ReportPage() {
  const [report, setReport] = useState<DailyReport | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.latestReport(), api.reports()])
      .then(([latest, reportRows]) => {
        setReport(latest);
        setReports(reportRows);
      })
      .catch((err: Error) => setError(`日报读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载每日简报" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!report) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="日报为空" /></div>;

  return (
    <motion.div 
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="min-h-screen bg-slate-50 px-6 py-8 space-y-6"
    >
      <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-6 mb-8">
           <div>
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">DAILY INTELLIGENCE BRIEF</div>
              <h1 className="text-3xl font-black text-slate-900 tracking-tight">{report.title}</h1>
              <p className="mt-2 text-sm font-medium text-slate-500 max-w-3xl leading-relaxed">
                {report.market_summary}
              </p>
           </div>
           <div className="flex bg-slate-100 rounded-2xl p-1.5 items-center gap-2 pr-4">
              <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center shadow-sm">
                 <Calendar size={20} className="text-indigo-600" />
              </div>
              <span className="text-sm font-black font-mono text-slate-900">{report.report_date}</span>
           </div>
        </div>

        <div className="border-t border-slate-50 pt-6">
           <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-4">ARCHIVE NAVIGATION</div>
           <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
              {reports.map((item) => (
                <button
                  key={item.report_date}
                  onClick={() => api.reportByDate(item.report_date).then(setReport)}
                  className={`h-10 shrink-0 px-5 rounded-xl text-xs font-bold transition-all border ${
                    report.report_date === item.report_date 
                      ? "bg-slate-900 border-slate-900 text-white shadow-lg shadow-slate-200" 
                      : "bg-white border-slate-100 text-slate-500 hover:border-indigo-200 hover:text-indigo-600"
                  }`}
                >
                  {item.report_date}
                </button>
              ))}
           </div>
        </div>
      </motion.section>

      <motion.section variants={itemVariants} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatusCard 
          icon={<Database className="text-indigo-600" size={18} />}
          label="数据质量状态" 
          value={report.data_quality.status} 
          detail={`F:${report.data_quality.summary.fail_count} / W:${report.data_quality.summary.warn_count}`} 
        />
        <StatusCard 
          icon={<Activity className="text-emerald-600" size={18} />}
          label="研究池准入" 
          value={`${report.research_universe.summary.eligible_count} / ${report.research_universe.summary.stock_count}`} 
          detail={`ELIGIBILITY RATIO ${Math.round(report.research_universe.summary.eligible_ratio * 100)}%`} 
        />
        <StatusCard 
          icon={<ShieldCheck className="text-blue-600" size={18} />}
          label="平均评分可信度" 
          value={averageConfidence(report.top_trend_stocks)} 
          detail={`VALIDATED ${report.top_trend_stocks.filter((row) => row.research_gate?.passed).length} / ${report.top_trend_stocks.length} STOCKS`} 
        />
      </motion.section>

      <div className="grid gap-6 lg:grid-cols-2">
        <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
               <div className="w-8 h-8 rounded-lg bg-indigo-50 flex items-center justify-center text-indigo-600">
                  <BarChart3 size={18} />
               </div>
               观察池核心动态
            </h2>
            <Link href="/watchlist" className="text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-indigo-600 transition-colors">View All</Link>
          </div>
          <div className="space-y-3">
            {report.watchlist_changes.new_entries.slice(0, 5).map((item) => (
              <Link key={`new-${item.code}`} href={`/stocks/${encodeURIComponent(item.code)}?from=/report`} className="flex items-center justify-between p-4 rounded-2xl bg-slate-50 border border-transparent hover:border-indigo-100 hover:bg-white transition-all group">
                <div className="flex items-center gap-4">
                   <div className="w-10 h-10 rounded-xl bg-white border border-slate-100 flex items-center justify-center font-black text-slate-400 group-hover:text-indigo-600 transition-colors">
                     {item.name.substring(0, 1)}
                   </div>
                   <div>
                      <div className="text-sm font-black text-slate-900">{item.name}</div>
                      <div className="text-[10px] font-mono font-bold text-slate-400 uppercase">{item.code} / {marketLabel(item.market)}</div>
                   </div>
                </div>
                <div className="text-right">
                   <div className="text-sm font-black text-emerald-600 font-mono">{item.final_score?.toFixed(1) ?? "-"}</div>
                   <div className="text-[9px] font-black uppercase tracking-tighter text-slate-400">{item.rating ?? "NO RATING"}</div>
                </div>
              </Link>
            ))}
            {report.watchlist_changes.new_entries.length === 0 && (
              <div className="py-10 text-center text-slate-300 font-black uppercase tracking-widest text-[10px]">No new entries today</div>
            )}
          </div>
        </motion.section>

        <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-3">
               <div className="w-8 h-8 rounded-lg bg-slate-900 flex items-center justify-center text-white">
                  <ShieldCheck size={18} />
               </div>
               各板块研究准入率
            </h2>
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">MARKET SEGMENTATION</div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {report.research_universe.segments.slice(0, 6).map((segment) => (
              <div key={`${segment.market}-${segment.board}`} className="p-4 rounded-2xl bg-slate-50 border border-slate-100">
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">{marketLabel(segment.market)} / {boardLabel(segment.board)}</div>
                <div className="flex items-baseline gap-2">
                   <span className="text-lg font-black text-slate-900">{segment.eligible_count}</span>
                   <span className="text-xs font-bold text-slate-400">/ {segment.stock_count}</span>
                </div>
                <div className="mt-3 h-1 w-full bg-slate-200 rounded-full overflow-hidden">
                   <div className="h-full bg-slate-900" style={{ width: `${segment.eligible_ratio * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </motion.section>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
          <h2 className="text-xl font-black text-slate-900 tracking-tight mb-8">今日观察池候选</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {report.new_watchlist_stocks.slice(0, 10).map((item) => (
              <Link key={item.code} href={`/stocks/${encodeURIComponent(item.code)}?from=/report`} className="flex flex-col p-5 rounded-2xl border border-slate-100 bg-slate-50/50 hover:bg-white hover:border-indigo-100 hover:shadow-sm transition-all group">
                <div className="flex justify-between items-start mb-4">
                   <div>
                      <div className="text-sm font-black text-slate-900 group-hover:text-indigo-600 transition-colors">{item.name}</div>
                      <div className="text-[10px] font-mono font-bold text-slate-400">{item.code}</div>
                   </div>
                   <div className="text-right">
                      <div className="text-sm font-black text-indigo-600 font-mono">{Number(item.final_score).toFixed(1)}</div>
                   </div>
                </div>
                <div className="mt-auto pt-4 border-t border-slate-100 flex items-center justify-between">
                   <span className="text-[9px] font-black text-slate-500 uppercase tracking-tighter">{item.industry}</span>
                   <div className="flex items-center gap-1">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <span className="text-[9px] font-black text-slate-400 uppercase">{formatPct(item.confidence?.combined_confidence)}</span>
                   </div>
                </div>
              </Link>
            ))}
          </div>
        </motion.section>

        <motion.div variants={itemVariants} className="space-y-6">
          <section className="bg-rose-50 rounded-3xl p-8 border border-rose-100">
            <div className="flex items-center gap-3 text-rose-600 mb-6">
               <AlertTriangle size={24} />
               <h2 className="text-lg font-black uppercase tracking-tight">风险预警清单</h2>
            </div>
            <div className="space-y-3">
              {report.risk_alerts.length ? report.risk_alerts.map((alert, i) => (
                <div key={i} className="p-4 bg-white/60 border border-rose-50 rounded-2xl text-xs font-bold leading-relaxed text-rose-900">
                  {alert}
                </div>
              )) : (
                <div className="py-6 text-center text-rose-300 font-black uppercase tracking-widest text-[10px]">No high-risk alerts</div>
              )}
            </div>
          </section>

          <section className="bg-slate-900 rounded-3xl p-8 shadow-2xl border border-slate-800 text-slate-300 overflow-hidden relative">
            <div className="absolute top-0 right-0 p-4 opacity-10">
               <FileText size={120} />
            </div>
            <div className="relative z-10">
              <h2 className="text-white text-lg font-black uppercase tracking-widest mb-6">简报原文</h2>
              <div className="text-xs leading-relaxed font-mono opacity-80 whitespace-pre-wrap max-h-[500px] overflow-y-auto pr-4 scrollbar-hide">
                {report.full_markdown}
              </div>
            </div>
          </section>
        </motion.div>
      </div>
    </motion.div>
  );
}

function StatusCard({ label, value, detail, icon }: { label: string; value: string; detail: string; icon: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 group hover:border-indigo-100 transition-all">
      <div className="flex items-center gap-2 mb-4">
        <div className="p-1.5 bg-slate-50 rounded-lg group-hover:bg-indigo-50 transition-colors">{icon}</div>
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</span>
      </div>
      <div className="text-2xl font-black text-slate-900 font-mono tracking-tighter mb-2">{value}</div>
      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest opacity-60">{detail}</div>
    </div>
  );
}

function averageConfidence(rows: DailyReport["top_trend_stocks"]) {
  const values = rows
    .map((row) => row.confidence?.combined_confidence)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!values.length) return "-";
  return `${Math.round((values.reduce((sum, value) => sum + value, 0) / values.length) * 100)}%`;
}

function formatPct(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "-";
}
