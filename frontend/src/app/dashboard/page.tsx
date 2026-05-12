"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { 
  Activity,
  ArrowRight, 
  ArrowUpRight,
  BarChart3, 
  ClipboardCheck, 
  Crosshair,
  FileText, 
  FlaskConical,
  Radar,
  Repeat2, 
  Share2,
  ShieldCheck,
  Target,
  TrendingUp
} from "lucide-react";
import { motion } from "framer-motion";
import { api, type DataQuality, type DataStatus, type IndustryRadarRow, type IngestionTask, type MarketSummary, type ReportSummary, type ResearchDataGate, type ResearchUniverse, type SignalBacktestLatest, type TenbaggerThesisList, type TrendPoolRow, type WatchlistChanges } from "@/lib/api";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { boardLabel, marketLabel } from "@/lib/markets";

export default function DashboardPage() {
  const [summary, setSummary] = useState<MarketSummary | null>(null);
  const [industries, setIndustries] = useState<IndustryRadarRow[]>([]);
  const [trendPool, setTrendPool] = useState<TrendPoolRow[]>([]);
  const [report, setReport] = useState<ReportSummary | null>(null);
  const [dataStatus, setDataStatus] = useState<DataStatus | null>(null);
  const [dataQuality, setDataQuality] = useState<DataQuality | null>(null);
  const [ingestionTasks, setIngestionTasks] = useState<IngestionTask[]>([]);
  const [researchUniverse, setResearchUniverse] = useState<ResearchUniverse | null>(null);
  const [watchlistChanges, setWatchlistChanges] = useState<WatchlistChanges | null>(null);
  const [thesisSnapshot, setThesisSnapshot] = useState<TenbaggerThesisList | null>(null);
  const [researchGate, setResearchGate] = useState<ResearchDataGate | null>(null);
  const [backtestSnapshot, setBacktestSnapshot] = useState<SignalBacktestLatest | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.marketSummary(),
      api.watchlistChanges(),
      api.industryRadar(),
      api.trendPool({ limit: 80 }),
      api.reports()
    ])
      .then(([marketSummary, changes, industryRows, trendRows, reports]) => {
        setSummary(marketSummary);
        setWatchlistChanges(changes);
        setIndustries(industryRows);
        setTrendPool(trendRows);
        setReport(reports[0] ?? null);
      })
      .catch((err: Error) => setError(`无法读取后端数据：${err.message}。请先运行 daily pipeline 并启动 FastAPI。`))
      .finally(() => setLoading(false));

    void Promise.allSettled([
      api.dataStatus(),
      api.dataQuality(),
      api.ingestionTasks(),
      api.researchUniverse()
    ]).then(([status, quality, tasks, universe]) => {
      setDataStatus(status.status === "fulfilled" ? status.value : null);
      setDataQuality(quality.status === "fulfilled" ? quality.value : null);
      setIngestionTasks(tasks.status === "fulfilled" ? tasks.value : []);
      setResearchUniverse(universe.status === "fulfilled" ? universe.value : null);
    });

    void Promise.allSettled([
      api.tenbaggerTheses({ limit: 6 }),
      api.researchDataGate({ limit: 6 }),
      api.latestBacktest()
    ]).then(([thesis, gate, backtest]) => {
      setThesisSnapshot(thesis.status === "fulfilled" ? thesis.value : null);
      setResearchGate(gate.status === "fulfilled" ? gate.value : null);
      setBacktestSnapshot(backtest.status === "fulfilled" ? backtest.value : null);
    });
  }, []);

  if (loading) return <div className="min-h-[60vh] flex items-center justify-center"><LoadingState label="系统正在同步全球产业波动数据" /></div>;
  if (error) return <div className="max-w-2xl mx-auto py-12"><ErrorState message={error} /></div>;

  const topStocks = trendPool.slice(0, 8);
  const latestRun = dataStatus?.runs?.[0] ?? null;
  const queuedTasks = ingestionTasks.filter((task) => ["queued", "pending"].includes(task.status)).length;
  const runningTasks = ingestionTasks.filter((task) => task.status === "running").length;
  const thesisSummary = thesisSnapshot?.summary;
  const gateSummary = researchGate?.summary;
  const latestBacktest = backtestSnapshot?.latest ?? null;
  const gateStatus = (gateSummary?.fail_count ?? 0) > 0 ? "FAIL" : (gateSummary?.pass_count ?? 0) > 0 ? "PASS" : "WARN";
  const formalReadyPct = Math.round((gateSummary?.formal_ready_ratio ?? 0) * 100);

  return (
    <div className="space-y-6">
      {/* Hero Section */}
      <motion.section 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid gap-6 lg:grid-cols-[1.6fr_0.8fr]"
      >
        <div className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
          <div className="flex items-center gap-3">
             <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
               <Activity size={20} />
             </div>
             <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">MARKET PULSE / {summary?.latest_trade_date ?? "TODAY"}</p>
          </div>
          <h1 className="mt-4 text-3xl font-bold tracking-tight text-slate-900">产业热度、趋势强度与证据链观察台</h1>
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-slate-500 font-medium">
            AlphaRadar 通过多维数据挖掘生成高确定性的观察池和研究线索。产业热度综合了资讯共振、资金流向及关联个股的量价特征。
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 md:grid-cols-4">
            <Metric label="样本股票" value={summary?.stock_count ?? 0} unit="Symbols" />
            <Metric label="观察候选" value={summary?.watch_count ?? 0} unit="Watchlisted" highlight />
            <Metric label="产业热度记录" value={summary?.industry_heat_records ?? 0} unit="Records" />
            <Metric label="最新交易日" value={summary?.latest_trade_date?.split('-').slice(1).join('/') ?? "-"} unit="Trade Date" />
          </div>
        </div>
        
        <div className="rounded-3xl bg-indigo-600 p-8 shadow-xl shadow-indigo-200 text-white flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-indigo-200">
              <FileText size={14} />
              DAILY BRIEFING
            </div>
            <p className="mt-6 text-xl font-bold leading-tight">{report?.title || "暂无最新报告"}</p>
            <p className="mt-4 text-sm leading-relaxed text-indigo-100 line-clamp-3">
              {report?.market_summary || "等待系统生成今日市场简报..."}
            </p>
          </div>
          <Link href="/report" className="mt-8 inline-flex items-center justify-center gap-2 rounded-xl bg-white px-6 py-3 text-sm font-bold text-indigo-600 transition-transform hover:scale-[1.02] active:scale-[0.98]">
            阅读全文 <ArrowRight size={16} />
          </Link>
        </div>
      </motion.section>

      {/* Tenbagger Research Loop */}
      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.9fr_0.9fr]">
        <Link href="/research/thesis" className="group rounded-3xl bg-slate-900 p-7 text-white shadow-xl shadow-slate-200 transition-transform hover:-translate-y-0.5">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-white/10 text-white">
                <FlaskConical size={21} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">TENBAGGER LOOP</div>
                <h2 className="mt-1 text-2xl font-black tracking-tight">十倍股研究闭环</h2>
              </div>
            </div>
            <ArrowUpRight size={18} className="text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </div>
          <p className="mt-5 max-w-2xl text-sm leading-6 text-slate-300">
            新增的核心能力已经接入：把趋势线索推进到可证伪假设，再经过正式数据门控和历史信号校准。
          </p>
          <div className="mt-6 grid grid-cols-3 gap-4">
            <LoopStat label="假设数" value={thesisSummary?.count ?? 0} dark />
            <LoopStat label="候选" value={thesisSummary?.candidate_count ?? 0} dark />
            <LoopStat label="阻断" value={thesisSummary?.blocked_count ?? 0} dark danger={(thesisSummary?.blocked_count ?? 0) > 0} />
          </div>
        </Link>

        <Link href="/research/data-quality" className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-100">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
                <ShieldCheck size={21} />
              </div>
              <div>
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">DATA GATE</div>
                <h2 className="mt-1 text-xl font-black text-slate-900">正式研究门控</h2>
              </div>
            </div>
            <StatusIndicator status={gateStatus} />
          </div>
          <div className="mt-6 grid grid-cols-2 gap-4">
            <LoopStat label="可正式研究" value={`${formalReadyPct}%`} />
            <LoopStat label="PASS / WARN / FAIL" value={`${gateSummary?.pass_count ?? 0}/${gateSummary?.warn_count ?? 0}/${gateSummary?.fail_count ?? 0}`} danger={(gateSummary?.fail_count ?? 0) > 0} />
          </div>
          <p className="mt-4 text-xs leading-5 text-slate-500">mock、fallback、低信源置信和财务缺口会被拦截，避免把线索误当结论。</p>
        </Link>

        <Link href="/research/backtest" className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm transition-transform hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-100">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
              <BarChart3 size={21} />
            </div>
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">SIGNAL CALIBRATION</div>
              <h2 className="mt-1 text-xl font-black text-slate-900">信号回测校准</h2>
            </div>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-4">
            <LoopStat label="样本" value={latestBacktest?.sample_count ?? 0} />
            <LoopStat label="周期" value={`${latestBacktest?.horizon_days ?? 0}D`} />
            <LoopStat label="2x" value={pct(latestBacktest?.hit_rate_2x ?? 0)} />
          </div>
          <p className="mt-4 text-xs leading-5 text-slate-500">{latestBacktest?.explanation || "暂无回测样本时，可进入校准页运行短周期或等待未来行情补齐。"}</p>
        </Link>
      </section>

      {/* Quick Nav */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        <PanelLink icon={<Share2 size={20} />} title="AI大图谱" href="/research/ai-big-graph" text="看产业空间与链路结构" />
        <PanelLink icon={<Radar size={20} />} title="趋势雷达" href="/trend" text="看趋势、强度与买点线索" />
        <PanelLink icon={<Crosshair size={20} />} title="逻辑狙击" href="/research/thesis" text="门控、反证与TAM模拟" />
        <PanelLink icon={<ClipboardCheck size={20} />} title="研究任务" href="/research" text="每日待验证事项清单" />
        <PanelLink icon={<ShieldCheck size={20} />} title="数据门控" href="/research/data-quality" text="正式研究准入状态" />
        <PanelLink icon={<FileText size={20} />} title="投研简报" href="/report" text="日报与关键变化回看" />
      </section>

      {/* Main Grid Content */}
      <div className="grid gap-6 lg:grid-cols-[1fr_0.8fr]">
        
        {/* Left Column */}
        <div className="space-y-6">
          {/* Watchlist Changes */}
          <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                   <Repeat2 size={14} /> 
                   WATCHLIST TRACKING
                </div>
                <h2 className="text-xl font-bold text-slate-900">观察池核心变动</h2>
              </div>
              <Link href="/watchlist" className="text-[12px] font-bold text-indigo-600 hover:underline">查看复盘详情</Link>
            </div>
            
            <div className="mt-6 flex items-center gap-4 bg-slate-50 p-4 rounded-2xl border border-slate-100">
              <div className="px-3 py-1 bg-white border border-slate-200 rounded-lg text-[11px] font-bold text-slate-500">
                {watchlistChanges?.previous_date?.split('-').slice(1).join('/') || "PREV"}
              </div>
              <ArrowRight size={14} className="text-slate-300" />
              <div className="px-3 py-1 bg-indigo-50 border border-indigo-100 rounded-lg text-[11px] font-bold text-indigo-600">
                {watchlistChanges?.latest_date?.split('-').slice(1).join('/') || "LATEST"}
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-4">
              <MetricMini label="当前观察" value={watchlistChanges?.summary.latest_watch_count ?? 0} />
              <MetricMini label="新进标的" value={watchlistChanges?.summary.new_count ?? 0} variant="success" />
              <MetricMini label="移出标的" value={watchlistChanges?.summary.removed_count ?? 0} variant="danger" />
              <MetricMini label="评级调整" value={(watchlistChanges?.summary.upgraded_count ?? 0) + (watchlistChanges?.summary.downgraded_count ?? 0)} />
            </div>

            <div className="mt-8 grid gap-6 md:grid-cols-2">
              <div className="space-y-4">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">NEW ENTRIES / 新进观察</p>
                <div className="space-y-2">
                  {watchlistChanges?.new_entries.slice(0, 4).map(row => (
                    <StockRowSmall key={row.code} row={row} />
                  ))}
                  {(!watchlistChanges || watchlistChanges.new_entries.length === 0) && <EmptyState text="今日无新进标的" />}
                </div>
              </div>
              <div className="space-y-4">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">SCORE GAINERS / 评分上升</p>
                <div className="space-y-2">
                  {watchlistChanges?.score_gainers.slice(0, 4).map(row => (
                    <StockRowSmall key={row.code} row={row} showDelta />
                  ))}
                  {(!watchlistChanges || watchlistChanges.score_gainers.length === 0) && <EmptyState text="今日无明显评分上升" />}
                </div>
              </div>
            </div>
          </section>

          {/* Universe & Eligibility */}
          <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
             <div className="flex items-start justify-between mb-8">
              <div>
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                   <Target size={14} /> 
                   RESEARCH UNIVERSE
                </div>
                <h2 className="text-xl font-bold text-slate-900">研究股票池准入</h2>
                <p className="mt-2 text-sm text-slate-500">系统已自动过滤 ST、低流动性、极低市值及次新噪声，确保研究基数的有效性。</p>
              </div>
            </div>
            
            <div className="grid gap-4 md:grid-cols-4">
              <MetricCard label="全市场总数" value={researchUniverse?.summary.stock_count ?? "-"} />
              <MetricCard label="可研究标的" value={researchUniverse?.summary.eligible_count ?? "-"} highlight />
              <MetricCard label="排除标的" value={researchUniverse?.summary.excluded_count ?? "-"} />
              <MetricCard label="准入效率" value={researchUniverse ? `${Math.round(researchUniverse.summary.eligible_ratio * 100)}%` : "-"} />
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-3">
               {researchUniverse?.segments.map(segment => (
                 <div key={`${segment.market}-${segment.board}`} className="rounded-2xl border border-slate-100 bg-slate-50/50 p-4 transition-colors hover:border-indigo-100 hover:bg-white">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900">{marketLabel(segment.market)}</span>
                      <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">{boardLabel(segment.board)}</span>
                    </div>
                    <div className="mt-3 flex items-baseline gap-2">
                      <span className="text-xl font-bold text-slate-900 tracking-tight">{segment.eligible_count}</span>
                      <span className="text-[10px] font-bold text-slate-400">/ {segment.stock_count}</span>
                    </div>
                    <div className="mt-3 h-1 w-full bg-slate-200 rounded-full overflow-hidden">
                       <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${segment.eligible_ratio * 100}%` }} />
                    </div>
                 </div>
               ))}
               {!researchUniverse && (
                 <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-sm font-medium text-slate-400 md:col-span-3">
                   股票池准入明细正在等待数据状态接口返回
                 </div>
               )}
            </div>
          </section>
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Top Industries */}
          <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
            <div className="flex items-center justify-between mb-6">
               <h2 className="text-xl font-bold text-slate-900">今日活跃赛道</h2>
               <Link href="/industry" className="text-[12px] font-bold text-indigo-600 hover:underline">全部</Link>
            </div>
            <div className="space-y-5">
              {industries.slice(0, 6).map((row) => (
                <div key={row.industry_id} className="group flex items-center justify-between gap-4 p-2 -m-2 rounded-2xl hover:bg-slate-50 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-slate-900 truncate">{row.name}</div>
                    <div className="mt-1 flex items-center gap-2">
                       <span className={`px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest ${evidenceStatusClass(row)}`}>
                        {evidenceStatusLabel(row)}
                       </span>
                       <span className="text-[10px] text-slate-400 font-medium truncate">{row.top_keywords.slice(0, 2).join(' / ')}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-xs font-black text-indigo-600 tabular-nums">{row.heat_score.toFixed(1)}</div>
                    <div className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">HEAT SCORE</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Data Quality & Status */}
          <section className="rounded-3xl bg-slate-900 p-8 text-white shadow-xl shadow-slate-200/50">
             <div className="flex items-center justify-between mb-6">
               <div>
                 <p className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">DATA INTEGRITY</p>
                 <h2 className="text-xl font-bold mt-1">引擎与数据状态</h2>
               </div>
               <StatusIndicator status={dataQuality?.status ?? "WARN"} />
             </div>

             <div className="space-y-4">
                {latestRun && (
                  <div className="rounded-2xl bg-white/5 border border-white/10 p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-300">最新批次: {latestRun.job_name}</span>
                      <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">{latestRun.status}</span>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-4 text-[11px] font-medium text-slate-400">
                      <div>写入行数: <span className="text-white ml-1">{latestRun.rows_inserted}</span></div>
                      <div>信源置信: <span className="text-white ml-1">{Math.round((latestRun.source_confidence ?? 0) * 100)}%</span></div>
                    </div>
                  </div>
                )}
                
                <div className="grid grid-cols-2 gap-3">
                  {dataStatus?.coverage.slice(0, 4).map(row => (
                    <div key={`${row.market}-${row.board}`} className="rounded-xl bg-white/5 p-3">
                      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{marketLabel(row.market)}</div>
                      <div className="mt-1 text-sm font-bold text-white">{Math.round(row.coverage_ratio * 100)}% <span className="text-[10px] text-slate-500 ml-1">Coverage</span></div>
                    </div>
                  ))}
                </div>
             </div>
             
             <div className="mt-8 pt-8 border-t border-white/10 flex items-center justify-between">
                <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">BACKFILL QUEUE</div>
                <div className="flex items-center gap-4 text-xs font-bold text-slate-300">
                  <span className="flex items-center gap-1.5"><div className="h-1.5 w-1.5 rounded-full bg-indigo-500" /> {runningTasks}</span>
                  <span className="flex items-center gap-1.5"><div className="h-1.5 w-1.5 rounded-full bg-slate-600" /> {queuedTasks}</span>
                </div>
             </div>
          </section>
        </div>
      </div>

      {/* Full Width Section: Trend Stocks */}
      <section className="rounded-3xl bg-white border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-8 border-b border-slate-100 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
               <TrendingUp size={14} /> 
               MOMENTUM RADAR
            </div>
            <h2 className="text-2xl font-bold text-slate-900">趋势增强观察标的</h2>
          </div>
          <Link href="/trend" className="inline-flex items-center gap-2 rounded-xl bg-slate-50 px-4 py-2 text-sm font-bold text-slate-900 hover:bg-slate-100 transition-colors">
            进入完整分析 <ArrowUpRight size={16} />
          </Link>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] text-left border-collapse">
            <thead className="bg-slate-50/50">
              <tr>
                <th className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">股票 / 代码</th>
                <th className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">市场分区</th>
                <th className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">所属产业</th>
                <th className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">综合评分</th>
                <th className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">量价趋势</th>
                <th className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400">证据链核验</th>
                <th className="px-8 py-4 text-[10px] font-black uppercase tracking-widest text-slate-400 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {topStocks.map((row) => (
                <tr key={row.code} className="group hover:bg-slate-50 transition-colors">
                  <td className="px-8 py-5">
                    <div className="flex flex-col">
                      <span className="text-[14px] font-bold text-slate-900">{row.name}</span>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">{row.code}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <div className="flex flex-col">
                      <span className="text-[13px] font-bold text-slate-700">{marketLabel(row.market)}</span>
                      <span className="text-[11px] font-medium text-slate-400 mt-1">{boardLabel(row.board)}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <span className="text-[13px] font-bold text-slate-700">{row.industry}</span>
                  </td>
                  <td className="px-8 py-5">
                    <ScoreBadge score={row.final_score} rating={row.rating} />
                  </td>
                  <td className="px-8 py-5">
                    <div className="flex items-center gap-3">
                       <div className="flex-1 h-1.5 w-16 bg-slate-100 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${row.trend_score > 60 ? 'bg-orange-500' : 'bg-slate-300'}`} style={{ width: `${Math.min(100, row.trend_score)}%` }} />
                       </div>
                       <span className="text-[13px] font-black text-slate-900 tabular-nums">{row.trend_score.toFixed(1)}</span>
                    </div>
                  </td>
                  <td className="px-8 py-5">
                    <div className="flex flex-wrap gap-1.5">
                       <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-50 text-indigo-600 border border-indigo-100/50">
                         {row.confidence?.level || "NORMAL"}
                       </span>
                       <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-500">
                         CONF: {Math.round((row.confidence?.combined_confidence || 0) * 100)}%
                       </span>
                    </div>
                  </td>
                  <td className="px-8 py-5 text-right">
                    <Link 
                      href={`/stocks/${encodeURIComponent(row.code)}?from=/`} 
                      className="inline-flex h-8 items-center justify-center rounded-lg bg-indigo-600 px-4 text-[11px] font-bold text-white shadow-lg shadow-indigo-100 transition-transform hover:scale-105 active:scale-95"
                    >
                      查看证据链
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// Sub-components for better organization

function Metric({ label, value, unit, highlight = false }: { label: string; value: string | number; unit: string; highlight?: boolean }) {
  return (
    <div className={`rounded-2xl border border-slate-100 p-5 ${highlight ? 'bg-indigo-50/30' : 'bg-slate-50/50'}`}>
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className={`text-2xl font-bold tracking-tight ${highlight ? 'text-indigo-600' : 'text-slate-900'}`}>{value}</span>
        <span className="text-[10px] font-bold text-slate-400">{unit}</span>
      </div>
    </div>
  );
}

function MetricMini({ label, value, variant = "default" }: { label: string; value: number | string, variant?: "default" | "success" | "danger" }) {
  const colors = {
    default: "text-slate-900 bg-white",
    success: "text-red-600 bg-red-50/50", // In finance, red is often used for increase/success in China
    danger: "text-emerald-600 bg-emerald-50/50"
  };
  
  return (
    <div className={`rounded-xl border border-slate-100 p-3 flex flex-col items-center justify-center text-center`}>
      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-2 text-lg font-bold tabular-nums ${colors[variant].split(' ')[0]}`}>{value}</div>
    </div>
  );
}

function MetricCard({ label, value, highlight = false }: { label: string; value: string | number; highlight?: boolean }) {
  return (
    <div className={`p-4 rounded-2xl border ${highlight ? 'border-indigo-100 bg-indigo-50/30 text-indigo-900' : 'border-slate-100 bg-slate-50/30 text-slate-900'}`}>
      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2">{label}</div>
      <div className="text-lg font-bold tracking-tight">{value}</div>
    </div>
  );
}

function LoopStat({ label, value, dark = false, danger = false }: { label: string; value: string | number; dark?: boolean; danger?: boolean }) {
  const valueClass = dark
    ? danger ? "text-rose-300" : "text-white"
    : danger ? "text-rose-600" : "text-slate-900";
  return (
    <div>
      <div className={`text-[9px] font-black uppercase tracking-widest ${dark ? "text-slate-500" : "text-slate-400"}`}>{label}</div>
      <div className={`mt-1 text-lg font-black tabular-nums ${valueClass}`}>{value}</div>
    </div>
  );
}

function PanelLink({ icon, title, text, href }: { icon: React.ReactNode; title: string; text: string; href: string }) {
  return (
    <Link href={href} className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 transition-all duration-300 hover:border-indigo-300 hover:shadow-xl hover:shadow-indigo-50 hover:-translate-y-1">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-50 text-slate-400 group-hover:bg-indigo-600 group-hover:text-white transition-colors duration-300">
          {icon}
        </div>
        <h3 className="font-bold text-slate-900">{title}</h3>
      </div>
      <p className="mt-4 text-[12px] font-medium leading-relaxed text-slate-500 group-hover:text-slate-600 transition-colors">
        {text}
      </p>
      <div className="mt-4 flex items-center gap-1.5 text-[11px] font-bold text-indigo-600 opacity-0 group-hover:opacity-100 transition-all -translate-x-2 group-hover:translate-x-0">
        立即进入 <ArrowRight size={12} />
      </div>
    </Link>
  );
}

function StockRowSmall({ row, showDelta = false }: { row: any, showDelta?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 p-3 rounded-xl bg-white border border-slate-100 hover:border-indigo-100 transition-colors group">
      <div className="flex flex-col min-w-0">
        <div className="font-bold text-[13px] text-slate-900 truncate group-hover:text-indigo-600 transition-colors">{row.name}</div>
        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">{row.code}</div>
      </div>
      <div className="text-right shrink-0">
        <div className="text-[12px] font-black text-slate-900 tabular-nums">{row.final_score?.toFixed(1) || "-"}</div>
        {showDelta && row.score_delta !== null && (
          <div className={`text-[10px] font-bold mt-0.5 ${row.score_delta >= 0 ? 'text-red-500' : 'text-emerald-500'}`}>
            {row.score_delta > 0 ? '+' : ''}{row.score_delta.toFixed(1)}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusIndicator({ status }: { status: string }) {
  const config = {
    PASS: "bg-emerald-500 shadow-emerald-500/50",
    WARN: "bg-amber-500 shadow-amber-500/50",
    FAIL: "bg-rose-500 shadow-rose-500/50"
  };
  const color = config[status as keyof typeof config] || config.PASS;
  return (
    <div className="flex items-center gap-2">
      <div className={`h-2 w-2 rounded-full animate-pulse shadow-lg ${color}`} />
      <span className="text-[10px] font-black uppercase tracking-widest text-slate-300">{status}</span>
    </div>
  );
}

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="py-4 text-center rounded-xl border border-dashed border-slate-200">
      <p className="text-[11px] font-medium text-slate-400">{text}</p>
    </div>
  );
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
  if (status === "mapped_only") return "bg-slate-50 text-slate-500 border border-slate-100";
  return "bg-slate-50 text-slate-400 border border-slate-100";
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

function newsHeat(row: IndustryRadarRow) {
  return isFiniteNumber(row.news_heat_score) ? row.news_heat_score : (isFiniteNumber(row.global_heat_score) ? row.global_heat_score : row.heat_score);
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
