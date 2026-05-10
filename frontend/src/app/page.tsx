"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowRight, BarChart3, ClipboardCheck, Database, FileText, Layers3, PlayCircle, Repeat2, ShieldCheck } from "lucide-react";
import { api, type BackfillManifest, type DataQuality, type DataStatus, type IndustryRadarRow, type IngestionBatch, type IngestionPlan, type IngestionTask, type MarketSummary, type ReportSummary, type ResearchUniverse, type TrendPoolRow, type WatchlistChanges } from "@/lib/api";
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
  const [ingestionPlan, setIngestionPlan] = useState<IngestionPlan | null>(null);
  const [backfillManifest, setBackfillManifest] = useState<BackfillManifest | null>(null);
  const [ingestionTasks, setIngestionTasks] = useState<IngestionTask[]>([]);
  const [ingestionBatches, setIngestionBatches] = useState<IngestionBatch[]>([]);
  const [researchUniverse, setResearchUniverse] = useState<ResearchUniverse | null>(null);
  const [watchlistChanges, setWatchlistChanges] = useState<WatchlistChanges | null>(null);
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
      api.ingestionPlan(),
      api.backfillManifest(),
      api.ingestionTasks(),
      api.ingestionBatches(),
      api.researchUniverse()
    ]).then(([status, quality, plan, manifest, tasks, batches, universe]) => {
      setDataStatus(status.status === "fulfilled" ? status.value : null);
      setDataQuality(quality.status === "fulfilled" ? quality.value : null);
      setIngestionPlan(plan.status === "fulfilled" ? plan.value : null);
      setBackfillManifest(manifest.status === "fulfilled" ? manifest.value : null);
      setIngestionTasks(tasks.status === "fulfilled" ? tasks.value : []);
      setIngestionBatches(batches.status === "fulfilled" ? batches.value : []);
      setResearchUniverse(universe.status === "fulfilled" ? universe.value : null);
    });
  }, []);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载 AlphaRadar 数据" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  const topStocks = trendPool.slice(0, 8);
  const latestRun = dataStatus?.runs?.[0] ?? null;
  const queuedTasks = ingestionTasks.filter((task) => ["queued", "pending"].includes(task.status)).length;
  const runningTasks = ingestionTasks.filter((task) => task.status === "running").length;
  const failedTasks = ingestionTasks.filter((task) => task.status === "failed").length;
  const completedTasks = ingestionTasks.filter((task) => ["success", "completed"].includes(task.status)).length;
  const batchRequested = ingestionBatches.reduce((sum, batch) => sum + (Number.isFinite(batch.requested) ? batch.requested : 0), 0);
  const batchProcessed = ingestionBatches.reduce((sum, batch) => sum + (Number.isFinite(batch.processed) ? batch.processed : 0), 0);
  const batchProgress = batchRequested > 0 ? Math.round((batchProcessed / batchRequested) * 100) : null;
  const manifestTotals = backfillManifest?.totals ?? {};
  const manifestCoverage = backfillManifest?.coverage ?? [];

  return (
    <div className="page-shell space-y-5">
      <section className="grid gap-4 lg:grid-cols-[1.4fr_0.9fr]">
        <div className="panel p-5">
          <div className="label">今日雷达</div>
          <h1 className="mt-2 text-2xl font-semibold tracking-normal">产业热度、趋势强度与证据链观察台</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            AlphaRadar 只生成观察池和研究线索，不输出买入、卖出、目标价或收益承诺。产业热度是资讯、行情、关联股票和观察池共同形成的赛道热度。
          </p>
          <div className="mt-5 grid gap-3 md:grid-cols-4">
            <Metric label="样本股票" value={summary?.stock_count ?? 0} />
            <Metric label="最新交易日" value={summary?.latest_trade_date ?? "-"} />
            <Metric label="观察候选" value={summary?.watch_count ?? 0} />
            <Metric label="产业热度记录" value={summary?.industry_heat_records ?? 0} />
          </div>
        </div>
        <div className="panel p-5">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <FileText size={18} />
            最新简报
          </div>
          <p className="mt-4 text-lg font-semibold">{report?.title}</p>
          <p className="mt-3 text-sm leading-6 text-slate-600">{report?.market_summary}</p>
          <Link href="/report" className="mt-5 inline-flex items-center gap-2 rounded-md bg-mint px-4 py-2 text-sm text-white">
            查看日报 <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-5">
        <PanelLink icon={<Layers3 size={18} />} title="产业雷达" href="/industry" text="查看热度分、7日变化、核心关键词与相关新闻线索。" />
        <PanelLink icon={<BarChart3 size={18} />} title="趋势股票池" href="/trend" text="按最终评分、趋势分、风险扣分和观察等级筛选候选。" />
        <PanelLink icon={<Repeat2 size={18} />} title="观察池复盘" href="/watchlist" text="追踪新进、移出、评级变化和分数跃迁，定位今日研究重点。" />
        <PanelLink icon={<ClipboardCheck size={18} />} title="研究任务" href="/research" text="汇总待验证事项与风险核验，生成每日投研行动清单。" />
        <PanelLink icon={<AlertTriangle size={18} />} title="证据链核验" href="/stocks/300308" text="查看单股产业逻辑、趋势逻辑、催化线索和待验证事项。" />
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><Repeat2 size={18} />观察池变化</div>
            <p className="mt-1 text-sm text-slate-600">跟踪最新观察候选相对上一交易日的新进、移出、评级变化和评分变化。首日快照会把当前候选视为新进。</p>
          </div>
          <Link href="/watchlist" className="text-sm text-mint">查看完整复盘</Link>
        </div>
        <div className="label mb-3">{watchlistChanges?.previous_date ?? "首日"} → {watchlistChanges?.latest_date ?? "-"}</div>
        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="当前观察" value={watchlistChanges?.summary.latest_watch_count ?? 0} />
          <Metric label="新进" value={watchlistChanges?.summary.new_count ?? 0} />
          <Metric label="移出" value={watchlistChanges?.summary.removed_count ?? 0} />
          <Metric label="评级变化" value={(watchlistChanges?.summary.upgraded_count ?? 0) + (watchlistChanges?.summary.downgraded_count ?? 0)} />
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <ChangeList title="新进观察" rows={watchlistChanges?.new_entries ?? []} />
          <ChangeList title="评分上升" rows={watchlistChanges?.score_gainers ?? []} />
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">研究股票池准入</h2>
            <p className="mt-1 text-sm text-slate-600">在评分前先过滤 ST、历史不足、市值过小、流动性不足和低价噪声，避免全市场分析被不可研究标的污染。</p>
          </div>
          <Link href="/trend" className="text-sm text-mint">查看趋势池</Link>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="全市场股票" value={researchUniverse?.summary.stock_count ?? 0} />
          <Metric label="可研究" value={researchUniverse?.summary.eligible_count ?? 0} />
          <Metric label="排除" value={researchUniverse?.summary.excluded_count ?? 0} />
          <Metric label="准入率" value={`${Math.round((researchUniverse?.summary.eligible_ratio ?? 0) * 100)}%`} />
        </div>
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          {(researchUniverse?.segments ?? []).map((segment) => (
            <div key={`universe-${segment.market}-${segment.board}`} className="rounded-md border border-line bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium">{marketLabel(segment.market)}</div>
                <div className="label">{boardLabel(segment.board)}</div>
              </div>
              <div className="mono mt-2 text-lg font-semibold">{segment.eligible_count}/{segment.stock_count}</div>
              <div className="label mt-1">准入率 {Math.round(segment.eligible_ratio * 100)}%</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">全市场分区</h2>
            <p className="mt-1 text-sm text-slate-600">按美股、A股、港股组织研究入口；A股继续拆分主板、创业板、科创板、北交所。</p>
          </div>
          <Link href="/trend" className="text-sm text-mint">进入全市场分析</Link>
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          {(summary?.markets ?? []).map((segment) => (
            <div key={segment.market} className="rounded-md border border-line bg-slate-50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold">{marketLabel(segment.market)}</div>
                <div className="label">{segment.stock_count} 只 / 观察 {segment.watch_count}</div>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {segment.boards.map((board) => (
                  <span key={board.board} className="rounded-md border border-line bg-white px-2 py-1 text-xs text-slate-700">
                    {boardLabel(board.board)} {board.stock_count}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><Database size={18} />数据源状态</div>
            <p className="mt-1 text-sm text-slate-600">真实源不可用时自动回退 mock；这里显示最近 pipeline 留痕和各市场日线覆盖。</p>
          </div>
          <div className="label">
            最新运行 {latestRun?.finished_at?.slice(0, 19).replace("T", " ") ?? latestRun?.started_at?.slice(0, 19).replace("T", " ") ?? "-"}
          </div>
        </div>
        <div className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="grid gap-2 md:grid-cols-3">
            {(dataStatus?.coverage ?? []).map((row) => (
              <div key={`${row.market}-${row.board}`} className="rounded-md border border-line bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{marketLabel(row.market)}</div>
                  <div className="label">{boardLabel(row.board)}</div>
                </div>
                <div className="mono mt-2 text-lg font-semibold">{Math.round(row.coverage_ratio * 100)}%</div>
                <div className="label mt-1">{row.stocks_with_bars}/{row.stock_count} 有日线，最新 {row.latest_trade_date ?? "-"}</div>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            {(dataStatus?.runs ?? []).slice(0, 4).map((run, index) => (
              <div key={`${run.job_name}-${index}`} className="rounded-md border border-line bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{run.job_name}</div>
                  <span className={`rounded-md px-2 py-1 text-xs ${run.status === "success" ? "bg-mint text-white" : "bg-red-100 text-red-700"}`}>
                    {run.status}
                  </span>
                </div>
                <div className="label mt-1">source {run.effective_source} / {run.source_kind ?? "unknown"} / {formatPercent(run.source_confidence)}</div>
                <div className="label mt-1">markets {run.markets.join(",")}</div>
                <div className="label mt-1">rows {run.rows_total}，insert {run.rows_inserted}，update {run.rows_updated}</div>
              </div>
            ))}
            {(dataStatus?.source_coverage ?? []).slice(0, 4).map((row) => (
              <div key={`source-${row.source_kind}-${row.source}`} className="rounded-md border border-line bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{row.source}</div>
                  <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">{row.source_kind}</span>
                </div>
                <div className="label mt-1">{row.stocks_with_bars} 只 / {row.bars_count} 根，最新 {row.latest_trade_date ?? "-"}</div>
              </div>
            ))}
            {(dataStatus?.runs ?? []).length === 0 ? <div className="rounded-md border border-line bg-slate-50 p-3 text-sm text-slate-600">状态接口暂未返回运行留痕，覆盖率和批次面板会在后端写入后自动显示。</div> : null}
          </div>
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><PlayCircle size={18} />全市场回填进度</div>
            <p className="mt-1 text-sm text-slate-600">展示已排队任务、运行中任务、失败任务和最近批次处理量；接口缺字段时保留可用状态，不阻塞 Dashboard。</p>
          </div>
          <div className="label">批次处理 {batchProgress === null ? "-" : `${batchProgress}%`}</div>
        </div>
        <div className="grid gap-3 md:grid-cols-5">
          <Metric label="队列任务" value={ingestionTasks.length} />
          <Metric label="待运行" value={queuedTasks} />
          <Metric label="运行中" value={runningTasks} />
          <Metric label="已完成" value={completedTasks} />
          <Metric label="失败" value={failedTasks} />
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-md border border-line bg-slate-50 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="font-medium">最近批次</div>
              <div className="label">{batchProcessed}/{batchRequested || "-"} processed</div>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-white">
              <div className="h-full rounded-full bg-mint" style={{ width: `${batchProgress ?? 0}%` }} />
            </div>
            <div className="label mt-2">失败 {ingestionBatches.reduce((sum, batch) => sum + (Number.isFinite(batch.failed) ? batch.failed : 0), 0)} / 最近记录 {ingestionBatches.length}</div>
            <div className="mt-4 rounded-md border border-line bg-white p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">Manifest</div>
                <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">{backfillManifest?.status ?? "not_started"}</span>
              </div>
              <div className="label mt-2">已处理 {manifestTotals.processed_symbols ?? 0} 只 / 写入 {manifestTotals.inserted ?? 0} 行</div>
              <div className="label mt-1">更新 {backfillManifest?.updated_at?.slice(0, 19).replace("T", " ") ?? "-"}</div>
            </div>
          </div>
          <div className="space-y-2">
            {manifestCoverage.slice(0, 3).map((row) => (
              <div key={`manifest-${row.market}`} className="rounded-md border border-line bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{marketLabel(row.market)}</div>
                  <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">{Math.round(row.coverage_ratio * 100)}%</span>
                </div>
                <div className="label mt-1">完整 {row.covered_symbols} / 部分 {row.partial_symbols} / 空 {row.empty_symbols}</div>
              </div>
            ))}
            {ingestionTasks.slice(0, 4).map((task) => (
              <div key={task.id} className="rounded-md border border-line bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{marketLabel(task.market)}<span className="label ml-2">{boardLabel(task.board)} / {task.task_type}</span></div>
                  <span className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">{task.status}</span>
                </div>
                <div className="label mt-1">requested {task.requested} / processed {task.processed} / failed {task.failed}</div>
              </div>
            ))}
            {ingestionTasks.length === 0 ? <div className="rounded-md border border-line bg-slate-50 p-3 text-sm text-slate-600">暂无队列任务；可先使用下方推荐命令或后端队列接口创建小批次。</div> : null}
          </div>
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={18} />全市场数据质量门</div>
            <p className="mt-1 text-sm text-slate-600">检查覆盖率、历史长度、OHLC异常、流动性缺失、数据源混用。质量不过关时，趋势和评分只作流程验证。</p>
          </div>
          <StatusPill status={dataQuality?.status ?? "WARN"} />
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <Metric label="检查股票" value={dataQuality?.summary.stock_count ?? 0} />
          <Metric label="FAIL" value={dataQuality?.summary.fail_count ?? 0} />
          <Metric label="WARN" value={dataQuality?.summary.warn_count ?? 0} />
          <Metric label="最低历史" value={`${dataQuality?.summary.min_required_bars ?? 60} 根`} />
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="grid gap-2 md:grid-cols-3">
            {(dataQuality?.segments ?? []).map((segment) => (
              <div key={`quality-${segment.market}-${segment.board}`} className="rounded-md border border-line bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{marketLabel(segment.market)}</div>
                  <StatusPill status={segment.status} compact />
                </div>
                <div className="label mt-1">{boardLabel(segment.board)} / 最新 {segment.latest_trade_date ?? "-"}</div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                  <Ratio label="覆盖" value={segment.coverage_ratio} />
                  <Ratio label="真实源" value={segment.real_coverage_ratio ?? 0} />
                  <Ratio label="60日" value={segment.required_history_ratio} />
                </div>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            {(dataQuality?.issues ?? []).slice(0, 5).map((issue) => (
              <div key={`${issue.code}-${issue.issue_type}`} className="rounded-md border border-line bg-white p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{issue.name}<span className="label ml-2">{issue.code}</span></div>
                  <StatusPill status={issue.severity} compact />
                </div>
                <div className="label mt-1">{marketLabel(issue.market)} / {boardLabel(issue.board)} / {issue.issue_type}</div>
                <p className="mt-2 text-xs leading-5 text-slate-600">{issue.message}</p>
              </div>
            ))}
            {(dataQuality?.issues ?? []).length === 0 ? <div className="rounded-md border border-line bg-slate-50 p-3 text-sm text-slate-600">当前未发现核心数据质量问题。</div> : null}
          </div>
        </div>
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold"><PlayCircle size={18} />真实数据分批接入计划</div>
            <p className="mt-1 text-sm text-slate-600">用于从 mock 过渡到真实源。先按单市场小批次跑，质量门通过后再扩大，不直接全市场硬拉。</p>
          </div>
          <div className="label">mode {ingestionPlan?.mode ?? "-"}</div>
        </div>
        <div className="grid gap-3 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="grid gap-2 md:grid-cols-3">
            {(ingestionPlan?.markets ?? []).map((item) => (
              <div key={`ingest-${item.market}`} className="rounded-md border border-line bg-slate-50 p-3">
                <div className="font-medium">{marketLabel(item.market)}</div>
                <div className="mono mt-2 text-lg font-semibold">{item.next_batch_size}</div>
                <div className="label mt-1">下批数量 / 当前覆盖 {Math.round(item.coverage_ratio * 100)}%</div>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            {(ingestionPlan?.recommended_commands ?? []).slice(0, 3).map((command) => (
              <div key={command} className="overflow-x-auto rounded-md border border-line bg-slate-950 px-3 py-2 text-xs text-slate-100">
                <code>{command}</code>
              </div>
            ))}
            <div className="flex flex-wrap gap-2 pt-1">
              {(ingestionPlan?.safety_rules ?? []).slice(0, 3).map((rule) => (
                <span key={rule} className="rounded-md border border-line bg-white px-2 py-1 text-xs text-slate-600">{rule}</span>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="panel p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">今日最强赛道</h2>
              <p className="mt-1 text-sm text-slate-600">综合热度用于排序赛道研究线索，不代表交易建议。</p>
            </div>
            <Link href="/industry" className="text-sm text-mint">全部</Link>
          </div>
          <div className="space-y-3">
            {industries.slice(0, 6).map((row) => (
              <div key={row.industry_id} className="border-b border-line pb-3 last:border-0 last:pb-0">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">{row.name}</div>
                    <div className="mt-1">
                      <span className={`rounded-md px-2 py-1 text-xs font-semibold ${evidenceStatusClass(row)}`}>
                        {evidenceStatusLabel(row)}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="label">综合热度</div>
                    <div className={`mono text-sm font-semibold ${row.heat_score === 0 ? "text-slate-500" : "text-mint"}`}>{formatNumber(row.heat_score)}</div>
                  </div>
                </div>
                <div className="label mt-2">{industryEvidenceLine(row)}</div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                  <CompactMetric label="资讯热度" value={formatNumber(newsHeat(row))} />
                  <CompactMetric label="关联股票" value={formatCount(row.related_stock_count)} />
                  <CompactMetric label="观察池" value={formatCount(row.watch_stock_count)} />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="panel overflow-hidden">
          <div className="border-b border-line p-5">
            <h2 className="text-lg font-semibold">趋势增强股票</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-4 py-3">股票</th>
                  <th className="px-4 py-3">市场</th>
                  <th className="px-4 py-3">产业</th>
                  <th className="px-4 py-3">评分</th>
                  <th className="px-4 py-3">可信度</th>
                  <th className="px-4 py-3">趋势</th>
                  <th className="px-4 py-3">风险扣分</th>
                  <th className="px-4 py-3">证据链</th>
                </tr>
              </thead>
              <tbody>
                {topStocks.map((row) => (
                  <tr key={row.code} className="border-t border-line">
                    <td className="px-4 py-3 font-medium">{row.name}<span className="label ml-2">{row.code}</span></td>
                    <td className="px-4 py-3">{marketLabel(row.market)}<div className="label">{boardLabel(row.board)} / {row.exchange}</div></td>
                    <td className="px-4 py-3">{row.industry}</td>
                    <td className="px-4 py-3"><ScoreBadge score={row.final_score} rating={row.rating} /></td>
                    <td className="px-4 py-3">
                      <div className="text-xs font-semibold">{row.confidence?.level ?? "unknown"} / {formatPercent(row.confidence?.combined_confidence)}</div>
                      <div className="label mt-1">源 {formatPercent(row.confidence?.source_confidence)} / 资讯 {formatPercent(row.confidence?.news_confidence)}</div>
                    </td>
                    <td className="mono px-4 py-3">{row.trend_score.toFixed(1)}</td>
                    <td className="mono px-4 py-3">{row.risk_penalty.toFixed(1)}</td>
                    <td className="px-4 py-3"><Link href={`/stocks/${encodeURIComponent(row.code)}?from=/`} className="text-mint">查看</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-line bg-slate-50 p-4">
      <div className="label">{label}</div>
      <div className="mono mt-2 text-xl font-semibold">{value}</div>
    </div>
  );
}

function CompactMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 px-2 py-2">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{value}</div>
    </div>
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
  if (status === "news_active") return "bg-mint text-white";
  if (status === "structure_active") return "bg-slate-900 text-white";
  if (status === "mapped_only") return "bg-amber text-white";
  return "bg-slate-100 text-slate-600";
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

function industryEvidenceLine(row: IndustryRadarRow) {
  if (row.top_keywords.length > 0) return row.top_keywords.join(" / ");
  if (row.heat_score === 0) return row.zero_heat_reason || fallbackEvidenceLine(row);
  return fallbackEvidenceLine(row);
}

function fallbackEvidenceLine(row: IndustryRadarRow) {
  const parts = [
    `${evidenceStatusLabel(row)}`,
    `关联 ${formatCount(row.related_stock_count)}`,
    `观察池 ${formatCount(row.watch_stock_count)}`
  ];
  if (isFiniteNumber(row.trend_breadth)) parts.push(`趋势宽度 ${formatRatio(row.trend_breadth)}`);
  if (isFiniteNumber(row.breakout_breadth)) parts.push(`突破宽度 ${formatRatio(row.breakout_breadth)}`);
  return parts.join(" / ");
}

function formatNumber(value: number | null | undefined) {
  return isFiniteNumber(value) ? value.toFixed(1) : "-";
}

function formatCount(value: number | null | undefined) {
  return isFiniteNumber(value) ? String(value) : "-";
}

function formatRatio(value: number | null | undefined) {
  return isFiniteNumber(value) ? `${Math.round(value * 100)}%` : "-";
}

function formatPercent(value: number | null | undefined) {
  return isFiniteNumber(value) ? `${Math.round(value * 100)}%` : "-";
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function Ratio({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-white p-2">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{Math.round(value * 100)}%</div>
    </div>
  );
}

function StatusPill({ status, compact = false }: { status: "PASS" | "WARN" | "FAIL"; compact?: boolean }) {
  const className =
    status === "PASS"
      ? "bg-mint text-white"
      : status === "WARN"
        ? "bg-amber text-white"
        : "bg-red-100 text-red-700";
  return <span className={`inline-flex rounded-md px-2 py-1 text-xs font-semibold ${className}`}>{compact ? status : `DATA ${status}`}</span>;
}

function ChangeList({ title, rows }: { title: string; rows: { code: string; name: string; market: string; board: string; rating: string | null; final_score: number | null; score_delta: number | null }[] }) {
  return (
    <div className="rounded-md border border-line bg-slate-50 p-3">
      <div className="mb-2 font-medium">{title}</div>
      <div className="space-y-2">
        {rows.slice(0, 5).map((row) => (
          <div key={`${title}-${row.code}`} className="flex items-center justify-between gap-3 rounded-md bg-white px-3 py-2 text-sm">
            <div>
              <div className="font-medium">{row.name}<span className="label ml-2">{row.code}</span></div>
              <div className="label">{marketLabel(row.market)} / {boardLabel(row.board)} / {row.rating ?? "-"}</div>
            </div>
            <div className="mono text-right">
              <div>{row.final_score?.toFixed(1) ?? "-"}</div>
              <div className="label">{row.score_delta === null ? "new" : `${row.score_delta > 0 ? "+" : ""}${row.score_delta.toFixed(1)}`}</div>
            </div>
          </div>
        ))}
        {rows.length === 0 ? <div className="rounded-md bg-white px-3 py-2 text-sm text-slate-600">暂无变化。</div> : null}
      </div>
    </div>
  );
}

function PanelLink({ icon, title, text, href }: { icon: React.ReactNode; title: string; text: string; href: string }) {
  return (
    <Link href={href} className="panel block p-5 hover:border-mint">
      <div className="flex items-center gap-2 font-semibold">{icon}{title}</div>
      <p className="mt-3 text-sm leading-6 text-slate-600">{text}</p>
    </Link>
  );
}
