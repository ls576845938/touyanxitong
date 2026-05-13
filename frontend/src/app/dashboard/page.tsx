"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  CalendarDays,
  ClipboardCheck,
  Crosshair,
  Eye,
  FileText,
  FlaskConical,
  Info,
  Radar,
  Repeat2,
  Share2,
  ShieldCheck,
  Target,
  TrendingUp
} from "lucide-react";
import { motion } from "framer-motion";
import { api, type AnnotationSummary, type DataQuality, type DataStatus, type IndustryRadarRow, type IngestionTask, type MarketSummary, type ReportQualityPoint, type ReportSummary, type ResearchDataGate, type ResearchUniverse, type ResearchThesis, type SignalBacktestLatest, type TenbaggerThesisList, type ThesisAnalytics, type TrendPoolRow, type WatchlistChanges, type WatchlistItemEnhanced } from "@/lib/api";
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
  const [todayTheses, setTodayTheses] = useState<ResearchThesis[]>([]);
  const [pendingReviewTheses, setPendingReviewTheses] = useState<ResearchThesis[]>([]);
  const [watchlistItemsForDash, setWatchlistItemsForDash] = useState<WatchlistItemEnhanced[]>([]);
  const [thesesError, setThesesError] = useState("");
  const [analyticsData, setAnalyticsData] = useState<ThesisAnalytics | null>(null);
  const [annotationData, setAnnotationData] = useState<AnnotationSummary | null>(null);
  const [reportQualityData, setReportQualityData] = useState<ReportQualityPoint[]>([]);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
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

    // Fetch theses and watchlist items (graceful 404 handling)
    void api.fetchTheses({ source_type: "daily_report", status: "active", limit: 5 })
      .then(setTodayTheses)
      .catch(() => setThesesError("theses_unavailable"));

    void api.fetchTheses({ status: "active", limit: 20 })
      .then((allTheses) => {
        const now = new Date();
        const upcoming = allTheses.filter((t) => t.review_date && new Date(t.review_date) >= now).slice(0, 5);
        setPendingReviewTheses(upcoming.length > 0 ? upcoming : allTheses.slice(0, 3));
      })
      .catch(() => {});

    void api.fetchWatchlistItems({ status: "active", limit: 5 })
      .then(setWatchlistItemsForDash)
      .catch(() => {});

    // Fetch thesis review analytics (graceful 404 handling)
    void Promise.allSettled([
      api.fetchThesisAnalytics(),
      api.fetchAnnotationSummary(),
      api.fetchReportQualityTimeseries(),
    ]).then(([analytics, annotations, qualityPoints]) => {
      setAnalyticsData(analytics.status === "fulfilled" ? analytics.value : null);
      setAnnotationData(annotations.status === "fulfilled" ? annotations.value : null);
      setReportQualityData(qualityPoints.status === "fulfilled" ? qualityPoints.value : []);
      setAnalyticsLoading(false);
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

      {/* Research Theses & Pending Reviews */}
      <div className="grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        {/* Today's Theses */}
        <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
          <div className="flex items-start justify-between mb-6">
            <div>
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                <Info size={14} />
                TODAY'S THESES
              </div>
              <h2 className="text-xl font-bold text-slate-900">今日核心观点</h2>
            </div>
            {todayTheses.length > 0 && (
              <Link href="/watchlist" className="text-[12px] font-bold text-indigo-600 hover:underline">
                查看全部
              </Link>
            )}
          </div>
          {thesesError === "theses_unavailable" ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-6 text-center">
              <p className="text-sm font-medium text-slate-400">观点数据接口暂不可用，系统将在数据就绪后自动展示。</p>
            </div>
          ) : todayTheses.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-6 text-center">
              <p className="text-sm font-medium text-slate-400">暂无今日核心观点，启动 Agent 投研生成分析。</p>
            </div>
          ) : (
            <div className="space-y-4">
              {todayTheses.map((thesis) => (
                <ThesisCard key={thesis.id} thesis={thesis} />
              ))}
            </div>
          )}
        </section>

        {/* Pending Reviews / Watchlist Summary */}
        <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
          <div className="flex items-start justify-between mb-6">
            <div>
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                <CalendarDays size={14} />
                PENDING REVIEWS
              </div>
              <h2 className="text-xl font-bold text-slate-900">待复盘观点</h2>
            </div>
          </div>
          {pendingReviewTheses.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-6 text-center">
              <p className="text-sm font-medium text-slate-400">暂无待复盘的观点。</p>
            </div>
          ) : (
            <div className="space-y-3">
              {pendingReviewTheses.map((thesis) => (
                <PendingReviewCard key={thesis.id} thesis={thesis} />
              ))}
            </div>
          )}

          {/* Divider */}
          <div className="my-6 border-t border-slate-100" />

          {/* Watchlist Summary */}
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-4">
              <Eye size={14} />
              WATCHLIST SUMMARY
            </div>
            {watchlistItemsForDash.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-center">
                <p className="text-xs font-medium text-slate-400">观察池暂无数据。</p>
              </div>
            ) : (
              <div className="space-y-2">
                {watchlistItemsForDash.slice(0, 4).map((item) => (
                  <Link
                    key={item.id}
                    href={`/watchlist`}
                    className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-50 border border-slate-100 hover:border-indigo-100 transition-colors group"
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-bold text-slate-900 truncate group-hover:text-indigo-600 transition-colors">
                        {item.subject_name}
                      </div>
                      <div className="text-[10px] font-medium text-slate-400 mt-0.5 truncate">
                        {item.thesis_title || item.reason}
                      </div>
                    </div>
                    <span className={`shrink-0 px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider ${
                      item.priority === "S" ? "bg-rose-100 text-rose-700" :
                      item.priority === "A" ? "bg-amber-100 text-amber-700" :
                      "bg-slate-100 text-slate-600"
                    }`}>
                      {item.priority}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Thesis Review Analytics */}
      {analyticsLoading ? (
        <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
          <div className="animate-pulse">
            <div className="h-3 w-48 bg-slate-100 rounded mb-6" />
            <div className="h-5 w-32 bg-slate-100 rounded mb-8" />
            <div className="grid grid-cols-4 gap-4">
              {[1,2,3,4].map(i => <div key={i} className="h-24 bg-slate-100 rounded-2xl" />)}
            </div>
          </div>
        </section>
      ) : (
        <>
          {/* Row 1: Thesis Overview + Annotation Summary */}
          <div className="grid gap-6 lg:grid-cols-[1fr_0.4fr]">
            {/* Section 1: Thesis Review Overview */}
            <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                <ClipboardCheck size={14} />
                THESIS REVIEW ANALYTICS
              </div>
              <h2 className="text-xl font-bold text-slate-900 mb-6">观点复盘总览</h2>
              {!analyticsData ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-6 text-center">
                  <p className="text-sm font-medium text-slate-400">暂无复盘数据。</p>
                </div>
              ) : (
                <>
                  {analyticsData.sample_size < 10 && (
                    <div className="mb-4 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-[11px] font-medium text-amber-700">
                      样本不足 (N={analyticsData.sample_size})，暂不作结论
                    </div>
                  )}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 rounded-2xl border border-slate-100 bg-slate-50/30">
                      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2">已复盘</div>
                      <div className="text-lg font-bold text-slate-900">{analyticsData.sample_size}</div>
                    </div>
                    <div className="p-4 rounded-2xl border border-emerald-100 bg-emerald-50/30">
                      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2">命中率</div>
                      <div className="text-lg font-bold text-emerald-600">{pct(analyticsData.hit_rate ?? 0)}</div>
                    </div>
                    <div className="p-4 rounded-2xl border border-rose-100 bg-rose-50/30">
                      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2">错失率</div>
                      <div className="text-lg font-bold text-rose-600">{pct(analyticsData.miss_rate ?? 0)}</div>
                    </div>
                    <div className="p-4 rounded-2xl border border-amber-100 bg-amber-50/30">
                      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-2">不确定率</div>
                      <div className="text-lg font-bold text-amber-600">{pct(analyticsData.inconclusive_rate ?? 0)}</div>
                    </div>
                  </div>
                </>
              )}
            </section>

            {/* Section 5: Annotation Summary */}
            <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                <Info size={14} />
                ANNOTATIONS
              </div>
              <h2 className="text-xl font-bold text-slate-900 mb-6">标注统计</h2>
              {!annotationData ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 py-6 text-center">
                  <p className="text-sm font-medium text-slate-400">暂无标注。</p>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">总标注</div>
                    <div className="text-2xl font-black text-slate-900">{annotationData.total}</div>
                  </div>
                  <div className="space-y-2">
                    <AnnotationStat label="有用率" value={annotationData.useful_rate} color="emerald" />
                    <AnnotationStat label="证据弱率" value={annotationData.evidence_weak_rate} color="amber" />
                    <AnnotationStat label="模糊率" value={annotationData.too_vague_rate} color="rose" />
                  </div>
                </div>
              )}
            </section>
          </div>

          {/* Row 2: Calibration + Best/Worst (only if analytics data exists) */}
          {analyticsData && (
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
              {/* Section 2: Confidence Calibration */}
              <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                  <BarChart3 size={14} />
                  CALIBRATION
                </div>
                <h2 className="text-xl font-bold text-slate-900 mb-6">置信度校准</h2>
                {(() => {
                  const buckets: CalibrationBucket[] = parseJsonField<CalibrationBucket[]>(analyticsData.calibration_report_json) || [];
                  if (buckets.length === 0) {
                    return (
                      <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 py-6 text-center">
                        <p className="text-sm font-medium text-slate-400">暂无校准数据。</p>
                      </div>
                    );
                  }
                  return (
                    <div className="space-y-5">
                      {buckets.map((b, i) => (
                        <div key={i}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[11px] font-bold text-slate-600">{b.bucket}</span>
                            <span className="text-[10px] font-bold text-slate-400">N={b.sample_size}</span>
                          </div>
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="text-[9px] font-medium text-indigo-400 w-12 shrink-0">预期</span>
                              <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-200 rounded-full transition-all" style={{ width: `${Math.min(100, (b.confidence_mid ?? 0) * 100)}%` }} />
                              </div>
                              <span className="text-[9px] font-bold text-indigo-400 w-10 text-right">{(b.confidence_mid ?? 0) * 100}%</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-[9px] font-medium text-indigo-600 w-12 shrink-0">实际</span>
                              <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-600 rounded-full transition-all" style={{ width: `${Math.min(100, (b.actual_hit_rate ?? 0) * 100)}%` }} />
                              </div>
                              <span className="text-[9px] font-bold text-indigo-600 w-10 text-right">{(b.actual_hit_rate ?? 0) * 100}%</span>
                            </div>
                          </div>
                          <div className="mt-1 flex justify-end">
                            <CalibrationGap gap={b.gap} />
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </section>

              {/* Section 3: Best/Worst Groups */}
              <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
                <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
                  <Target size={14} />
                  GROUP PERFORMANCE
                </div>
                <h2 className="text-xl font-bold text-slate-900 mb-6">分群表现</h2>
                <div className="space-y-6">
                  {parseGroupsSummary(analyticsData).map((group, i) => (
                    <div key={i}>
                      <div className="text-[11px] font-black uppercase tracking-widest text-slate-400 mb-2">{group.label}</div>
                      <div className="space-y-1">
                        {group.items.length > 0 ? group.items.map((item, j) => (
                          <GroupRow key={j} item={item} />
                        )) : (
                          <div className="text-[11px] font-medium text-slate-400 py-1">暂无数据</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}

          {/* Section 4: Report Quality Trend */}
          <section className="rounded-3xl bg-white border border-slate-200 p-8 shadow-sm">
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
              <TrendingUp size={14} />
              REPORT QUALITY TREND
            </div>
            <h2 className="text-xl font-bold text-slate-900 mb-6">日报质量趋势</h2>
            {reportQualityData.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-6 text-center">
                <p className="text-sm font-medium text-slate-400">暂无质量趋势数据。</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="text-[9px] font-black uppercase tracking-widest text-slate-400">
                      <th className="pb-3 pr-4">日期</th>
                      <th className="pb-3 pr-4">质量评分</th>
                      <th className="pb-3 pr-4">观点数</th>
                      <th className="pb-3 pr-4">证据数</th>
                      <th className="pb-3 pr-4">平均置信</th>
                      <th className="pb-3 pr-4">5日命中</th>
                      <th className="pb-3 pr-4">20日命中</th>
                      <th className="pb-3 pr-4">状态</th>
                      <th className="pb-3">趋势</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {reportQualityData.slice(0, 10).map((point, idx, arr) => (
                      <tr key={point.score_date} className="text-[13px] text-slate-900 font-medium">
                        <td className="py-3 pr-4 text-slate-500">{point.score_date}</td>
                        <td className="py-3 pr-4 font-bold">{point.quality_score.toFixed(1)}</td>
                        <td className="py-3 pr-4">{point.thesis_count}</td>
                        <td className="py-3 pr-4">{point.evidence_count}</td>
                        <td className="py-3 pr-4">{Math.round(point.avg_confidence * 100)}%</td>
                        <td className="py-3 pr-4">{point.hit_rate_5d != null ? `${(point.hit_rate_5d * 100).toFixed(0)}%` : '-'}</td>
                        <td className="py-3 pr-4">{point.hit_rate_20d != null ? `${(point.hit_rate_20d * 100).toFixed(0)}%` : '-'}</td>
                        <td className="py-3 pr-4">
                          <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider ${
                            point.review_backed ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                          }`}>
                            {point.review_backed ? '已复盘' : '待复盘'}
                          </span>
                        </td>
                        <td className="py-3">
                          <TrendArrow
                            current={point.quality_score}
                            previous={idx < arr.length - 1 ? arr[idx + 1].quality_score : null}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {/* Anomalies */}
      {industries.filter((ind) => Math.abs(ind.heat_change_7d) > 30).length > 0 && (
        <section className="rounded-3xl bg-white border border-amber-200 p-8 shadow-sm">
          <div className="flex items-start gap-4 mb-6">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-amber-600">
              <AlertTriangle size={20} />
            </div>
            <div>
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-amber-500 mb-2">
                异常信号
              </div>
              <h2 className="text-xl font-bold text-slate-900">产业热度异常波动</h2>
              <p className="mt-1 text-sm text-slate-500">以下产业近7日热度变化超过阈值，建议重点关注。</p>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {industries
              .filter((ind) => Math.abs(ind.heat_change_7d) > 30)
              .slice(0, 8)
              .map((ind) => (
                <div key={ind.industry_id} className="rounded-2xl border border-slate-100 bg-slate-50/50 p-5">
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold text-slate-900 truncate">{ind.name}</h3>
                    <span className={`text-[11px] font-black tabular-nums ${
                      ind.heat_change_7d > 0 ? "text-rose-500" : "text-emerald-500"
                    }`}>
                      {ind.heat_change_7d > 0 ? "+" : ""}{ind.heat_change_7d.toFixed(0)}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-500">热度 {ind.heat_score.toFixed(1)}</span>
                    <span className="w-1 h-1 bg-slate-300 rounded-full" />
                    <span className="text-xs font-medium text-slate-500">{ind.related_stock_count} 只股票</span>
                  </div>
                  {ind.top_keywords.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {ind.top_keywords.slice(0, 3).map((kw) => (
                        <span key={kw} className="px-2 py-0.5 rounded bg-white border border-slate-200 text-[9px] font-bold text-slate-500">
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </section>
      )}

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

// ---------------------------------------------------------------------------
// Thesis Analytics types & helpers
// ---------------------------------------------------------------------------
interface CalibrationBucket {
  bucket: string;
  confidence_mid: number | null;
  sample_size: number;
  actual_hit_rate: number | null;
  gap: number | null;
}

interface GroupItem {
  name: string;
  hit_rate: number | null;
  sample_size: number;
}

interface GroupSummary {
  label: string;
  items: GroupItem[];
}

function parseJsonField<T>(json: string): T | null {
  try {
    return JSON.parse(json) as T;
  } catch {
    return null;
  }
}

function parseGroupsSummary(data: ThesisAnalytics): GroupSummary[] {
  const subjectTypes = parseJsonField<Array<{ subject_type: string; sample_size: number; hit_rate: number | null }>>(data.by_subject_type_json) || [];
  const horizons = parseJsonField<Array<{ horizon_days: number; sample_size: number; hit_rate: number | null }>>(data.by_horizon_json) || [];
  const sortedST = [...subjectTypes].sort((a, b) => (b.hit_rate ?? 0) - (a.hit_rate ?? 0));
  const sortedH = [...horizons].sort((a, b) => (b.hit_rate ?? 0) - (a.hit_rate ?? 0));
  const labelMap: Record<string, string> = { stock: "个股", industry: "产业", index: "指数", sector: "板块" };
  return [
    {
      label: "最佳类型",
      items: sortedST.slice(0, 2).map(s => ({ name: labelMap[s.subject_type] || s.subject_type, hit_rate: s.hit_rate, sample_size: s.sample_size })),
    },
    {
      label: "最佳周期",
      items: sortedH.slice(0, 2).map(h => ({ name: `${h.horizon_days}天`, hit_rate: h.hit_rate, sample_size: h.sample_size })),
    },
    {
      label: "最差类型",
      items: sortedST.slice(-2).reverse().map(s => ({ name: labelMap[s.subject_type] || s.subject_type, hit_rate: s.hit_rate, sample_size: s.sample_size })),
    },
  ];
}

// ---------------------------------------------------------------------------
// Thesis Analytics sub-components
// ---------------------------------------------------------------------------
function AnnotationStat({ label, value, color }: { label: string; value: number | null; color: string }) {
  const colorMap: Record<string, string> = { emerald: "text-emerald-600", amber: "text-amber-600", rose: "text-rose-600" };
  return (
    <div className="flex items-center justify-between">
      <span className="text-[11px] font-medium text-slate-500">{label}</span>
      <span className={`text-[12px] font-bold tabular-nums ${colorMap[color] || 'text-slate-900'}`}>
        {value != null ? `${(value * 100).toFixed(0)}%` : '-'}
      </span>
    </div>
  );
}

function CalibrationGap({ gap }: { gap: number | null }) {
  if (gap == null) return <span className="text-[9px] text-slate-400">--</span>;
  const isOver = gap > 0;
  return (
    <span className={`text-[9px] font-bold ${isOver ? 'text-rose-500' : 'text-emerald-500'}`}>
      {isOver ? '过度自信' : '保守'} {Math.abs(gap).toFixed(1)}%
    </span>
  );
}

function GroupRow({ item }: { item: GroupItem }) {
  return (
    <div className="flex items-center justify-between py-1">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-[12px] font-bold text-slate-900 truncate">{item.name}</span>
        <span className="text-[9px] font-medium text-slate-400 shrink-0">N={item.sample_size}</span>
      </div>
      <span className={`text-[11px] font-black tabular-nums ${(item.hit_rate ?? 0) >= 0.5 ? 'text-emerald-600' : 'text-rose-600'}`}>
        {pct(item.hit_rate ?? 0)}
      </span>
    </div>
  );
}

function TrendArrow({ current, previous }: { current: number; previous: number | null }) {
  if (previous == null) return <span className="text-slate-300">--</span>;
  if (current > previous) return <span className="text-emerald-500 text-sm">&#8593;</span>;
  if (current < previous) return <span className="text-rose-500 text-sm">&#8595;</span>;
  return <span className="text-slate-400 text-sm">&#8594;</span>;
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

function ThesisCard({ thesis }: { thesis: ResearchThesis }) {
  const [expanded, setExpanded] = useState(false);
  const directionColors: Record<string, string> = {
    positive: "bg-rose-100 text-rose-700 border-rose-200",
    negative: "bg-emerald-100 text-emerald-700 border-emerald-200",
    neutral: "bg-slate-100 text-slate-600 border-slate-200",
    mixed: "bg-amber-100 text-amber-700 border-amber-200"
  };
  const directionLabels: Record<string, string> = {
    positive: "看多",
    negative: "看空",
    neutral: "中性",
    mixed: "多空交织"
  };
  let invalidationConditions: string[] = [];
  try {
    const parsed = JSON.parse(thesis.invalidation_conditions_json);
    invalidationConditions = Array.isArray(parsed) ? parsed : typeof parsed === "string" ? [parsed] : [];
  } catch {}

  return (
    <div className="rounded-2xl border border-slate-100 bg-slate-50/30 p-5 hover:border-indigo-100 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider border ${directionColors[thesis.direction] || directionColors.neutral}`}>
              {directionLabels[thesis.direction] || thesis.direction}
            </span>
            <span className="text-[10px] font-bold text-slate-400">
              {thesis.horizon_days}天周期
            </span>
            <span className="text-[10px] font-bold text-slate-400">
              {thesis.source_type === "daily_report" ? "日报" : thesis.source_type}
            </span>
          </div>
          <h3 className="text-sm font-bold text-slate-900 leading-snug">
            {thesis.thesis_title || thesis.thesis_body?.slice(0, 120)}
          </h3>
          {thesis.subject_name && (
            <p className="mt-1 text-[11px] font-medium text-indigo-600">
              {thesis.subject_name} ({thesis.subject_id})
            </p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">置信度</div>
          <div className="text-lg font-black text-slate-900 tabular-nums">{Math.round(thesis.confidence * 100)}%</div>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mt-3 h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-indigo-500 transition-all"
          style={{ width: `${Math.round(thesis.confidence * 100)}%` }}
        />
      </div>

      {/* Invalidation conditions (collapsed) */}
      {invalidationConditions.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] font-bold text-slate-400 hover:text-slate-600 transition-colors flex items-center gap-1"
          >
            {expanded ? "收起" : "展开"}证伪条件 ({invalidationConditions.length})
          </button>
          {expanded && (
            <ul className="mt-2 space-y-1">
              {invalidationConditions.map((cond, i) => (
                <li key={i} className="text-[11px] font-medium text-slate-500 flex items-start gap-2">
                  <span className="w-1 h-1 mt-1.5 shrink-0 rounded-full bg-slate-300" />
                  {cond}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function PendingReviewCard({ thesis }: { thesis: ResearchThesis }) {
  return (
    <Link
      href={thesis.subject_type === "stock" ? `/stocks/${encodeURIComponent(thesis.subject_id)}` : "/watchlist"}
      className="block rounded-xl border border-slate-100 bg-slate-50/30 p-4 hover:border-indigo-100 hover:bg-white transition-all group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-bold text-slate-900 truncate group-hover:text-indigo-600 transition-colors">
            {thesis.thesis_title || thesis.thesis_body?.slice(0, 80)}
          </div>
          {thesis.subject_name && (
            <div className="text-[11px] font-medium text-slate-500 mt-0.5">
              {thesis.subject_name} ({thesis.subject_id})
            </div>
          )}
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1">
          {thesis.review_date && (
            <span className="text-[10px] font-bold text-amber-600 whitespace-nowrap">
              复盘日: {thesis.review_date}
            </span>
          )}
          <span className="text-[10px] font-bold text-slate-400">
            置信度 {Math.round(thesis.confidence * 100)}%
          </span>
        </div>
      </div>
    </Link>
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
