"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { IndustryHeatChart } from "@/components/IndustryHeatChart";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type IndustryRadarRow } from "@/lib/api";
import { MARKET_OPTIONS, marketLabel } from "@/lib/markets";
import { Zap, Activity, Compass, TrendingUp } from "lucide-react";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export default function IndustryPage() {
  const [rows, setRows] = useState<IndustryRadarRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [market, setMarket] = useState("ALL");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.industryRadar({ market })
      .then(setRows)
      .catch((err: Error) => setError(`产业雷达读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载产业雷达" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  return (
    <motion.div 
      className="min-h-screen bg-slate-50 p-6 lg:p-10 space-y-8"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <motion.section 
        variants={itemVariants}
        className="bg-white border border-slate-200 rounded-[2rem] p-8 shadow-sm"
      >
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2 mb-4">
              <div className="bg-indigo-600 p-2 rounded-xl text-white">
                <Compass size={20} />
              </div>
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Industry Radar System</span>
            </div>
            <h1 className="text-4xl font-black text-slate-900 tracking-tight">产业热度雷达</h1>
            <p className="mt-4 text-base leading-relaxed text-slate-500 font-medium">
              综合热度多维评估：综合资讯热度、行情覆盖、关联股票和观察池数量。
              <span className="block mt-1 text-slate-400 text-sm italic">数据仅供研究参考，不作为投资决策依据。</span>
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link href="/industry/chain" className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-6 py-3 text-sm font-bold text-slate-700 shadow-sm hover:border-indigo-600 hover:text-indigo-600 transition-all">
              查看产业链地图
            </Link>
            <Link href="/industry/review" className="flex items-center gap-2 rounded-2xl bg-slate-900 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-slate-200 hover:bg-slate-800 transition-all">
              查看赛道复盘
            </Link>
          </div>
        </div>
        
        <div className="mt-10 pt-8 border-t border-slate-100 flex flex-wrap items-center gap-3">
          <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest mr-2">Market Filter</span>
          {MARKET_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMarket(option)}
              className={`rounded-xl px-5 py-2.5 text-xs font-bold transition-all ${
                market === option 
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-200" 
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
              }`}
            >
              {marketLabel(option)}
            </button>
          ))}
        </div>
      </motion.section>

      <motion.section 
        variants={itemVariants}
        className="bg-white border border-slate-200 rounded-[2rem] p-8 shadow-sm"
      >
        <div className="flex items-center gap-2 mb-6">
          <Activity size={18} className="text-indigo-600" />
          <h2 className="text-sm font-black text-slate-900 uppercase tracking-widest">Heat Distribution</h2>
        </div>
        <IndustryHeatChart rows={rows} />
      </motion.section>

      <motion.section 
        variants={itemVariants}
        className="grid gap-6 md:grid-cols-2 xl:grid-cols-3"
      >
        {rows.map((row) => (
          <article 
            key={row.industry_id} 
            className="bg-white border border-slate-200 rounded-[2rem] p-7 shadow-sm hover:shadow-xl hover:shadow-slate-200/50 transition-all duration-500 group"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <Link 
                  href={`/industry/${row.industry_id}${market === "ALL" ? "" : `?market=${market}`}`} 
                  className="text-xl font-black text-slate-900 group-hover:text-indigo-600 transition-colors block mb-1"
                >
                  {row.name}
                </Link>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest bg-slate-50 px-2 py-0.5 rounded-md border border-slate-100">
                    {row.market_label}
                  </span>
                  <span className="text-[10px] font-medium text-slate-400">
                    {row.trade_date ?? "-"}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">Score</div>
                <div className={`tabular-nums rounded-xl px-3 py-1.5 text-sm font-black shadow-sm ${heatScoreClass(row)}`}>
                  {formatNumber(row.heat_score)}
                </div>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-2">
              <span className={`rounded-lg px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${evidenceStatusClass(row)}`}>
                {evidenceStatusLabel(row)}
              </span>
              {row.heat_score === 0 ? (
                <span className="text-[11px] text-slate-400 italic">{heatZeroReason(row)}</span>
              ) : null}
            </div>

            <div className="mt-8 grid grid-cols-2 gap-3">
              <MiniMetric label="资讯热度" value={formatNumber(newsHeat(row))} icon={<TrendingUp size={12}/>} />
              <MiniMetric label="结构热度" value={formatNumber(row.structure_heat_score)} icon={<Activity size={12}/>} />
              <MiniMetric label="关联股票" value={formatCount(row.related_stock_count)} />
              <MiniMetric label="观察池" value={formatCount(row.watch_stock_count)} />
            </div>

            <div className="mt-6 flex flex-wrap gap-1.5">
              {row.top_keywords.map((keyword) => (
                <span key={keyword} className="rounded-lg bg-slate-50 border border-slate-100 px-2.5 py-1 text-[11px] font-bold text-slate-600">
                  {keyword}
                </span>
              ))}
            </div>

            <div className="mt-8 pt-6 border-t border-slate-50">
              {row.heat_score === 0 ? (
                <p className="text-xs leading-relaxed text-slate-400 bg-slate-50 p-4 rounded-2xl italic">
                  {heatZeroReason(row)}
                </p>
              ) : (
                <div className="flex items-start gap-3">
                   <div className="mt-1 text-indigo-500"><Zap size={14} /></div>
                   <p className="text-sm leading-relaxed text-slate-500 font-medium line-clamp-3">
                    {row.explanation}
                   </p>
                </div>
              )}
            </div>
          </article>
        ))}
      </motion.section>
    </motion.div>
  );
}

function globalHeat(row: IndustryRadarRow) {
  return isFiniteNumber(row.global_heat_score) ? row.global_heat_score : row.heat_score;
}

function newsHeat(row: IndustryRadarRow) {
  return isFiniteNumber(row.news_heat_score) ? row.news_heat_score : globalHeat(row);
}

function evidenceStatusLabel(row: IndustryRadarRow) {
  const status = normalizeEvidenceStatus(row);
  if (status === "news_active") return "资讯活跃";
  if (status === "structure_active") return "结构活跃";
  if (status === "mapped_only") return "仅有映射";
  return "无证据";
}

function evidenceStatusClass(row: IndustryRadarRow) {
  const status = normalizeEvidenceStatus(row);
  if (status === "news_active") return "bg-red-50 text-red-600 border border-red-100";
  if (status === "structure_active") return "bg-orange-50 text-orange-600 border border-orange-100";
  if (status === "mapped_only") return "bg-amber-50 text-amber-600 border border-amber-100";
  return "bg-slate-50 text-slate-400 border border-slate-100";
}

function heatScoreClass(row: IndustryRadarRow) {
  if (row.heat_score === 0) return "bg-slate-50 text-slate-400";
  if (row.heat_score >= 80) return "bg-red-500 text-white shadow-red-200";
  if (row.heat_score >= 50) return "bg-orange-500 text-white shadow-orange-200";
  return "bg-amber-500 text-white shadow-amber-200";
}

function normalizeEvidenceStatus(row: IndustryRadarRow) {
  const status = row.evidence_status;
  if (status === "资讯活跃" || status === "news_active") return "news_active";
  if (status === "结构活跃" || status === "structure_active") return "structure_active";
  if (status === "仅有映射" || status === "mapped_only") return "mapped_only";
  if (status === "无证据" || status === "no_evidence") return "no_evidence";
  if (row.heat_score === 0) return row.related_stock_count > 0 ? "mapped_only" : "no_evidence";
  if (isFiniteNumber(newsHeat(row)) && newsHeat(row) > 0) return "news_active";
  return "structure_active";
}

function heatZeroReason(row: IndustryRadarRow) {
  if (row.zero_heat_reason) return row.zero_heat_reason;
  if (row.related_stock_count > 0) return `目前仅保留 ${row.related_stock_count} 只关联股票映射。`;
  return "当前没有发现明显的资讯或结构化证据。";
}

function formatNumber(value: number | null | undefined) {
  return isFiniteNumber(value) ? value.toFixed(1) : "-";
}

function formatCount(value: number | null | undefined) {
  return isFiniteNumber(value) ? String(value) : "-";
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function MiniMetric({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
      <div className="flex items-center gap-1.5 mb-1">
        {icon && <span className="text-slate-400">{icon}</span>}
        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{label}</div>
      </div>
      <div className="tabular-nums font-black text-slate-900">{value}</div>
    </div>
  );
}
