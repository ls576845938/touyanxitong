"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Database, Filter, PlayCircle, Search, Layers, Activity, ChevronRight, AlertCircle, RefreshCw } from "lucide-react";
import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type IngestionBatch, type IngestionPlan, type IngestionPriority, type IngestionTask, type InstrumentsResponse } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { 
    opacity: 1,
    transition: { staggerChildren: 0.05 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 }
};

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
    setAction("创建中...");
    api.createIngestionTask({ task_type: "batch", market: targetMarket, board: targetMarket === "A" ? board : "all", source: "akshare", batch_limit: 20, periods: 320 })
      .then((task) => {
        setQueueMessage(`已创建任务：${task.market}/${task.board}`);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`创建任务失败：${err.message}`))
      .finally(() => setAction(""));
  };

  const queueBackfill = () => {
    const markets = market === "ALL" ? ["A", "US", "HK"] : [market];
    setAction("批量入队中...");
    api.createIngestionBackfill({
      markets,
      board: market === "A" ? board : "all",
      source: "akshare",
      batches_per_market: 3,
      batch_limit: 20,
      periods: 320
    })
      .then((result) => {
        setQueueMessage(`已入队 ${result.queued_count} 个任务`);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`批量入队失败：${err.message}`))
      .finally(() => setAction(""));
  };

  const runNext = () => {
    setAction("运行中...");
    api.runNextIngestionTask()
      .then((task) => {
        setQueueMessage(`已运行：${task.market}/${task.board}`);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`运行任务失败：${err.message}`))
      .finally(() => setAction(""));
  };

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载证券主数据" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  return (
    <motion.div 
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="min-h-screen bg-slate-50 px-6 py-8 space-y-6"
    >
      <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">SECURITY MASTER TERMINAL</div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight">全市场证券主数据</h1>
            <p className="mt-2 text-sm font-medium text-slate-500 max-w-2xl">
              构建跨市场的基础证券数据库，管理全球资产覆盖与行情接入进度。
            </p>
          </div>
          <div className="flex gap-4">
             <StatCard label="TOTAL INSTRUMENTS" value={payload?.total ?? 0} />
             <StatCard label="MARKET COVERAGE" value={Math.round((plan?.markets[0]?.coverage_ratio ?? 0) * 100)} unit="%" highlight />
          </div>
        </div>
      </motion.section>

      <motion.section variants={itemVariants} className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200">
        <div className="flex flex-wrap items-center gap-6">
          <div className="flex bg-slate-100 rounded-xl p-1">
            {MARKET_OPTIONS.map((option) => (
              <button
                key={option}
                onClick={() => {
                  setMarket(option);
                  setOffset(0);
                  if (option !== "A") setBoard("all");
                }}
                className={`px-4 py-2 rounded-lg text-xs font-black uppercase transition-all ${
                  market === option ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {marketLabel(option)}
              </button>
            ))}
          </div>

          <div className="h-8 w-px bg-slate-200" />

          <div className="flex items-center gap-3 flex-1 min-w-[300px]">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
              <input
                className="w-full bg-slate-50 border border-slate-100 rounded-xl pl-10 pr-4 py-2 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 transition-all placeholder:text-slate-300"
                placeholder="搜索代码或名称..."
                value={query}
                onChange={(e) => { setQuery(e.target.value); setOffset(0); }}
              />
            </div>
            
            <select 
              className="bg-slate-50 border border-slate-100 rounded-xl px-4 py-2 text-sm font-bold text-slate-700 outline-none focus:ring-2 focus:ring-indigo-100 transition-all"
              value={assetType} 
              onChange={(e) => { setAssetType(e.target.value); setOffset(0); }}
            >
              <option value="all">所有类型</option>
              <option value="equity">股票</option>
              <option value="etf">ETF</option>
            </select>
          </div>

          <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
            PAGE {Math.floor(offset / limit) + 1} / {Math.ceil((payload?.total ?? 0) / limit)}
          </div>
        </div>

        {market === "A" && (
          <div className="mt-3 flex flex-wrap gap-1.5 pl-1">
            {A_BOARD_OPTIONS.map((option) => (
              <button
                key={option}
                onClick={() => { setBoard(option); setOffset(0); }}
                className={`px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-tighter transition-all ${
                  board === option ? "bg-indigo-50 text-indigo-700 border border-indigo-100" : "text-slate-400 hover:text-slate-600"
                }`}
              >
                {boardLabel(option)}
              </button>
            ))}
          </div>
        )}
      </motion.section>

      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <motion.section variants={itemVariants} className="bg-white rounded-3xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-100/50">
                  <th className="pl-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">INSTRUMENT</th>
                  <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">CLASSIFICATION</th>
                  <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">MARKET CAP</th>
                  <th className="py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">DATA SYNC</th>
                  <th className="pr-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">ACTION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(payload?.rows ?? []).map((row) => (
                  <tr key={`${row.market}-${row.code}`} className="hover:bg-indigo-50/30 even:bg-slate-50/50 transition-all group">
                    <td className="pl-8 py-5">
                      <div className="flex items-center gap-3">
                         <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-[10px] font-black text-slate-400">
                           {row.market}
                         </div>
                         <div>
                            <div className="font-black text-slate-900 tracking-tight group-hover:text-indigo-600 transition-colors">{row.name}</div>
                            <div className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-tighter">{row.code}</div>
                         </div>
                      </div>
                    </td>
                    <td className="py-5">
                      <div className="space-y-1">
                         <div className="text-xs font-bold text-slate-600">{row.industry_level1}</div>
                         <div className="flex items-center gap-1.5">
                            <span className="text-[9px] font-black uppercase tracking-tighter text-slate-400 px-1.5 py-0.5 bg-slate-100 rounded-md">
                              {row.asset_type}
                            </span>
                            {row.is_etf && <span className="text-[9px] font-black uppercase tracking-tighter text-indigo-500 bg-indigo-50 px-1.5 py-0.5 rounded-md">ETF</span>}
                         </div>
                      </div>
                    </td>
                    <td className="py-5 text-right font-mono text-sm font-black text-slate-700">
                      {row.market_cap.toFixed(1)}
                    </td>
                    <td className="py-5">
                       <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2">
                             <div className={`w-1.5 h-1.5 rounded-full ${row.bars_count > 0 ? 'bg-emerald-500' : 'bg-slate-200'}`} />
                             <span className="text-[10px] font-bold text-slate-600">{row.bars_count} BARS</span>
                          </div>
                          <div className="text-[9px] font-bold text-slate-400">{row.latest_trade_date || "NO DATA"}</div>
                       </div>
                    </td>
                    <td className="pr-8 py-5 text-right">
                       <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/universe`} className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-slate-400 hover:text-indigo-600 transition-colors">
                         TERMINAL <ChevronRight size={12} />
                       </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="p-4 bg-slate-50/50 border-t border-slate-100 flex items-center justify-between">
            <button 
              disabled={offset <= 0} 
              onClick={() => setOffset(Math.max(0, offset - limit))} 
              className="px-6 py-2 rounded-xl bg-white border border-slate-200 text-xs font-black uppercase tracking-widest text-slate-600 hover:bg-slate-50 disabled:opacity-30 transition-all shadow-sm"
            >
              PREVIOUS
            </button>
            <button 
              disabled={offset + limit >= (payload?.total ?? 0)} 
              onClick={() => setOffset(offset + limit)} 
              className="px-6 py-2 rounded-xl bg-white border border-slate-200 text-xs font-black uppercase tracking-widest text-slate-600 hover:bg-slate-50 disabled:opacity-30 transition-all shadow-sm"
            >
              NEXT
            </button>
          </div>
        </motion.section>

        <motion.aside variants={itemVariants} className="space-y-6">
          <section className="bg-white rounded-3xl p-6 shadow-sm border border-slate-200">
            <div className="flex items-center gap-3 mb-6">
               <div className="w-10 h-10 rounded-2xl bg-indigo-600 flex items-center justify-center text-white shadow-lg shadow-indigo-100">
                 <PlayCircle size={20} />
               </div>
               <div>
                 <h2 className="text-lg font-black text-slate-900 tracking-tight">接入控制中心</h2>
                 <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">INGESTION PIPELINE</div>
               </div>
            </div>

            <div className="grid grid-cols-2 gap-2 mb-6">
               <ActionButton icon={<Layers size={14} />} label="创建批次" onClick={() => queueBatch(market === "ALL" ? "A" : market)} loading={action === "创建中..."} />
               <ActionButton icon={<Database size={14} />} label="批量入队" onClick={queueBackfill} loading={action === "批量入队中..."} />
               <ActionButton icon={<Activity size={14} />} label="最高优先" onClick={runNext} loading={action === "运行中..."} />
               <ActionButton icon={<RefreshCw size={14} />} label="连跑3个" onClick={() => api.runIngestionQueue(3).then(() => setRefreshKey(v => v+1))} />
            </div>

            {queueMessage && (
              <div className="mb-6 p-4 bg-indigo-50 border border-indigo-100 rounded-2xl text-xs font-bold text-indigo-700 animate-in fade-in slide-in-from-top-2">
                {queueMessage}
              </div>
            )}

            <div className="space-y-3">
              {(plan?.markets ?? []).map((item) => (
                <div key={item.market} className="bg-slate-50 rounded-2xl p-4 border border-slate-100 relative overflow-hidden group">
                  <div className="absolute top-0 right-0 h-full w-1 bg-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-black uppercase tracking-[0.15em] text-slate-400">{marketLabel(item.market)}</span>
                    <span className="text-xs font-black font-mono text-slate-900">{Math.round(item.coverage_ratio * 100)}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden mb-3">
                     <div className="h-full bg-indigo-600 rounded-full" style={{ width: `${item.coverage_ratio * 100}%` }} />
                  </div>
                  <div className="flex justify-between text-[10px] font-bold text-slate-500 font-mono">
                    <span>{item.stocks_with_bars} / {item.stock_count}</span>
                    <span className="text-indigo-600">OFFSET: {item.next_batch_offset}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="bg-white rounded-3xl p-6 shadow-sm border border-slate-200">
            <h2 className="text-sm font-black text-slate-900 uppercase tracking-widest mb-6 border-b border-slate-100 pb-3">
              优先级补齐候选
            </h2>
            <div className="space-y-4">
               {(priority?.candidates ?? []).slice(0, 5).map((row) => (
                 <div key={row.code} className="flex items-center justify-between group">
                    <div className="flex flex-col">
                       <Link href={`/stocks/${encodeURIComponent(row.code)}?from=/universe`} className="text-xs font-black text-slate-700 hover:text-indigo-600 transition-colors">
                         {row.name}
                       </Link>
                       <span className="text-[10px] font-bold text-slate-400 font-mono">{row.code}</span>
                    </div>
                    <div className="text-right">
                       <div className="text-xs font-black font-mono text-slate-900">{row.priority_score.toFixed(1)}</div>
                       <div className="text-[9px] font-bold text-slate-400">MISS {row.missing_bars}</div>
                    </div>
                 </div>
               ))}
            </div>
          </section>

          <section className="bg-slate-900 rounded-3xl p-6 shadow-2xl border border-slate-800 text-slate-300">
             <div className="flex items-center gap-2 mb-6">
                <AlertCircle size={16} className="text-indigo-400" />
                <span className="text-xs font-black uppercase tracking-widest text-white">Active Tasks</span>
             </div>
             <div className="space-y-3">
                {tasks.slice(0, 5).map((task) => (
                  <div key={task.task_key} className="bg-slate-800/50 border border-slate-700 rounded-xl p-3">
                     <div className="flex justify-between items-center mb-1">
                        <span className="text-[9px] font-black text-indigo-300 uppercase">{task.market} / {task.task_type}</span>
                        <span className={`text-[8px] font-black px-1.5 py-0.5 rounded-md ${
                          task.status === "success" ? "bg-emerald-500/20 text-emerald-400" : 
                          task.status === "running" ? "bg-indigo-500/20 text-indigo-400 animate-pulse" : 
                          "bg-slate-700 text-slate-400"
                        }`}>
                          {task.status.toUpperCase()}
                        </span>
                     </div>
                     <div className="text-[10px] font-mono text-slate-400">
                        REQ:{task.requested} PROC:{task.processed} FAIL:{task.failed}
                     </div>
                  </div>
                ))}
             </div>
          </section>
        </motion.aside>
      </div>
    </motion.div>
  );
}

function StatCard({ label, value, unit = "", highlight = false }: { label: string; value: number | string; unit?: string; highlight?: boolean }) {
  return (
    <div className={`px-6 py-3 rounded-2xl border ${highlight ? 'bg-indigo-600 border-indigo-500 shadow-lg shadow-indigo-100' : 'bg-slate-50 border-slate-100'}`}>
      <div className={`text-[9px] font-black uppercase tracking-widest mb-0.5 ${highlight ? 'text-indigo-200' : 'text-slate-400'}`}>{label}</div>
      <div className={`text-2xl font-black font-mono tracking-tight ${highlight ? 'text-white' : 'text-slate-900'}`}>
        {value}{unit && <span className="text-sm ml-0.5 opacity-60 font-bold">{unit}</span>}
      </div>
    </div>
  );
}

function ActionButton({ icon, label, onClick, loading = false }: { icon: React.ReactNode; label: string; onClick: () => void; loading?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="flex flex-col items-center justify-center gap-2 p-3 bg-slate-50 border border-slate-100 rounded-2xl hover:bg-white hover:border-indigo-100 hover:shadow-sm transition-all group disabled:opacity-50"
    >
       <div className="text-slate-400 group-hover:text-indigo-600 transition-colors">
         {loading ? <RefreshCw size={14} className="animate-spin" /> : icon}
       </div>
       <span className="text-[10px] font-black uppercase tracking-tighter text-slate-500 group-hover:text-slate-900">{label}</span>
    </button>
  );
}
