"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Clipboard, FileText, Filter, Layout, ArrowLeft } from "lucide-react";
import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type ResearchBrief } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.05 }
  }
};

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0 }
};

export default function ResearchBriefPage() {
  const [brief, setBrief] = useState<ResearchBrief | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [watchOnly, setWatchOnly] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.researchBrief({ market, board: market === "A" ? board : "all", watchOnly, limit: 120 })
      .then(setBrief)
      .catch((err: Error) => setError(`研究工作单读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board, watchOnly]);

  const copyMarkdown = async () => {
    if (!brief?.markdown) return;
    await navigator.clipboard.writeText(brief.markdown);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在生成研究工作单" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!brief) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="研究工作单为空" /></div>;

  return (
    <div className="min-h-screen bg-slate-50 p-6 lg:p-10">
      <motion.div 
        variants={container}
        initial="hidden"
        animate="show"
        className="mx-auto max-w-7xl space-y-8"
      >
        {/* Header Section */}
        <motion.section variants={item} className="flex flex-wrap items-end justify-between gap-6">
          <div className="space-y-2">
            <Link href="/research" className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-indigo-600 hover:text-indigo-700 transition-colors mb-2">
              <ArrowLeft size={12} /> Back to Hub
            </Link>
            <h1 className="text-4xl font-bold tracking-tight text-slate-900">每日研究工作单</h1>
            <p className="max-w-2xl text-base text-slate-500">
              汇总优先级、股票和赛道为可执行工作单。用于人工核验证据，不构成交易指令。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button 
              type="button" 
              onClick={copyMarkdown} 
              className={`flex h-12 items-center gap-3 rounded-2xl px-6 text-sm font-semibold transition-all shadow-sm ${
                copied 
                  ? "bg-emerald-500 text-white shadow-emerald-200" 
                  : "bg-indigo-600 text-white shadow-indigo-200 hover:bg-indigo-700"
              }`}
            >
              <Clipboard size={18} /> 
              <span>{copied ? "已复制到剪贴板" : "复制 Markdown"}</span>
            </button>
            <Link 
              href="/research" 
              className="flex h-12 items-center gap-3 rounded-2xl bg-white px-6 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-slate-200 transition-all hover:bg-slate-50"
            >
              <FileText size={18} className="text-slate-400" /> 
              <span>任务中心</span>
            </Link>
          </div>
        </motion.section>

        {/* Filters Section */}
        <motion.section variants={item} className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="flex flex-wrap items-center gap-6">
            <div className="space-y-4 flex-1 min-w-[300px]">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Generation Scope</div>
              <div className="flex flex-wrap gap-2">
                {MARKET_OPTIONS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => {
                      setMarket(option);
                      if (option !== "A") setBoard("all");
                    }}
                    className={`h-10 rounded-xl px-4 text-sm font-medium transition-all ${
                      market === option 
                        ? "bg-slate-900 text-white shadow-lg shadow-slate-200" 
                        : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {marketLabel(option)}
                  </button>
                ))}
              </div>
            </div>
            
            <div className="h-12 w-px bg-slate-100 hidden lg:block" />

            <div className="flex items-center gap-6">
              <label className="flex items-center gap-3 cursor-pointer group">
                <div className="relative flex items-center">
                  <input 
                    type="checkbox" 
                    checked={watchOnly} 
                    onChange={(event) => setWatchOnly(event.target.checked)}
                    className="peer sr-only"
                  />
                  <div className="h-6 w-11 rounded-full bg-slate-200 transition-colors peer-checked:bg-indigo-600" />
                  <div className="absolute left-1 top-1 h-4 w-4 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
                </div>
                <span className="text-sm font-bold text-slate-600 group-hover:text-slate-900 transition-colors">仅观察池候选</span>
              </label>
              
              <div className="text-right">
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Snapshot</div>
                <div className="text-sm font-bold text-slate-900">{brief.latest_date ?? "-"}</div>
              </div>
            </div>
          </div>

          {market === "A" && (
            <div className="mt-6 flex flex-wrap gap-2 border-t border-slate-50 pt-6">
              {A_BOARD_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setBoard(option)}
                  className={`h-8 rounded-lg px-3 text-xs font-medium transition-all ${
                    board === option 
                      ? "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200" 
                      : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                  }`}
                >
                  {boardLabel(option)}
                </button>
              ))}
            </div>
          )}
        </motion.section>

        {/* Metrics Section */}
        <motion.section variants={item} className="grid gap-4 grid-cols-2 md:grid-cols-4">
          <Metric label="任务总数" value={brief.summary.task_count} />
          <Metric label="涉及股票" value={brief.summary.stock_count} />
          <Metric label="高优先级" value={brief.summary.high_priority_count} highlight />
          <Metric label="风险核验" value={brief.summary.risk_task_count} danger />
        </motion.section>

        <motion.section variants={item} className="grid gap-8 lg:grid-cols-[1fr_1.2fr]">
          <div className="space-y-8">
            {/* Focus Stocks */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 px-2">
                <Layout size={18} className="text-slate-400" />
                <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500">重点关注标的</h2>
              </div>
              <div className="space-y-3">
                {brief.focus_stocks.slice(0, 10).map((row) => (
                  <Link 
                    key={row.stock_code} 
                    href={`/stocks/${encodeURIComponent(row.stock_code)}?from=/research/brief`} 
                    className="group block rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 transition-all hover:shadow-lg hover:shadow-slate-200/50"
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <div className="text-lg font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">{row.stock_name}</div>
                        <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{row.stock_code}</div>
                        <div className="mt-1 text-[11px] font-medium text-slate-500">
                          {marketLabel(row.market)} · {boardLabel(row.board)} · {row.industry} · {row.rating}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xl font-black text-slate-900">{row.final_score.toFixed(1)}</div>
                        <div className="text-[10px] font-bold text-slate-400 uppercase">{row.task_count} TASKS</div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {row.top_task_titles.slice(0, 2).map((title) => (
                        <span key={`${row.stock_code}-${title}`} className="rounded-lg bg-slate-50 px-2.5 py-1 text-[10px] font-bold text-slate-600 ring-1 ring-slate-100">
                          {title}
                        </span>
                      ))}
                    </div>
                  </Link>
                ))}
              </div>
            </div>

            {/* Industry Distribution */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 px-2 border-t border-slate-200 pt-8">
                <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500">产业热度分布</h2>
              </div>
              <div className="space-y-3">
                {brief.focus_industries.map((row) => (
                  <div key={row.industry} className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
                    <div className="flex items-center justify-between mb-3">
                      <div className="text-base font-bold text-slate-900">{row.industry}</div>
                      <div className="text-sm font-black text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-lg">{row.average_priority_score.toFixed(1)}</div>
                    </div>
                    <div className="grid grid-cols-4 gap-2 mb-4">
                      <MiniStat label="TASKS" value={row.task_count} />
                      <MiniStat label="STOCKS" value={row.stock_count} />
                      <MiniStat label="HIGH" value={row.high_priority_count} highlight />
                      <MiniStat label="RISK" value={row.risk_task_count} danger />
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {row.top_stocks.map((stock) => (
                        <Link 
                          key={`${row.industry}-${stock.stock_code}`} 
                          href={`/stocks/${encodeURIComponent(stock.stock_code)}?from=/research/brief`} 
                          className="rounded-lg bg-slate-50 px-2 py-1 text-[11px] font-bold text-slate-600 hover:bg-indigo-600 hover:text-white transition-all"
                        >
                          {stock.stock_name} <span className="opacity-60">{stock.final_score.toFixed(1)}</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Markdown Content */}
          <div className="relative">
            <div className="sticky top-10 space-y-4">
              <div className="flex items-center justify-between px-2">
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500">Markdown 工作单预览</h2>
                </div>
              </div>
              <div className="rounded-3xl bg-white shadow-xl shadow-slate-200/50 ring-1 ring-slate-200 overflow-hidden">
                <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50/50 px-6 py-3">
                  <div className="flex gap-1.5">
                    <div className="size-2.5 rounded-full bg-slate-200" />
                    <div className="size-2.5 rounded-full bg-slate-200" />
                    <div className="size-2.5 rounded-full bg-slate-200" />
                  </div>
                  <div className="mx-auto text-[10px] font-black uppercase tracking-widest text-slate-400">RESEARCH_REPORT.md</div>
                </div>
                <pre className="max-h-[850px] overflow-auto whitespace-pre-wrap p-8 text-sm leading-8 text-slate-800 font-mono">
                  {brief.markdown}
                </pre>
              </div>
            </div>
          </div>
        </motion.section>
      </motion.div>
    </div>
  );
}

function Metric({ label, value, highlight, danger }: { label: string; value: string | number; highlight?: boolean; danger?: boolean }) {
  return (
    <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 transition-all hover:shadow-lg hover:shadow-slate-200/50">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-2 text-3xl font-black tracking-tight ${
        highlight ? "text-indigo-600" : danger ? "text-red-500" : "text-slate-900"
      }`}>
        {value}
      </div>
    </div>
  );
}

function MiniStat({ label, value, highlight, danger }: { label: string; value: number; highlight?: boolean; danger?: boolean }) {
  return (
    <div className="text-center">
      <div className="text-[8px] font-black text-slate-400 tracking-tighter uppercase">{label}</div>
      <div className={`text-xs font-bold ${highlight ? "text-indigo-600" : danger ? "text-red-500" : "text-slate-900"}`}>
        {value}
      </div>
    </div>
  );
}
