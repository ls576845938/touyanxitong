"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Newspaper, Tags, ArrowLeft, Target, Activity, Share2, ExternalLink } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { IndustryDetailHeatChart } from "@/components/IndustryDetailHeatChart";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { api, type IndustryDetail, type IndustryDetailStock } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

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

export default function IndustryDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const market = searchParams.get("market") ?? "ALL";
  const [detail, setDetail] = useState<IndustryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const removedRoute = params.id === "chain-cockpit";

  useEffect(() => {
    if (removedRoute) {
      setLoading(false);
      setDetail(null);
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    api.industryDetail(params.id, { market })
      .then(setDetail)
      .catch((err: Error) => setError(`赛道详情读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [params.id, market, removedRoute]);

  if (removedRoute) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="该页面已删除" /></div>;
  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载赛道详情" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!detail) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="赛道详情为空" /></div>;

  return (
    <motion.div 
      className="min-h-screen bg-slate-50 p-6 lg:p-10 space-y-8"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      <motion.div variants={itemVariants}>
        <Link href="/industry" className="inline-flex items-center gap-2 text-slate-500 hover:text-indigo-600 font-bold text-sm transition-colors mb-6 group">
          <ArrowLeft size={16} className="group-hover:-translate-x-1 transition-transform" />
          返回产业雷达
        </Link>
        
        <div className="bg-white border border-slate-200 rounded-[2.5rem] p-8 lg:p-12 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 p-12 opacity-[0.03] pointer-events-none">
            <Target size={240} />
          </div>
          
          <div className="flex flex-wrap items-start justify-between gap-8 relative z-10">
            <div className="max-w-3xl">
              <div className="flex items-center gap-3 mb-4">
                <span className="bg-indigo-600 text-white text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest">
                  Industry Insight
                </span>
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                  {detail.summary.market_label} Market
                </span>
              </div>
              <h1 className="text-5xl font-black text-slate-900 tracking-tight mb-6">{detail.industry.name}</h1>
              <p className="text-lg leading-relaxed text-slate-500 font-medium">{detail.industry.description}</p>
              
              <div className="mt-8 flex flex-wrap gap-2">
                {detail.industry.keywords.map((keyword) => (
                  <span key={keyword} className="rounded-xl bg-slate-100 border border-slate-200 px-4 py-1.5 text-xs font-bold text-slate-600">
                    #{keyword}
                  </span>
                ))}
              </div>
            </div>

            <div className="bg-slate-900 rounded-[2rem] p-8 text-white shadow-2xl min-w-[200px] text-center">
              <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Latest Heat</div>
              <div className="text-5xl font-black italic tabular-nums tracking-tighter">
                {detail.latest_heat?.heat_score.toFixed(1) ?? "-"}
              </div>
              <div className={`mt-3 text-sm font-bold ${detail.latest_heat?.heat_score_delta && detail.latest_heat.heat_score_delta > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {formatDelta(detail.latest_heat?.heat_score_delta)}
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      <motion.section variants={itemVariants} className="grid gap-4 md:grid-cols-5">
        <Metric label="关联股票" value={detail.summary.related_stock_count} />
        <Metric label="观察候选" value={detail.summary.watch_stock_count} />
        <Metric label="强观察" value={detail.summary.strong_watch_count} />
        <Metric label="相关新闻" value={detail.summary.recent_article_count} />
        <Metric label="热度趋势" value={formatDelta(detail.latest_heat?.heat_score_delta)} highlight />
      </motion.section>

      <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <motion.div variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-8 shadow-sm">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h2 className="text-xl font-black text-slate-900">热度历史回顾</h2>
              <p className="mt-1 text-sm text-slate-500 font-medium">Heat Score History & Trend Analysis</p>
            </div>
            <Activity className="text-indigo-600" />
          </div>
          <div className="h-[400px]">
            <IndustryDetailHeatChart rows={detail.heat_history} />
          </div>
        </motion.div>

        <motion.div variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-8 shadow-sm">
          <div className="flex items-center gap-2 mb-8">
            <Tags size={20} className="text-indigo-600" />
            <h2 className="text-xl font-black text-slate-900 uppercase tracking-tight">热度引擎拆解</h2>
          </div>
          
          <div className="grid grid-cols-3 gap-4 mb-8">
            <MiniMetric label="1D Impact" value={detail.latest_heat?.heat_1d.toFixed(1) ?? "-"} />
            <MiniMetric label="7D Momentum" value={detail.latest_heat?.heat_7d.toFixed(1) ?? "-"} />
            <MiniMetric label="30D Volume" value={detail.latest_heat?.heat_30d.toFixed(1) ?? "-"} />
          </div>

          <div className="bg-slate-50 rounded-3xl p-6 border border-slate-100 mb-8">
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Narrative Analysis</div>
            <p className="text-sm leading-relaxed text-slate-600 font-medium">
              {detail.latest_heat?.explanation ?? "暂无热度解释。"}
            </p>
          </div>

          <div className="space-y-3">
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Key Evidence</div>
            {(detail.latest_heat?.top_articles ?? []).slice(0, 4).map((title, idx) => (
              <div key={idx} className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-white p-4 text-xs font-bold text-slate-700 shadow-sm hover:border-indigo-200 transition-colors">
                <div className="mt-0.5 text-indigo-500"><Share2 size={12} /></div>
                <span className="line-clamp-2 leading-relaxed">{title}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      <motion.section variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] overflow-hidden shadow-sm">
        <div className="border-b border-slate-100 p-8 lg:px-10">
          <h2 className="text-2xl font-black text-slate-900">赛道关联股票</h2>
          <p className="mt-1 text-sm text-slate-500 font-medium">Sorted by Comprehensive Score & Alpha Signal</p>
        </div>
        <StockTable rows={detail.related_stocks} industryId={params.id} />
      </motion.section>

      <motion.section variants={itemVariants} className="bg-white border border-slate-200 rounded-[2.5rem] p-8 lg:p-10 shadow-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="bg-slate-900 p-2 rounded-xl text-white">
            <Newspaper size={20} />
          </div>
          <h2 className="text-2xl font-black text-slate-900">相关新闻证据链</h2>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          {detail.recent_articles.map((article, idx) => (
            <article key={idx} className="group relative rounded-[2rem] border border-slate-100 bg-slate-50 p-6 hover:bg-white hover:shadow-xl hover:shadow-slate-200/50 transition-all duration-500">
              <div className="flex justify-between items-start gap-4 mb-4">
                <h3 className="font-black text-slate-900 text-lg group-hover:text-indigo-600 transition-colors">{article.title}</h3>
                <Link href={article.source_url} target="_blank" className="text-slate-300 hover:text-indigo-600 transition-colors">
                  <ExternalLink size={18} />
                </Link>
              </div>
              <p className="text-sm leading-relaxed text-slate-500 font-medium mb-6">{article.summary}</p>
              <div className="flex flex-wrap gap-2 mb-6">
                {article.matched_keywords.slice(0, 6).map((keyword) => (
                  <span key={keyword} className="rounded-lg bg-white border border-slate-100 px-3 py-1 text-[10px] font-black text-indigo-600 uppercase tracking-wider shadow-sm">
                    {keyword}
                  </span>
                ))}
              </div>
              <div className="flex items-center justify-between pt-6 border-t border-slate-200/50">
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{article.source}</span>
                <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{article.published_at.slice(0, 10)}</span>
              </div>
            </article>
          ))}
        </div>
      </motion.section>
    </motion.div>
  );
}

function StockTable({ rows, industryId }: { rows: IndustryDetailStock[]; industryId: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1080px] text-left text-sm">
        <thead>
          <tr className="bg-slate-50 text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">
            <th className="px-8 py-5">Equity & Symbol</th>
            <th className="px-4 py-5">Market</th>
            <th className="px-4 py-5">Sector Node</th>
            <th className="px-4 py-5">Alpha Score</th>
            <th className="px-4 py-5 text-right">Industry</th>
            <th className="px-4 py-5 text-right">Company</th>
            <th className="px-4 py-5 text-right">Trend</th>
            <th className="px-4 py-5 text-right">Risk</th>
            <th className="px-4 py-5">Patterns</th>
            <th className="px-8 py-5">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {rows.map((row) => (
            <tr key={row.code} className="hover:bg-slate-50/50 transition-colors group">
              <td className="px-8 py-5">
                <div className="font-black text-slate-900 text-base">{row.name}</div>
                <div className="text-[10px] font-bold text-slate-400 tracking-wider tabular-nums">{row.code}</div>
              </td>
              <td className="px-4 py-5">
                <div className="text-xs font-black text-slate-700">{marketLabel(row.market)}</div>
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-tight">{boardLabel(row.board)}</div>
              </td>
              <td className="px-4 py-5">
                <div className="text-xs font-bold text-slate-600 mb-1.5">{row.industry_level2}</div>
                <Concepts items={row.concepts} />
              </td>
              <td className="px-4 py-5">
                <ScoreBadge score={row.final_score} rating={row.rating} />
              </td>
              <td className="px-4 py-5 text-right font-black tabular-nums text-slate-700">{formatNumber(row.industry_score)}</td>
              <td className="px-4 py-5 text-right font-black tabular-nums text-slate-700">{formatNumber(row.company_score)}</td>
              <td className="px-4 py-5 text-right font-black tabular-nums text-slate-700">{formatNumber(row.trend_score)}</td>
              <td className="px-4 py-5 text-right font-black tabular-nums text-rose-500">{formatNumber(row.risk_penalty)}</td>
              <td className="px-4 py-5">
                <div className="flex flex-wrap gap-1.5">
                  <Flag active={row.is_ma_bullish} label="多头" />
                  <Flag active={row.is_breakout_120d} label="120H" />
                </div>
              </td>
              <td className="px-8 py-5">
                <Link 
                  href={`/stocks/${encodeURIComponent(row.code)}?from=/industry/${industryId}`} 
                  className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-slate-100 text-slate-400 hover:bg-indigo-600 hover:text-white transition-all shadow-sm"
                >
                  <ExternalLink size={14} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Concepts({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.slice(0, 3).map((item) => (
        <span key={item} className="rounded-md bg-white border border-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500 shadow-sm">
          {item}
        </span>
      ))}
    </div>
  );
}

function Metric({ label, value, highlight }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="bg-white border border-slate-200 rounded-[2rem] p-6 shadow-sm group hover:border-indigo-200 transition-colors">
      <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">{label}</div>
      <div className={`text-2xl font-black italic tabular-nums ${highlight ? 'text-indigo-600' : 'text-slate-900'}`}>
        {value}
      </div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-50 rounded-2xl p-4 border border-slate-100">
      <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">{label}</div>
      <div className="text-base font-black text-slate-900 tabular-nums tracking-tight">{value}</div>
    </div>
  );
}

function Flag({ active, label }: { active: boolean | null; label: string }) {
  if (!active) return null;
  return (
    <span className="rounded-lg bg-indigo-50 text-indigo-600 px-2 py-1 text-[10px] font-black uppercase tracking-wider border border-indigo-100 shadow-sm">
      {label}
    </span>
  );
}

function formatNumber(value: number | null) {
  return value === null ? "-" : value.toFixed(1);
}

function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return "NEW";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}
