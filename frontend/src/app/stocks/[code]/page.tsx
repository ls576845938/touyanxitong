"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Database, History, RotateCcw, TrendingUp, ShieldCheck, Activity, Info } from "lucide-react";
import { motion } from "framer-motion";
import { CandleChart } from "@/components/CandleChart";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { StockSearch } from "@/components/StockSearch";
import { api, type BarRow, type IngestionTask, type InstrumentNavigation, type SourceComparison, type StockEvidence, type StockHistory } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

const containerVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { 
    opacity: 1, 
    y: 0,
    transition: { 
      duration: 0.4,
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 }
};

export default function StockEvidencePage() {
  const params = useParams<{ code: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = params.code;
  const [evidence, setEvidence] = useState<StockEvidence | null>(null);
  const [history, setHistory] = useState<StockHistory | null>(null);
  const [bars, setBars] = useState<BarRow[]>([]);
  const [sourceComparison, setSourceComparison] = useState<SourceComparison | null>(null);
  const [navigation, setNavigation] = useState<InstrumentNavigation | null>(null);
  const [ingestionTask, setIngestionTask] = useState<IngestionTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all([
      api.stockEvidence(code), 
      api.stockHistory(code), 
      api.stockBars(code), 
      api.sourceComparison(code), 
      api.instrumentNavigation(code)
    ])
      .then(([evidenceData, historyData, barRows, sourceRows, navigationData]) => {
        setEvidence(evidenceData);
        setHistory(historyData);
        setBars(barRows);
        setSourceComparison(sourceRows);
        setNavigation(navigationData);
      })
      .catch((err: Error) => setError(`证据链读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [code, refreshKey]);

  const ingestThisStock = () => {
    setIngesting(true);
    setError("");
    api.ingestStock(code)
      .then((task) => {
        setIngestionTask(task);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`单票行情补齐失败：${err.message}`))
      .finally(() => setIngesting(false));
  };

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载单股证据链" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!evidence) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="证据链为空" /></div>;
  const from = searchParams.get("from");

  return (
    <motion.div 
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="min-h-screen bg-slate-50 px-6 py-8 space-y-6"
    >
      {/* Header Search & Nav */}
      <motion.section variants={itemVariants} className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200">
        <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-center">
          <StockSearch placeholder="输入代码或名称搜索标的..." />
          <div className="flex flex-wrap gap-2">
            <button 
              type="button" 
              onClick={() => router.back()} 
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors"
            >
              <RotateCcw size={16} />返回
            </button>
            {from && from !== "search" ? (
              <Link href={from} className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 transition-colors">
                <ArrowLeft size={16} />来源
              </Link>
            ) : null}
            <div className="flex bg-slate-100 rounded-xl p-1">
              {navigation?.previous ? (
                <Link href={`/stocks/${encodeURIComponent(navigation.previous.code)}?from=/stocks/${encodeURIComponent(code)}`} className="inline-flex h-8 items-center gap-2 rounded-lg px-3 text-xs font-semibold text-slate-600 hover:bg-white hover:shadow-sm transition-all">
                  <ArrowLeft size={14} /> 上一只
                </Link>
              ) : <div className="h-8 px-3 opacity-20" />}
              {navigation?.next ? (
                <Link href={`/stocks/${encodeURIComponent(navigation.next.code)}?from=/stocks/${encodeURIComponent(code)}`} className="inline-flex h-8 items-center gap-2 rounded-lg px-3 text-xs font-semibold text-slate-600 hover:bg-white hover:shadow-sm transition-all">
                  下一只 <ArrowRight size={14} />
                </Link>
              ) : <div className="h-8 px-3 opacity-20" />}
            </div>
          </div>
        </div>
      </motion.section>

      {/* Main Stock Info */}
      <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-50 rounded-full -mr-32 -mt-32 opacity-40 blur-3xl pointer-events-none" />
        <div className="relative z-10 flex flex-wrap items-start justify-between gap-6">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">STOCK EVIDENCE TERMINAL</div>
            <h1 className="text-4xl font-black text-slate-900 flex items-baseline gap-3">
              {evidence.stock.name} 
              <span className="text-2xl font-normal text-slate-400 font-mono tracking-tight">{evidence.stock.code}</span>
            </h1>
            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm font-medium text-slate-500">
              <span className="flex items-center gap-1.5"><Activity size={14} className="text-indigo-600" />{marketLabel(evidence.stock.market)} / {boardLabel(evidence.stock.board)}</span>
              <span className="w-1 h-1 bg-slate-300 rounded-full" />
              <span>{evidence.stock.exchange}</span>
              <span className="w-1 h-1 bg-slate-300 rounded-full" />
              <span className="text-slate-900">{evidence.stock.industry_level1}</span>
              <span className="text-slate-400">/</span>
              <span className="text-slate-900">{evidence.stock.industry_level2}</span>
            </div>
          </div>
          <div className="bg-slate-50 p-2 rounded-[2.5rem] border border-slate-100 shadow-inner">
             <ScoreBadge score={evidence.score.final_score} rating={evidence.score.rating} />
          </div>
        </div>
        
        <div className="mt-8 flex flex-wrap gap-2">
          {evidence.stock.concepts.map((concept) => (
            <span key={concept} className="rounded-full bg-slate-50 border border-slate-200 px-3 py-1 text-[11px] font-bold text-slate-600 tracking-tight">
              #{concept}
            </span>
          ))}
        </div>

        <nav className="mt-10 flex flex-wrap gap-1 p-1 bg-slate-50 rounded-2xl w-fit border border-slate-100">
          {["chart", "score", "evidence", "risk", "sources"].map((id) => (
            <a 
              key={id} 
              href={`#${id}`} 
              className="px-5 py-2 rounded-xl text-xs font-bold uppercase tracking-widest text-slate-500 hover:text-indigo-600 hover:bg-white transition-all"
            >
              {id === "chart" ? "K线数据" : id === "score" ? "评分拆解" : id === "evidence" ? "证据链" : id === "risk" ? "风险核验" : "数据源"}
            </a>
          ))}
        </nav>
      </motion.section>

      {/* Primary Metrics Grid */}
      <motion.section variants={itemVariants} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard 
          icon={<ShieldCheck className="text-indigo-600" size={18} />}
          label="评分可信度" 
          value={evidence.score.confidence.level} 
          subValue={formatPct(evidence.score.confidence.combined_confidence)}
        />
        <MetricCard 
          icon={<Activity className="text-emerald-600" size={18} />}
          label="研究准入" 
          value={evidence.score.research_gate.passed ? "PASSED" : "REVIEW"} 
          status={evidence.score.research_gate.passed ? "success" : "warning"}
        />
        <MetricCard 
          icon={<TrendingUp className="text-blue-600" size={18} />}
          label="基本面状态" 
          value={fundamentalLabel(evidence.score.fundamental_summary.status)} 
          subValue={formatPct(evidence.score.fundamental_summary.confidence)}
        />
        <MetricCard 
          icon={<Info className="text-slate-600" size={18} />}
          label="资讯证据" 
          value={evidenceStatusLabel(evidence.score.news_evidence_status)} 
        />
      </motion.section>

      {/* Ingestion Warning */}
      {bars.length === 0 && (
        <motion.section variants={itemVariants} className="bg-amber-50 rounded-2xl border border-amber-200 p-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center text-amber-600">
              <Database size={24} />
            </div>
            <div>
              <div className="font-bold text-slate-900">数据缺失：尚未下载行情数据</div>
              <p className="text-sm text-slate-600 mt-0.5">该标的目前暂无本地K线记录，请补齐行情后查看完整分析。</p>
            </div>
          </div>
          <button 
            type="button" 
            onClick={ingestThisStock} 
            disabled={ingesting} 
            className="bg-slate-900 text-white px-6 py-2.5 rounded-xl text-sm font-bold hover:bg-indigo-600 transition-colors disabled:opacity-50"
          >
            {ingesting ? "正在补齐..." : "立即补齐行情"}
          </button>
        </motion.section>
      )}

      {/* Charts & Scoring Split */}
      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <motion.section id="chart" variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 scroll-mt-6">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div>
              <h2 className="text-xl font-black text-slate-900 tracking-tight">K线走势分析</h2>
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-1">MARKET TREND & PRICE ACTION</div>
            </div>
            <button 
              type="button" 
              onClick={ingestThisStock} 
              disabled={ingesting} 
              className="text-[11px] font-bold uppercase tracking-widest text-slate-400 border border-slate-200 px-4 py-2 rounded-xl hover:text-indigo-600 hover:border-indigo-200 transition-all"
            >
              {ingesting ? "INGESTING..." : "RE-INGEST DATA"}
            </button>
          </div>
          
          <div className="flex flex-wrap gap-2 mb-6">
            {(sourceComparison?.sources ?? []).map((source) => (
              <div key={source.source} className="bg-slate-50 border border-slate-100 rounded-lg px-3 py-1.5 flex items-center gap-2">
                <span className="text-[10px] font-black text-slate-400 uppercase">{source.source}</span>
                <span className="w-1 h-1 bg-slate-300 rounded-full" />
                <span className="text-xs font-mono font-bold text-slate-600">{source.bars_count} BARS</span>
              </div>
            ))}
          </div>

          <div className="rounded-2xl border border-slate-100 p-2 overflow-hidden">
            <CandleChart rows={bars} />
          </div>
          
          {ingestionTask && (
            <div className="mt-4 bg-indigo-50/50 border border-indigo-100 rounded-xl p-4 text-xs font-medium text-indigo-900">
              <div className="flex items-center justify-between">
                <span>INGESTION STATUS: {ingestionTask.status.toUpperCase()}</span>
                <span className="font-mono">P:{ingestionTask.processed} / R:{ingestionTask.requested} / F:{ingestionTask.failed}</span>
              </div>
              {ingestionTask.error && <div className="mt-2 text-red-600">{ingestionTask.error}</div>}
            </div>
          )}
        </motion.section>

        <motion.section id="score" variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 scroll-mt-6">
          <h2 className="text-xl font-black text-slate-900 tracking-tight mb-6">评分引擎拆解</h2>
          
          <div className="grid grid-cols-2 gap-3 mb-8">
            <MiniConfidence label="DATA" value={evidence.score.confidence.data_confidence} />
            <MiniConfidence label="NEWS" value={evidence.score.confidence.news_confidence} />
            <MiniConfidence label="SRC" value={evidence.score.confidence.source_confidence} />
            <MiniConfidence label="FUND" value={evidence.score.confidence.fundamental_confidence} />
          </div>

          <div className="space-y-5">
            <ScoreProgressBar label="产业趋势" value={evidence.score.industry_score} max={30} />
            <ScoreProgressBar label="公司质量" value={evidence.score.company_score} max={30} />
            <ScoreProgressBar label="股价趋势" value={evidence.score.trend_score} max={30} />
            <ScoreProgressBar label="信息催化" value={evidence.score.catalyst_score} max={30} />
            <ScoreProgressBar label="风险扣分" value={evidence.score.risk_penalty} max={15} isNegative />
          </div>

          <div className="mt-8 pt-8 border-t border-slate-100">
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-3">AI EXECUTIVE SUMMARY</div>
            <p className="text-sm leading-relaxed text-slate-600 font-medium">{evidence.score.explanation}</p>
          </div>
        </motion.section>
      </div>

      {/* History Timeline */}
      <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-6 mb-8">
          <div>
            <div className="flex items-center gap-3 text-xl font-black text-slate-900 tracking-tight">
              <div className="w-10 h-10 bg-slate-900 rounded-xl flex items-center justify-center text-white">
                <History size={20} />
              </div>
              评分历史时间线
            </div>
            <p className="mt-2 text-sm font-medium text-slate-500">追踪该标的在历史交易日中的评级变动与趋势信号</p>
          </div>
          <div className="flex gap-4">
            <div className="text-right">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">SNAPSHOTS</div>
              <div className="text-xl font-bold text-slate-900">{history?.history.length ?? 0}</div>
            </div>
            <div className="text-right">
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">DELTA</div>
              <div className={`text-xl font-bold ${deltaClass(history?.latest?.score_delta)}`}>
                {formatDelta(history?.latest?.score_delta)}
              </div>
            </div>
          </div>
        </div>

        <div className="overflow-x-auto -mx-8 px-8">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="pb-4 text-[10px] font-black uppercase tracking-widest text-slate-400">DATE</th>
                <th className="pb-4 text-[10px] font-black uppercase tracking-widest text-slate-400">RATING</th>
                <th className="pb-4 text-[10px] font-black uppercase tracking-widest text-slate-400 text-right">SCORE</th>
                <th className="pb-4 text-[10px] font-black uppercase tracking-widest text-slate-400 text-right">TREND</th>
                <th className="pb-4 text-[10px] font-black uppercase tracking-widest text-slate-400">SIGNALS</th>
                <th className="pb-4 text-[10px] font-black uppercase tracking-widest text-slate-400">EVIDENCE SUMMARY</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {(history?.history ?? []).map((row) => (
                <tr key={row.trade_date} className="hover:bg-slate-50/50 transition-colors group">
                  <td className="py-5 font-mono text-xs font-bold text-slate-500">{row.trade_date}</td>
                  <td className="py-5">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-black bg-slate-900 text-white uppercase tracking-tighter">
                      {row.rating}
                    </span>
                  </td>
                  <td className="py-5 text-right">
                    <div className="text-sm font-black text-slate-900">{formatNumber(row.final_score)}</div>
                    <div className={`text-[10px] font-bold ${deltaClass(row.score_delta)}`}>{formatDelta(row.score_delta)}</div>
                  </td>
                  <td className="py-5 text-right font-mono text-xs font-bold text-slate-600">{formatNumber(row.trend_score)}</td>
                  <td className="py-5">
                    <div className="flex flex-wrap gap-1.5">
                      {row.is_ma_bullish && <SignalTag label="BULLISH" color="emerald" />}
                      {row.is_breakout_120d && <SignalTag label="120D BK" color="indigo" />}
                      {row.is_breakout_250d && <SignalTag label="250D BK" color="rose" />}
                    </div>
                  </td>
                  <td className="py-5 pl-4 max-w-md">
                    <div className="text-xs font-medium text-slate-600 line-clamp-2 leading-relaxed">
                      {row.summary || row.score_explanation}
                    </div>
                    {row.risk_summary && (
                      <div className="mt-1 text-[10px] font-bold text-red-500 uppercase flex items-center gap-1">
                         <AlertTriangle size={10} /> {row.risk_summary}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.section>

      {/* Logic Evidence Grid */}
      <motion.section id="evidence" variants={itemVariants} className="grid scroll-mt-6 gap-6 lg:grid-cols-2">
        <EvidenceCard title="产业逻辑" text={evidence.evidence.industry_logic} category="INDUSTRY" />
        <EvidenceCard title="公司逻辑" text={evidence.evidence.company_logic} category="COMPANY" />
        <EvidenceCard title="趋势逻辑" text={evidence.evidence.trend_logic} category="TREND" />
        <EvidenceCard title="催化逻辑" text={evidence.evidence.catalyst_logic} category="CATALYST" />
      </motion.section>

      {/* Risk & Verification */}
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <motion.section id="risk" variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 border-l-[12px] border-l-red-500 scroll-mt-6">
          <div className="flex items-center gap-3 text-xl font-black text-red-600 tracking-tight mb-6">
            <AlertTriangle size={24} /> 核心风险提示
          </div>
          <p className="text-sm leading-loose text-slate-700 font-medium bg-red-50/30 p-6 rounded-2xl border border-red-50">
            {evidence.evidence.risk_summary}
          </p>
        </motion.section>

        <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 scroll-mt-6">
          <div className="flex items-center gap-3 text-xl font-black text-slate-900 tracking-tight mb-6">
            <CheckCircle2 size={24} className="text-indigo-600" /> 待核验关键事项
          </div>
          <ul className="space-y-4">
            {evidence.evidence.questions_to_verify.map((question, i) => (
              <li key={i} className="flex gap-4 group">
                <span className="flex-shrink-0 w-6 h-6 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center text-xs font-black">
                  {i + 1}
                </span>
                <span className="text-sm font-semibold text-slate-600 group-hover:text-slate-900 transition-colors">
                  {question}
                </span>
              </li>
            ))}
          </ul>
        </motion.section>
      </div>

      {/* Sources Terminal */}
      <motion.section id="sources" variants={itemVariants} className="bg-slate-900 rounded-3xl p-8 shadow-2xl border border-slate-800 text-slate-300 scroll-mt-6">
        <div className="flex flex-wrap items-center justify-between gap-6 mb-8">
          <div>
            <div className="flex items-center gap-3 text-xl font-black text-white tracking-tight">
              <Database size={20} className="text-indigo-400" /> 数据源可信度终端
            </div>
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">DATA PROVENANCE & CONFIDENCE SCORING</div>
          </div>
          <div className="flex gap-4">
            <MiniDarkStat label="SOURCE" value={formatPct(evidence.score.confidence.source_confidence)} />
            <MiniDarkStat label="NEWS" value={formatPct(evidence.score.confidence.news_confidence)} />
          </div>
        </div>

        <div className="grid gap-4">
          {evidence.evidence.source_refs.map((ref, i) => (
            <div key={i} className="bg-slate-800/50 border border-slate-700 rounded-2xl p-5 hover:bg-slate-800 transition-all group">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-indigo-400 mb-1">{ref.source}</div>
                  <h3 className="text-sm font-bold text-white group-hover:text-indigo-300 transition-colors">{ref.title}</h3>
                  <div className="mt-2 text-xs font-mono text-slate-500 break-all">{ref.url}</div>
                </div>
                <div className="px-3 py-1 rounded-full bg-slate-900 text-[10px] font-black text-slate-400 border border-slate-700">
                  REF-{i.toString().padStart(3, '0')}
                </div>
              </div>
            </div>
          ))}
        </div>
      </motion.section>
    </motion.div>
  );
}

function MetricCard({ label, value, subValue, icon, status }: { label: string; value: string; subValue?: string; icon: React.ReactNode; status?: "success" | "warning" }) {
  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-200 group hover:border-indigo-200 transition-all">
      <div className="flex items-center gap-2 mb-3">
        <div className="p-2 bg-slate-50 rounded-lg group-hover:bg-indigo-50 transition-colors">{icon}</div>
        <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className={`text-xl font-black tracking-tight ${status === "success" ? "text-emerald-600" : status === "warning" ? "text-amber-600" : "text-slate-900"}`}>
          {value}
        </span>
        {subValue && <span className="text-xs font-bold text-slate-400 font-mono">{subValue}</span>}
      </div>
    </div>
  );
}

function ScoreProgressBar({ label, value, max, isNegative = false }: { label: string; value: number | null; max: number; isNegative?: boolean }) {
  const percentage = Math.min(100, Math.max(0, ((value ?? 0) / max) * 100));
  const colorClass = isNegative ? "bg-red-500" : "bg-indigo-600";
  
  return (
    <div>
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">{label}</span>
        <span className="text-sm font-black text-slate-900 font-mono">{value?.toFixed(1) ?? "-"}</span>
      </div>
      <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
        <motion.div 
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className={`h-full rounded-full ${colorClass}`}
        />
      </div>
    </div>
  );
}

function MiniConfidence({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="bg-slate-50 rounded-xl p-3 border border-slate-100 text-center">
      <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1">{label}</div>
      <div className="text-xs font-black text-slate-800 font-mono">{formatPct(value)}</div>
    </div>
  );
}

function EvidenceCard({ title, text, category }: { title: string; text: string; category: string }) {
  return (
    <article className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 group hover:shadow-md transition-all">
      <div className="text-[10px] font-black uppercase tracking-widest text-indigo-400 mb-2">{category} LOGIC</div>
      <h2 className="text-xl font-black text-slate-900 mb-4">{title}</h2>
      <p className="text-sm leading-loose text-slate-600 font-medium group-hover:text-slate-900 transition-colors">
        {text}
      </p>
    </article>
  );
}

function SignalTag({ label, color }: { label: string; color: "emerald" | "indigo" | "rose" }) {
  const colors = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-100",
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-100",
    rose: "bg-rose-50 text-rose-700 border-rose-100"
  };
  return (
    <span className={`px-2 py-0.5 rounded-md text-[9px] font-black border uppercase tracking-tighter ${colors[color]}`}>
      {label}
    </span>
  );
}

function MiniDarkStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <div className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-0.5">{label}</div>
      <div className="text-sm font-black text-white font-mono">{value}</div>
    </div>
  );
}

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : value.toFixed(1);
}

function formatPct(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "-";
}

function fundamentalLabel(status: string) {
  if (status === "complete") return "COMPLETE";
  if (status === "partial") return "PARTIAL";
  return "UNKNOWN";
}

function evidenceStatusLabel(status: string | null | undefined) {
  if (status === "active" || status === "sourced") return "SUFFICIENT";
  if (status === "partial" || status === "needs_verification") return "PENDING";
  return "MISSING";
}

function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return "NEW";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function deltaClass(value: number | null | undefined) {
  if (value === null || value === undefined) return "text-slate-400";
  if (value > 0) return "text-emerald-500";
  if (value < 0) return "text-rose-500";
  return "text-slate-400";
}
