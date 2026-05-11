"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { AlertCircle, ArrowLeft, CalendarDays, ExternalLink, Flame, Hash, Newspaper, RadioTower, RefreshCcw, Map } from "lucide-react";
import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { QualityBanner } from "@/components/Workbench";
import { api, type ResearchHotIndustry, type ResearchHotTerm, type ResearchHotTerms, type ResearchHotTermsRefresh } from "@/lib/api";
import { collectQualityFlags } from "@/lib/research-workbench";

type HotWindow = "1d" | "7d";

const WINDOWS: Array<{ key: HotWindow; label: string }> = [
  { key: "1d", label: "今日" },
  { key: "7d", label: "近一周" }
];

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

export default function HotTermsPage() {
  const [windowKey, setWindowKey] = useState<HotWindow>("1d");
  const [payload, setPayload] = useState<ResearchHotTerms | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [refreshError, setRefreshError] = useState("");
  const [refreshResult, setRefreshResult] = useState<ResearchHotTermsRefresh | null>(null);

  const loadHotTerms = useCallback(async (keepCurrent = false) => {
    if (!keepCurrent) setLoading(true);
    setError("");
    const data = await api.researchHotTerms({ window: windowKey, limit: 80 });
    setPayload(data);
    if (!keepCurrent) setLoading(false);
  }, [windowKey]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api.researchHotTerms({ window: windowKey, limit: 80 })
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`热词雷达读取失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [windowKey]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshError("");
    try {
      const result = await api.refreshHotTerms({ limitPerSource: 12, timeoutSeconds: 5, window: windowKey });
      setRefreshResult(result);
      setPayload(result.snapshot);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setRefreshError(`外部热词刷新失败：${message}`);
      await loadHotTerms(true).catch(() => undefined);
    } finally {
      setRefreshing(false);
    }
  };

  const summary = useMemo(() => {
    return [
      { label: "热门板块", value: payload?.summary.industry_count ?? 0, tone: "amber" as const },
      { label: "热词数量", value: payload?.summary.term_count ?? 0, tone: "orange" as const },
      { label: "匹配文章", value: payload?.summary.matched_article_count ?? payload?.summary.article_count ?? 0, tone: "red" as const },
      { label: "活跃来源", value: payload?.summary.source_count ?? 0, tone: "amber" as const }
    ];
  }, [payload]);

  const sourceHealth = useMemo(() => {
    const sources = payload?.sources ?? [];
    const activeSources = sources.filter((source) => source.status === "active").length;
    const fallbackSources = sources.filter((source) => isFallbackSource(source)).length;
    const degradedSources = sources.filter((source) => source.status === "degraded").length;
    const errorSources = sources.filter((source) => source.status === "error" || /failed|error/i.test(source.last_run_status ?? "")).length;
    const emptySources = sources.filter((source) => source.status === "connected_empty").length;
    const healthySources = sources.filter((source) => source.status === "active" || source.status === "connected_empty" || source.status === "internal_ready").length;
    const qualityFlags = collectQualityFlags(
      payload?.summary.data_mode,
      fallbackSources > 0 ? "FALLBACK" : undefined,
      errorSources > 0 ? "FAIL" : undefined,
      payload?.summary.is_stale ? "STALE" : undefined
    );

    return {
      activeSources,
      fallbackSources,
      degradedSources,
      errorSources,
      emptySources,
      healthySources,
      qualityFlags,
    };
  }, [payload]);

  const dataModeLabel = useMemo(() => {
    const raw = payload?.summary.data_mode ?? "";
    if (!raw) return "未知";
    return raw
      .split(/[_\s-]+/)
      .filter(Boolean)
      .map((item) => item.toUpperCase())
      .join(" / ");
  }, [payload?.summary.data_mode]);

  const qualityLabel = useMemo(() => {
    if (sourceHealth.errorSources > 0) return "FAIL";
    if (sourceHealth.fallbackSources > 0 || sourceHealth.degradedSources > 0) return "FALLBACK";
    if (payload?.summary.is_stale) return "STALE";
    if (sourceHealth.emptySources > 0) return "EMPTY";
    return "LIVE";
  }, [payload?.summary.is_stale, sourceHealth.degradedSources, sourceHealth.emptySources, sourceHealth.errorSources, sourceHealth.fallbackSources]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载资讯平台热词雷达" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;
  if (!payload) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message="热词雷达数据为空" /></div>;

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
            <Link href="/research" className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400 transition-colors hover:text-slate-700">
              <ArrowLeft size={14} />
              <span>研究中心</span>
            </Link>
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Trend Analysis</div>
            <h1 className="text-4xl font-bold tracking-tight text-slate-900">资讯平台热词雷达</h1>
            <p className="max-w-2xl text-base text-slate-500">
              聚合雪球、Reddit、同花顺、东方财富、淘股吧、盈透、华尔街日报、Reuters、CNBC、MarketWatch、Barrons、Investing.com 和本地产业热度，整理研究线索与来源状态，不输出投资建议。
            </p>
            <p className="text-xs font-medium leading-5 text-slate-400">
              这里展示的是研究辅助信号，产业相关性只表示文本和资讯映射关系，不等于买入或卖出结论。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link 
              href="/industry/chain" 
              className="flex h-12 items-center gap-3 rounded-2xl bg-white px-6 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-slate-200 transition-all hover:bg-slate-50"
            >
              <Map size={18} className="text-indigo-600" /> 
              <span>产业链地图</span>
            </Link>
            <Link 
              href="/research/brief" 
              className="flex h-12 items-center gap-3 rounded-2xl bg-white px-6 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-slate-200 transition-all hover:bg-slate-50"
            >
              <Newspaper size={18} className="text-slate-400" /> 
              <span>每日工作单</span>
            </Link>
          </div>
        </motion.section>

        {/* Time Window Selector */}
        <motion.section variants={item} className="flex flex-wrap items-center justify-between gap-4 rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
          <div className="flex gap-2">
            {WINDOWS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setWindowKey(item.key)}
                className={`h-10 rounded-xl px-6 text-sm font-bold transition-all ${
                  windowKey === item.key 
                    ? "bg-slate-900 text-white shadow-lg shadow-slate-200" 
                    : "text-slate-500 hover:bg-slate-50"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3 px-2">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-indigo-600 px-4 text-xs font-black uppercase tracking-widest text-white shadow-sm transition-all hover:bg-indigo-700 disabled:cursor-wait disabled:bg-indigo-300"
            >
              <RefreshCcw size={14} className={refreshing ? "animate-spin" : ""} />
              <span>{refreshing ? "刷新中" : "刷新外部源"}</span>
            </button>
            {refreshResult && (
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                +{refreshResult.inserted} / 跳过 {refreshResult.skipped} / 失败 {refreshResult.failed_sources}
              </div>
            )}
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              Snapshot: {payload.latest_date ?? "-"}
            </div>
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">
              Updated: {formatShortDate(payload.updated_at)}
            </div>
          </div>
        </motion.section>

        {qualityLabel === "FALLBACK" || qualityLabel === "FAIL" ? (
          <QualityBanner
            flags={sourceHealth.qualityFlags}
            fallbackLabel={`数据模式 ${dataModeLabel} · 质量状态 ${qualityLabel} · 来源健康 ${sourceHealth.activeSources}/${payload.sources.length} active`}
          />
        ) : null}

        <motion.section variants={item} className="grid gap-4 rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 md:grid-cols-2 xl:grid-cols-4">
          <QualityFact label="数据模式" value={dataModeLabel} detail="由后端 snapshot 返回，页面只做可视化。"/>
          <QualityFact label="质量标记" value={qualityLabel} detail={qualityNote(qualityLabel)} tone={qualityTone(qualityLabel)} />
          <QualityFact label="来源健康" value={`${sourceHealth.activeSources}/${payload.sources.length}`} detail={`healthy ${sourceHealth.healthySources} · fallback ${sourceHealth.fallbackSources} · empty ${sourceHealth.emptySources}`} />
          <QualityFact label="数据新鲜度" value={payload.summary.data_lag_days ?? "-"} detail={payload.summary.is_stale ? "数据日期落后当前日期，热词只能作为历史线索复核。" : "数据日期与当前日期一致。"} tone={payload.summary.is_stale ? "warn" : "pass"} />
          <QualityFact
            label="匹配文章"
            value={payload.summary.matched_article_count ?? payload.summary.article_count ?? 0}
            detail={`已过滤 ${payload.summary.unmatched_article_count ?? 0} 条无产业证据资讯，只表示关键词命中。`}
          />
        </motion.section>

        {refreshError && (
          <motion.div variants={item} className="flex items-start gap-2 rounded-2xl bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 ring-1 ring-rose-100">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{refreshError}</span>
          </motion.div>
        )}

        {/* Summary Metrics */}
        <motion.section variants={item} className="grid gap-4 grid-cols-2 md:grid-cols-4">
          {summary.map((item) => (
            <Metric key={item.label} label={item.label} value={item.value} tone={item.tone} />
          ))}
        </motion.section>

        {/* Source Status */}
        <motion.section variants={item} className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="mb-6 flex items-center gap-2 px-2">
            <RadioTower size={16} className="text-indigo-600" />
            <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500">数据源实时状态</h2>
          </div>
          <div className="mb-5 grid gap-3 md:grid-cols-4">
            <StatChip label="active" value={sourceHealth.activeSources} tone="emerald" />
            <StatChip label="degraded" value={sourceHealth.degradedSources} tone="amber" />
            <StatChip label="error" value={sourceHealth.errorSources} tone="rose" />
            <StatChip label="connected_empty" value={sourceHealth.emptySources} tone="sky" />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
            {payload.sources.map((source) => (
              <div key={source.key} className="group rounded-2xl bg-slate-50 p-4 transition-all hover:bg-white hover:shadow-lg hover:shadow-slate-200/50 ring-1 ring-inset ring-slate-100/50 hover:ring-slate-200">
                <div className="text-xs font-bold text-slate-900">{source.label}</div>
                <div className="mt-3">
                  <span className={`rounded-lg px-2 py-0.5 text-[9px] font-black uppercase tracking-widest ${sourceStatusClass(source.status)}`}>
                    {sourceStatusLabel(source.status)}
                  </span>
                </div>
                <div className="mt-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
                  {sourceStateNote(source)}
                </div>
                <div className="mt-4 text-[10px] font-black text-slate-400 group-hover:text-indigo-600 transition-colors">{source.article_count} 入库</div>
                {source.last_run_at && (
                  <div className="mt-1 text-[10px] font-bold text-slate-400">
                    {formatShortDate(source.last_run_at)} / {source.connector_item_count ?? 0}
                  </div>
                )}
                {source.connector_item_count ? (
                  <div className="mt-2 space-y-1 rounded-xl bg-white/70 p-2 text-[10px] font-bold leading-4 text-slate-500 ring-1 ring-slate-100">
                    <div>入库 {source.last_inserted ?? 0} · 跳过 {source.last_skipped ?? 0} · 过滤 {source.last_irrelevant ?? 0}</div>
                    <div>产业相关率 {formatPercent(source.relevance_rate)}</div>
                  </div>
                ) : null}
                {source.last_run_status && (
                  <div className="mt-1 text-[10px] font-bold text-slate-400">run: {source.last_run_status}</div>
                )}
                {(source.connector_status || source.window_data_status) && (
                  <div className="mt-1 text-[10px] font-bold text-slate-400">
                    connector {source.connector_status ?? "-"} · window {source.window_data_status ?? "-"}
                  </div>
                )}
                {source.last_error && (
                  <div className="mt-2 line-clamp-2 text-[10px] font-medium leading-relaxed text-rose-600">{source.last_error}</div>
                )}
              </div>
            ))}
          </div>
        </motion.section>

        {/* Main Content Grid */}
        <motion.section variants={item} className="grid gap-8 xl:grid-cols-[1.1fr_0.9fr]">
          <Panel title="热门产业板块" icon={<CalendarDays size={18} />} count={payload.hot_industries.length} subtitle="只看相关性和证据密度，不把热度写成结论。">
            <div className="grid gap-4">
              {payload.hot_industries.slice(0, 14).map((item) => (
                <IndustryRow key={item.industry} item={item} />
              ))}
              {payload.hot_industries.length === 0 && <EmptyHint label="当前窗口暂无热门产业板块" />}
            </div>
          </Panel>

          <Panel title="平台高频热词" icon={<Hash size={18} />} count={payload.hot_terms.length} subtitle="热词不是建议，只有产业相关性和来源命中。">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
              {payload.hot_terms.slice(0, 20).map((item) => (
                <TermCard key={item.term} item={item} />
              ))}
              {payload.hot_terms.length === 0 && <EmptyHint label="当前窗口暂无平台热词" />}
            </div>
          </Panel>
        </motion.section>

        {/* Platform Matrix */}
        <motion.section variants={item} className="rounded-3xl bg-white p-8 shadow-sm ring-1 ring-slate-200">
          <div className="mb-8 flex items-center gap-3">
            <Flame size={20} className="text-orange-500" />
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">分平台热词矩阵</h2>
          </div>
          {refreshResult && (
            <div className="mb-6 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">刷新摘要</div>
                  <div className="mt-1 text-sm font-semibold text-slate-700">
                    {refreshResult.status} · inserted {refreshResult.inserted} · skipped {refreshResult.skipped} · filtered {sumIrrelevant(refreshResult)} · failed {refreshResult.failed_sources}
                  </div>
                </div>
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                  来源数 {refreshResult.source_count}
                </div>
              </div>
              {refreshResult.sources.some((source) => source.error) && (
                <div className="mt-4 space-y-2">
                  {refreshResult.sources.filter((source) => source.error).map((source) => (
                    <div key={source.key} className="rounded-xl bg-white px-4 py-3 text-sm text-slate-700 ring-1 ring-slate-200">
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-bold text-slate-900">{source.label}</div>
                        <span className={`rounded-lg px-2 py-0.5 text-[9px] font-black uppercase tracking-widest ${source.status === "failed" ? "bg-rose-50 text-rose-700 ring-1 ring-rose-100" : "bg-amber-50 text-amber-700 ring-1 ring-amber-100"}`}>
                          {source.status}
                        </span>
                      </div>
                      <div className="mt-1 text-xs leading-5 text-rose-600">{source.error}</div>
                      <div className="mt-1 text-[10px] font-black uppercase tracking-widest text-slate-400">
                        fetched {source.fetched} · inserted {source.inserted} · skipped {source.skipped} · filtered {source.irrelevant ?? 0}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {payload.platform_terms.map((source) => (
              <div key={source.key} className="flex flex-col rounded-3xl bg-slate-50 p-6 ring-1 ring-inset ring-slate-100">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="text-base font-bold text-slate-900 leading-tight">{source.label}</div>
                    <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 mt-1">{source.kind}</div>
                  </div>
                  <span className={`rounded-lg px-2 py-0.5 text-[9px] font-black uppercase tracking-widest ${sourceStatusClass(source.status)}`}>
                    {sourceStatusLabel(source.status)}
                  </span>
                </div>
                <div className="text-xs font-semibold leading-5 text-slate-600">
                  <span className="font-black text-slate-900">{source.terms.length}</span> 个热词，展示产业相关性和平台覆盖，不把单条热词当成结论。
                </div>
                <div className="flex flex-wrap gap-1.5 mt-4">
                  {source.terms.length ? source.terms.slice(0, 10).map((term) => (
                    <span key={term.term} className="rounded-lg bg-white px-2.5 py-1 text-[11px] font-bold text-slate-600 shadow-sm ring-1 ring-slate-100">
                      {term.term}
                    </span>
                  )) : <span className="text-[11px] font-bold text-slate-400 italic">暂无入库热词</span>}
                </div>
              </div>
            ))}
          </div>
        </motion.section>
      </motion.div>
    </div>
  );
}

function Panel({ title, icon, count, subtitle, children }: { title: string; icon: ReactNode; count: number; subtitle?: string; children: ReactNode }) {
  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between px-2">
        <div className="flex items-center gap-3">
          <div className="text-slate-400">{icon}</div>
          <div>
            <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500">{title}</h2>
            {subtitle ? <div className="mt-1 text-[11px] leading-5 text-slate-400">{subtitle}</div> : null}
          </div>
        </div>
        <div className="text-sm font-black text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-lg">{count}</div>
      </div>
      {children}
    </section>
  );
}

function IndustryRow({ item }: { item: ResearchHotIndustry }) {
  const color = heatColor(item.intensity);
  return (
    <article className="group rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 transition-all hover:shadow-xl hover:shadow-slate-200/50">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="text-xl font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">{item.industry}</div>
          <div className="mt-1 text-[10px] font-black uppercase tracking-widest text-slate-400">
            产业相关性 {item.mentions} · {formatShortDate(item.latest_at)}
          </div>
        </div>
        <div className="text-2xl font-black italic tracking-tighter" style={{ color }}>
          {item.score.toFixed(1)}
        </div>
      </div>
      
      <div className="relative h-2 rounded-full bg-slate-100 overflow-hidden">
        <motion.div 
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(item.intensity * 100, 4)}%` }}
          className="h-full rounded-full" 
          style={{ backgroundColor: color }} 
        />
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        {item.top_terms.slice(0, 5).map((term) => (
          <span key={term.term} className="rounded-lg bg-slate-50 px-3 py-1 text-[11px] font-bold text-slate-600 ring-1 ring-slate-100">
            {term.term} · {term.score.toFixed(1)}
          </span>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap gap-1.5 border-t border-slate-50 pt-4">
        {item.sources.slice(0, 4).map((source) => (
          <span key={source.key} className="rounded-lg bg-indigo-50/50 px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-indigo-700">
            {source.label} {source.count}
          </span>
        ))}
      </div>
    </article>
  );
}

function TermCard({ item }: { item: ResearchHotTerm }) {
  const color = heatColor(item.intensity);
  return (
    <article className="group rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 transition-all hover:shadow-xl hover:shadow-slate-200/50">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="text-lg font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">{item.term}</div>
          <div className="mt-1 text-[10px] font-black uppercase tracking-widest text-slate-400">
            产业相关性 {item.industries.length} · {item.mentions} mentions
          </div>
        </div>
        <div className="text-xl font-black italic" style={{ color }}>
          {item.score.toFixed(1)}
        </div>
      </div>
      
      <div className="relative h-1.5 rounded-full bg-slate-100 overflow-hidden mb-5">
        <motion.div 
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(item.intensity * 100, 4)}%` }}
          className="h-full rounded-full" 
          style={{ backgroundColor: color }} 
        />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {item.industries.slice(0, 3).map((industry) => (
          <span key={industry.key} className="rounded-lg bg-slate-50 px-2 py-0.5 text-[10px] font-bold text-slate-500 ring-1 ring-slate-100">
            {industry.label} · {industry.count}
          </span>
        ))}
      </div>
      {item.examples.length > 0 && (
        <div className="mt-5 space-y-2 border-t border-slate-50 pt-4">
          {item.examples.slice(0, 2).map((example, index) => (
            <ExamplePreview key={`${example.url ?? example.title}-${index}`} example={example} />
          ))}
        </div>
      )}
    </article>
  );
}

function ExamplePreview({ example }: { example: ResearchHotTerm["examples"][number] }) {
  const sourceLabel = example.source_label ?? example.source;
  const sourceChannel = example.source_channel?.trim();
  const sourceRank = typeof example.source_rank === "number" && Number.isFinite(example.source_rank) ? example.source_rank : null;
  const synthetic = example.is_synthetic === true;
  const metaPieces = [sourceChannel, sourceRank !== null ? `#${sourceRank}` : null].filter(Boolean);
  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0">
          <span className="block truncate text-[10px] font-black uppercase tracking-widest text-slate-400">{sourceLabel}</span>
          <span className="mt-0.5 line-clamp-2 text-xs font-semibold leading-snug text-slate-600">{example.title}</span>
        </span>
        {example.url ? <ExternalLink size={12} className="mt-0.5 shrink-0 text-slate-400" /> : null}
      </div>
      {metaPieces.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {sourceChannel ? (
            <span className="rounded-md bg-white/80 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-slate-500 ring-1 ring-slate-100">
              频道 {sourceChannel}
            </span>
          ) : null}
          {sourceRank !== null ? (
            <span className="rounded-md bg-white/80 px-1.5 py-0.5 text-[9px] font-black uppercase tracking-widest text-slate-500 ring-1 ring-slate-100">
              Rank {sourceRank}
            </span>
          ) : null}
        </div>
      ) : null}
      {example.match_reason ? (
        <div className="mt-1 line-clamp-2 text-[10px] leading-4 text-slate-500">
          匹配原因: {example.match_reason}
        </div>
      ) : null}
      {synthetic ? (
        <div className="mt-2 inline-flex items-center gap-1 rounded-md bg-rose-100 px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-rose-700 ring-1 ring-rose-200">
          <AlertCircle size={10} />
          <span>Synthetic</span>
        </div>
      ) : null}
    </>
  );

  if (example.url) {
    return (
      <a
        href={example.url}
        target="_blank"
        rel="noreferrer"
        className={`group/link flex items-start gap-2 rounded-xl p-2 text-left transition-colors ${synthetic ? "bg-rose-50 ring-1 ring-rose-200 hover:bg-rose-100" : "bg-slate-50 hover:bg-indigo-50"}`}
      >
        <span className="min-w-0 flex-1">{body}</span>
      </a>
    );
  }

  return (
    <div className={`rounded-xl p-2 ${synthetic ? "bg-rose-50 ring-1 ring-rose-200" : "bg-slate-50"}`}>
      {body}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone: "amber" | "orange" | "red" }) {
  return (
    <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 transition-all hover:shadow-lg hover:shadow-slate-200/50">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-2 text-3xl font-black tracking-tight ${metricToneClass(tone)}`}>
        {value}
      </div>
    </div>
  );
}

function QualityFact({ label, value, detail, tone = "neutral" }: { label: string; value: string | number; detail: string; tone?: "neutral" | "pass" | "warn" | "fail" }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-2 text-lg font-black tracking-tight ${tone === "fail" ? "text-rose-600" : tone === "warn" ? "text-amber-600" : tone === "pass" ? "text-emerald-600" : "text-slate-900"}`}>
        {value}
      </div>
      <div className="mt-2 text-xs leading-5 text-slate-500">{detail}</div>
    </div>
  );
}

function StatChip({ label, value, tone }: { label: string; value: number; tone: "emerald" | "amber" | "rose" | "sky" }) {
  const cls = {
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-100",
    amber: "bg-amber-50 text-amber-700 ring-amber-100",
    rose: "bg-rose-50 text-rose-700 ring-rose-100",
    sky: "bg-sky-50 text-sky-700 ring-sky-100"
  }[tone];
  return (
    <div className={`rounded-2xl px-4 py-3 ring-1 ${cls}`}>
      <div className="text-[10px] font-black uppercase tracking-widest">{label}</div>
      <div className="mt-1 text-lg font-black">{value}</div>
    </div>
  );
}

function EmptyHint({ label }: { label: string }) {
  return <div className="rounded-2xl border-2 border-dashed border-slate-200 p-8 text-center text-sm text-slate-400 font-medium">{label}</div>;
}

function sourceStatusLabel(status: string) {
  if (status === "active") return "有数据";
  if (status === "connected_empty") return "空结果";
  if (status === "degraded") return "降级";
  if (status === "error") return "错误";
  if (status === "pending_connector") return "待接入";
  if (status === "internal_ready") return "内部可用";
  return status;
}

function sourceStatusClass(status: string) {
  if (status === "active") return "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-100";
  if (status === "connected_empty") return "bg-sky-50 text-sky-700 ring-1 ring-sky-100";
  if (status === "degraded") return "bg-orange-50 text-orange-700 ring-1 ring-orange-100";
  if (status === "error") return "bg-rose-50 text-rose-700 ring-1 ring-rose-100";
  if (status === "pending_connector") return "bg-slate-100 text-slate-500 ring-1 ring-slate-200";
  if (status === "internal_ready") return "bg-amber-50 text-amber-700 ring-1 ring-amber-100";
  return "bg-slate-100 text-slate-700 ring-1 ring-slate-200";
}

function sourceStateNote(source: ResearchHotTerms["sources"][number]) {
  if (source.status === "active") return "正式来源 / live";
  if (source.status === "connected_empty") return "空结果 / 需要复核";
  if (source.status === "degraded") return "fallback / 部分失败";
  if (source.status === "error") return "fallback / 错误";
  if (source.status === "pending_connector") return "待接入 / 无结果";
  if (source.status === "internal_ready") return "内部可用 / 未外连";
  return source.status;
}

function isFallbackSource(source: ResearchHotTerms["sources"][number]) {
  return source.status === "degraded"
    || source.status === "error"
    || /fallback/i.test(source.last_run_status ?? "")
    || /fallback/i.test(source.last_error ?? "");
}

function qualityTone(label: string): "neutral" | "pass" | "warn" | "fail" {
  if (label === "LIVE") return "pass";
  if (label === "EMPTY") return "warn";
  if (label === "STALE") return "warn";
  return label === "FALLBACK" ? "warn" : "fail";
}

function qualityNote(label: string) {
  if (label === "LIVE") return "来源健康，仍按研究线索看待。";
  if (label === "EMPTY") return "只有空结果，不能把热词当成正式信号。";
  if (label === "STALE") return "数据日期滞后，只适合回看和复核。";
  if (label === "FALLBACK") return "存在 fallback / 降级来源，必须回看原始出处。";
  return "存在错误来源，当前视图只适合排查和复核。";
}

function metricToneClass(tone: "amber" | "orange" | "red") {
  if (tone === "amber") return "text-[#eab308]";
  if (tone === "orange") return "text-[#f97316]";
  return "text-[#ef4444]";
}

function heatColor(intensity: number) {
  if (!Number.isFinite(intensity) || intensity <= 0.24) return "#eab308";
  if (intensity <= 0.6) return "#f97316";
  return "#ef4444";
}

function formatPercent(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function sumIrrelevant(result: ResearchHotTermsRefresh) {
  return result.sources.reduce((total, source) => total + (source.irrelevant ?? 0), 0);
}

function formatShortDate(value: string | null | undefined) {
  if (!value) return "-";
  return value.slice(0, 10);
}
