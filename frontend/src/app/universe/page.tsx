"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Database, Filter, PlayCircle } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type IngestionBatch, type IngestionPlan, type IngestionPriority, type IngestionTask, type InstrumentsResponse } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

export default function UniversePage() {
  const [payload, setPayload] = useState<InstrumentsResponse | null>(null);
  const [plan, setPlan] = useState<IngestionPlan | null>(null);
  const [batches, setBatches] = useState<IngestionBatch[]>([]);
  const [tasks, setTasks] = useState<IngestionTask[]>([]);
  const [priority, setPriority] = useState<IngestionPriority | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [assetType, setAssetType] = useState("all");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [queueMessage, setQueueMessage] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const limit = 100;

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all([
      api.instruments({ market, board: market === "A" ? board : "all", assetType, q: query, limit, offset }),
      api.ingestionPlan(),
      api.ingestionBatches(),
      api.ingestionTasks(),
      api.ingestionPriority({ market: market === "ALL" ? "A" : market, board: market === "A" ? board : "all", limit: 10 })
    ])
      .then(([instrumentRows, ingestionPlan, batchRows, taskRows, priorityRows]) => {
        setPayload(instrumentRows);
        setPlan(ingestionPlan);
        setBatches(batchRows);
        setTasks(taskRows);
        setPriority(priorityRows);
      })
      .catch((err: Error) => setError(`证券主数据读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board, assetType, query, offset, refreshKey]);

  const queueBatch = (targetMarket: string) => {
    setAction("正在创建行情补齐任务...");
    setQueueMessage("");
    api.createIngestionTask({ task_type: "batch", market: targetMarket, board: targetMarket === "A" ? board : "all", source: "akshare", batch_limit: 20, periods: 320 })
      .then((task) => {
        setQueueMessage(`已创建 1 个任务：${task.market}/${task.board}`);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`创建任务失败：${err.message}`))
      .finally(() => setAction(""));
  };

  const queueBackfill = () => {
    const markets = market === "ALL" ? ["A", "US", "HK"] : [market];
    setAction("正在批量创建全市场补齐队列...");
    setQueueMessage("");
    api.createIngestionBackfill({
      markets,
      board: market === "A" ? board : "all",
      source: "akshare",
      batches_per_market: 3,
      batch_limit: 20,
      periods: 320
    })
      .then((result) => {
        setQueueMessage(`已入队 ${result.queued_count} 个任务，跳过 ${result.skipped_count} 个已有队列。`);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`批量入队失败：${err.message}`))
      .finally(() => setAction(""));
  };

  const runNext = () => {
    setAction("正在运行最高优先级任务...");
    setQueueMessage("");
    api.runNextIngestionTask()
      .then((task) => {
        setQueueMessage(`已运行任务：${task.market}/${task.board}，状态 ${task.status}，处理 ${task.processed} 只。`);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`运行任务失败：${err.message}`))
      .finally(() => setAction(""));
  };

  const runQueue = () => {
    setAction("正在连续运行任务队列...");
    setQueueMessage("");
    api.runIngestionQueue(3)
      .then((result) => {
        setQueueMessage(`已运行 ${result.tasks_run} 个任务，停止原因：${result.stopped_reason}。`);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`运行队列失败：${err.message}`))
      .finally(() => setAction(""));
  };

  if (loading) return <div className="page-shell"><LoadingState label="正在加载证券主数据" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="label">Security Master</div>
        <h1 className="mt-2 text-2xl font-semibold">全市场证券主数据</h1>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
          先建立 A股、港股、美股的证券主数据，再分批拉取行情。全市场分析必须先经过数据覆盖和研究准入门。
        </p>
      </section>

      <section className="panel p-4">
        <div className="flex flex-wrap items-center gap-2">
          {MARKET_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setMarket(option);
                setOffset(0);
                if (option !== "A") setBoard("all");
              }}
              className={`h-10 rounded-md border px-4 text-sm ${
                market === option ? "border-mint bg-mint text-white" : "border-line bg-white text-ink hover:border-mint"
              }`}
            >
              {marketLabel(option)}
            </button>
          ))}
        </div>
        {market === "A" ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {A_BOARD_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setBoard(option);
                  setOffset(0);
                }}
                className={`h-9 rounded-md border px-3 text-sm ${
                  board === option ? "border-amber bg-amber text-white" : "border-line bg-white text-ink hover:border-amber"
                }`}
              >
                {boardLabel(option)}
              </button>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold"><Filter size={16} />筛选</div>
          <select className="h-10 rounded-md border border-line bg-white px-3 text-sm" value={assetType} onChange={(event) => { setAssetType(event.target.value); setOffset(0); }}>
            <option value="all">全部类型</option>
            <option value="equity">股票</option>
            <option value="etf">ETF</option>
          </select>
          <input
            className="h-10 w-56 rounded-md border border-line bg-white px-3 text-sm"
            placeholder="代码或名称"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
          <div className="label ml-auto">共 {payload?.total ?? 0} 条，当前 {payload?.offset ?? 0} - {Math.min((payload?.offset ?? 0) + (payload?.rows.length ?? 0), payload?.total ?? 0)}</div>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="panel overflow-hidden">
          <div className="border-b border-line p-5">
            <h2 className="text-lg font-semibold">证券列表</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1120px] text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-4 py-3">代码</th>
                  <th className="px-4 py-3">市场</th>
                  <th className="px-4 py-3">类型</th>
                  <th className="px-4 py-3">行业</th>
                  <th className="px-4 py-3 text-right">市值</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">K线</th>
                  <th className="px-4 py-3">数据源</th>
                </tr>
              </thead>
              <tbody>
                {(payload?.rows ?? []).map((row) => (
                  <tr key={`${row.market}-${row.code}`} className="border-t border-line">
                    <td className="px-4 py-3 font-medium">
                      <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/universe`} className="hover:text-mint">
                        {row.name}
                      </Link>
                      <div className="label">{row.code}</div>
                    </td>
                    <td className="px-4 py-3">{marketLabel(row.market)}<div className="label">{boardLabel(row.board)} / {row.exchange}</div></td>
                    <td className="px-4 py-3">{row.asset_type}<div className="label">{row.currency}{row.is_etf ? " / ETF" : ""}{row.is_adr ? " / ADR" : ""}</div></td>
                    <td className="px-4 py-3">{row.industry_level1}<div className="label">{row.industry_level2 || "-"}</div></td>
                    <td className="mono px-4 py-3 text-right">{row.market_cap.toFixed(1)}</td>
                    <td className="px-4 py-3">{row.listing_status}<div className="label">{row.is_active ? "active" : "inactive"}{row.is_st ? " / ST" : ""}</div></td>
                    <td className="px-4 py-3">
                      <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/universe`} className="text-mint">查看</Link>
                      <div className="label">{row.bars_count} 根 / {row.latest_trade_date ?? "未下载"}</div>
                    </td>
                    <td className="px-4 py-3">{row.data_vendor}<div className="label">{row.source}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-line p-4">
            <button type="button" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - limit))} className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-40">上一页</button>
            <button type="button" disabled={offset + limit >= (payload?.total ?? 0)} onClick={() => setOffset(offset + limit)} className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-40">下一页</button>
          </div>
        </div>

        <div className="space-y-4">
          <section className="panel p-5">
          <div className="mb-4 flex items-center gap-2 text-lg font-semibold"><PlayCircle size={18} />全市场接入计划</div>
            <div className="mb-4 flex flex-wrap gap-2">
              <button type="button" onClick={() => queueBatch(market === "ALL" ? "A" : market)} disabled={Boolean(action)} className="rounded-md bg-mint px-3 py-2 text-sm text-white disabled:opacity-50">创建下一批</button>
              <button type="button" onClick={queueBackfill} disabled={Boolean(action)} className="rounded-md border border-line px-3 py-2 text-sm hover:border-mint disabled:opacity-50">批量入队</button>
              <button type="button" onClick={runNext} disabled={Boolean(action)} className="rounded-md border border-line px-3 py-2 text-sm hover:border-mint disabled:opacity-50">运行最高优先级</button>
              <button type="button" onClick={runQueue} disabled={Boolean(action)} className="rounded-md border border-line px-3 py-2 text-sm hover:border-mint disabled:opacity-50">连续运行3个</button>
              {action ? <span className="self-center text-sm text-slate-600">{action}</span> : null}
            </div>
            {queueMessage ? <div className="mb-4 rounded-md border border-line bg-slate-50 p-3 text-sm text-slate-700">{queueMessage}</div> : null}
            <div className="space-y-3">
              {(plan?.markets ?? []).map((item) => (
                <div key={item.market} className="rounded-md border border-line bg-slate-50 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-medium">{marketLabel(item.market)}</div>
                    <div className="mono text-sm">{item.stocks_with_bars}/{item.stock_count}</div>
                  </div>
                  <div className="label mt-1">覆盖 {Math.round(item.coverage_ratio * 100)}%，下一批 {item.next_batch_size}，offset {item.next_batch_offset}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 space-y-2">
              {(plan?.discovery_commands ?? []).slice(0, 3).map((command) => <Command key={command} value={command} />)}
              {(plan?.recommended_commands ?? []).slice(0, 3).map((command) => <Command key={command} value={command} />)}
            </div>
          </section>

          <section className="panel p-5">
            <div className="mb-4 flex items-center gap-2 text-lg font-semibold"><PlayCircle size={18} />行情任务中心</div>
            <div className="space-y-2">
              {tasks.slice(0, 8).map((task) => (
                <div key={task.task_key} className="rounded-md border border-line bg-slate-50 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium">{task.task_type} / {task.market}{task.stock_code ? ` / ${task.stock_code}` : ""}</div>
                    <span className={`rounded-md px-2 py-1 text-xs ${task.status === "success" ? "bg-mint text-white" : task.status === "failed" ? "bg-red-100 text-red-700" : task.status === "running" ? "bg-amber text-white" : "bg-white text-slate-600"}`}>{task.status}</span>
                  </div>
                  <div className="label mt-1">source {task.source} / requested {task.requested} / processed {task.processed} / failed {task.failed} / retry {task.retry_count}</div>
                  {task.error ? <div className="mt-2 text-xs text-rose">{task.error}</div> : null}
                  {task.status !== "running" && task.status !== "success" ? (
                    <button type="button" onClick={() => api.runIngestionTask(task.id).then(() => setRefreshKey((value) => value + 1)).catch((err: Error) => setError(`运行任务失败：${err.message}`))} className="mt-2 rounded-md border border-line px-2 py-1 text-xs hover:border-mint">运行</button>
                  ) : null}
                </div>
              ))}
              {tasks.length === 0 ? <div className="text-sm text-slate-600">暂无任务，先创建下一批。</div> : null}
            </div>
          </section>

          <section className="panel p-5">
            <div className="mb-4 text-lg font-semibold">优先补齐候选</div>
            <div className="space-y-2">
              {(priority?.candidates ?? []).slice(0, 8).map((row) => (
                <div key={row.code} className="flex items-center justify-between gap-3 rounded-md border border-line bg-slate-50 p-3 text-sm">
                  <div>
                    <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/universe`} className="font-medium hover:text-mint">{row.name}<span className="label ml-2">{row.code}</span></Link>
                    <div className="label">{boardLabel(row.board)} / 已有 {row.bars_count} 根 / 缺 {row.missing_bars} 根</div>
                  </div>
                  <div className="mono text-right text-xs">{row.priority_score.toFixed(1)}</div>
                </div>
              ))}
              {(priority?.candidates ?? []).length === 0 ? <div className="text-sm text-slate-600">当前筛选范围没有待补齐候选。</div> : null}
            </div>
          </section>

          <section className="panel p-5">
            <div className="mb-4 flex items-center gap-2 text-lg font-semibold"><Database size={18} />最近批次</div>
            <div className="space-y-2">
              {batches.slice(0, 8).map((batch) => (
                <div key={batch.batch_key} className="rounded-md border border-line bg-slate-50 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium">{batch.job_name} / {batch.market}</div>
                    <span className={`rounded-md px-2 py-1 text-xs ${batch.status === "success" ? "bg-mint text-white" : batch.status === "failed" ? "bg-red-100 text-red-700" : "bg-amber text-white"}`}>{batch.status}</span>
                  </div>
                  <div className="label mt-1">offset {batch.offset} / requested {batch.requested} / processed {batch.processed} / failed {batch.failed}</div>
                </div>
              ))}
              {batches.length === 0 ? <div className="text-sm text-slate-600">暂无批次记录。</div> : null}
            </div>
          </section>
        </div>
      </section>
    </div>
  );
}

function Command({ value }: { value: string }) {
  return (
    <div className="overflow-x-auto rounded-md border border-line bg-slate-950 px-3 py-2 text-xs text-slate-100">
      <code>{value}</code>
    </div>
  );
}
