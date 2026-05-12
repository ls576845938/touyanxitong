"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowRight, BarChart3, FileText, FlaskConical, LayoutGrid, List, Map as MapIcon, ShieldCheck, TrendingUp, type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type ResearchDataGate, type ResearchTask, type ResearchTasks, type SignalBacktestLatest, type TenbaggerThesisList } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

const PRIORITIES = [
  { value: "all", label: "全部优先级" },
  { value: "high", label: "高优先级" },
  { value: "medium", label: "中优先级" },
  { value: "low", label: "低优先级" }
];

const TASK_TYPES = [
  { value: "all", label: "全部任务" },
  { value: "verify_question", label: "验证事项" },
  { value: "risk_review", label: "风险核验" }
];

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05
    }
  }
};

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0 }
};

export default function ResearchPage() {
  const [payload, setPayload] = useState<ResearchTasks | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [priority, setPriority] = useState("all");
  const [taskType, setTaskType] = useState("all");
  const [watchOnly, setWatchOnly] = useState(false);
  const [thesisSnapshot, setThesisSnapshot] = useState<TenbaggerThesisList | null>(null);
  const [researchGate, setResearchGate] = useState<ResearchDataGate | null>(null);
  const [backtestSnapshot, setBacktestSnapshot] = useState<SignalBacktestLatest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.researchTasks({
      market,
      board: market === "A" ? board : "all",
      priority,
      taskType,
      watchOnly,
      limit: 180
    })
      .then(setPayload)
      .catch((err: Error) => setError(`研究任务读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board, priority, taskType, watchOnly]);

  useEffect(() => {
    void Promise.allSettled([
      api.tenbaggerTheses({ limit: 1 }),
      api.researchDataGate({ limit: 1 }),
      api.latestBacktest()
    ]).then(([thesis, gate, backtest]) => {
      setThesisSnapshot(thesis.status === "fulfilled" ? thesis.value : null);
      setResearchGate(gate.status === "fulfilled" ? gate.value : null);
      setBacktestSnapshot(backtest.status === "fulfilled" ? backtest.value : null);
    });
  }, []);

  const grouped = useMemo(() => groupTasks(payload?.tasks ?? []), [payload]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载研究任务中心" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  const thesisSummary = thesisSnapshot?.summary;
  const gateSummary = researchGate?.summary;
  const latestBacktest = backtestSnapshot?.latest ?? null;
  const formalReadyPct = Math.round((gateSummary?.formal_ready_ratio ?? 0) * 100);

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
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Intelligence Hub</div>
            <h1 className="text-4xl font-bold tracking-tight text-slate-900">研究任务中心</h1>
            <p className="max-w-2xl text-base text-slate-500">
              将观察池候选的待验证事项和风险摘要转成每日投研清单。这里只做研究辅助，不输出买入、卖出、目标价或收益承诺。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <ResearchLink href="/research/thesis" label="假设引擎" icon={FlaskConical} />
            <ResearchLink href="/research/hot-terms" label="热词雷达" icon={TrendingUp} />
            <ResearchLink href="/research/ai-infra-map" label="AI算力图谱" icon={MapIcon} />
            <ResearchLink href="/research/backtest" label="回测校准" icon={BarChart3} />
            <ResearchLink href="/research/data-quality" label="数据门控" icon={ShieldCheck} />
            <ResearchLink href="/research/brief" label="今日工作单" icon={FileText} />
            <ResearchLink href="/research/evidence" label="证据总表" icon={LayoutGrid} />
            <ResearchLink href="/research/stock-pool" label="研究股票池" icon={List} />
            <ResearchLink href="/research/industry-chain" label="产业链工作台" icon={MapIcon} />
            <ResearchLink href="/portfolio/dashboard" label="组合看板" icon={Activity} />
          </div>
        </motion.section>

        <motion.section variants={item} className="grid gap-4 lg:grid-cols-3">
          <LoopCard
            href="/research/thesis"
            icon={FlaskConical}
            eyebrow="THESIS"
            title="假设池"
            value={thesisSummary?.count ?? 0}
            suffix="条"
            detail={`候选 ${thesisSummary?.candidate_count ?? 0} / 验证 ${thesisSummary?.verification_count ?? 0} / 阻断 ${thesisSummary?.blocked_count ?? 0}`}
          />
          <LoopCard
            href="/research/data-quality"
            icon={ShieldCheck}
            eyebrow="DATA GATE"
            title="正式门控"
            value={`${formalReadyPct}%`}
            detail={`PASS ${gateSummary?.pass_count ?? 0} / WARN ${gateSummary?.warn_count ?? 0} / FAIL ${gateSummary?.fail_count ?? 0}`}
            danger={(gateSummary?.fail_count ?? 0) > 0 || formalReadyPct === 0}
          />
          <LoopCard
            href="/research/backtest"
            icon={BarChart3}
            eyebrow="BACKTEST"
            title="信号校准"
            value={latestBacktest?.sample_count ?? 0}
            suffix="样本"
            detail={`${latestBacktest?.horizon_days ?? 0}D / 2x ${pct(latestBacktest?.hit_rate_2x ?? 0)} / 均值 ${pct(latestBacktest?.average_forward_return ?? 0)}`}
          />
        </motion.section>

        {/* Filters Section */}
        <motion.section variants={item} className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <div className="mb-4 text-[10px] font-black uppercase tracking-widest text-slate-400">Market Universe</div>
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
                      ? "bg-indigo-600 text-white shadow-lg shadow-indigo-200" 
                      : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {marketLabel(option)}
                </button>
              ))}
            </div>
            {market === "A" && (
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
                {A_BOARD_OPTIONS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setBoard(option)}
                    className={`h-8 rounded-lg px-3 text-xs font-medium transition-all ${
                      board === option 
                        ? "bg-slate-900 text-white" 
                        : "bg-slate-50 text-slate-500 hover:bg-slate-100"
                    }`}
                  >
                    {boardLabel(option)}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <div className="mb-4 text-[10px] font-black uppercase tracking-widest text-slate-400">Task Filters</div>
            <div className="flex flex-wrap items-center gap-3">
              <select 
                className="h-10 flex-1 rounded-xl bg-slate-50 px-4 text-sm font-medium text-slate-700 outline-none ring-1 ring-slate-100 focus:ring-2 focus:ring-indigo-500/20" 
                value={priority} 
                onChange={(event) => setPriority(event.target.value)}
              >
                {PRIORITIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <select 
                className="h-10 flex-1 rounded-xl bg-slate-50 px-4 text-sm font-medium text-slate-700 outline-none ring-1 ring-slate-100 focus:ring-2 focus:ring-indigo-500/20" 
                value={taskType} 
                onChange={(event) => setTaskType(event.target.value)}
              >
                {TASK_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <label className="flex h-10 items-center gap-3 rounded-xl bg-slate-50 px-4 text-sm font-medium text-slate-600 ring-1 ring-slate-100 cursor-pointer hover:bg-slate-100 transition-colors">
                <input 
                  type="checkbox" 
                  checked={watchOnly} 
                  onChange={(event) => setWatchOnly(event.target.checked)}
                  className="size-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                <span>仅观察池候选</span>
              </label>
            </div>
          </div>
        </motion.section>

        {/* Metrics Section */}
        <motion.section variants={item} className="grid gap-4 grid-cols-2 md:grid-cols-5">
          <Metric label="任务总数" value={payload?.summary.task_count ?? 0} />
          <Metric label="涉及标的" value={payload?.summary.stock_count ?? 0} />
          <Metric label="高优先级" value={payload?.summary.high_priority_count ?? 0} highlight />
          <Metric label="验证事项" value={payload?.summary.question_task_count ?? 0} />
          <Metric label="风险核验" value={payload?.summary.risk_task_count ?? 0} danger />
        </motion.section>

        {/* Main Content Grid */}
        <motion.section variants={item} className="grid gap-8 lg:grid-cols-[400px_1fr]">
          {/* Stock Groups */}
          <div className="space-y-6">
            <div className="flex items-center gap-2 px-2">
              <LayoutGrid size={18} className="text-slate-400" />
              <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500">按股票分组</h2>
            </div>
            <div className="space-y-4">
              {grouped.map((group) => (
                <div 
                  key={group.stock_code} 
                  className="group rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 transition-all hover:shadow-lg hover:shadow-slate-200/50"
                >
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <Link 
                        href={`/stocks/${encodeURIComponent(group.stock_code)}?from=/research`} 
                        className="text-lg font-bold text-slate-900 hover:text-indigo-600 transition-colors"
                      >
                        {group.stock_name}
                      </Link>
                      <div className="text-[10px] font-black text-slate-400">{group.stock_code}</div>
                      <div className="text-[11px] font-medium text-slate-500">
                        {marketLabel(group.market)} · {boardLabel(group.board)} · {group.industry}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-black text-slate-900">{group.final_score.toFixed(1)}</div>
                      <div className="text-[10px] font-bold uppercase tracking-tighter text-slate-400">{group.tasks.length} TASKS</div>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {group.highCount > 0 && <Badge label={`高 ${group.highCount}`} tone="high" />}
                    {group.riskCount > 0 && <Badge label={`风险 ${group.riskCount}`} tone="risk" />}
                    <Badge label={group.rating} tone="neutral" />
                  </div>
                </div>
              ))}
              {grouped.length === 0 && (
                <div className="rounded-3xl border-2 border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                  当前筛选范围没有研究任务
                </div>
              )}
            </div>
          </div>

          {/* Task List */}
          <div className="space-y-6">
            <div className="flex items-center justify-between px-2">
              <div className="flex items-center gap-2">
                <List size={18} className="text-slate-400" />
                <h2 className="text-sm font-bold uppercase tracking-widest text-slate-500">任务清单</h2>
              </div>
              <div className="text-[10px] font-bold text-slate-400">最新日期: {payload?.latest_date ?? "-"}</div>
            </div>
            <div className="rounded-3xl bg-white shadow-sm ring-1 ring-slate-200 overflow-hidden divide-y divide-slate-100">
              {(payload?.tasks ?? []).map((task) => <TaskCard key={task.id} task={task} />)}
              {(payload?.tasks ?? []).length === 0 && (
                <div className="p-12 text-center text-slate-400">当前无任务数据</div>
              )}
            </div>
          </div>
        </motion.section>
      </motion.div>
    </div>
  );
}

function LoopCard({
  href,
  icon: Icon,
  eyebrow,
  title,
  value,
  suffix,
  detail,
  danger
}: {
  href: string;
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  value: string | number;
  suffix?: string;
  detail: string;
  danger?: boolean;
}) {
  return (
    <Link
      href={href}
      className="group rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 transition-all hover:-translate-y-0.5 hover:shadow-lg hover:shadow-slate-200/60"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className={`flex h-11 w-11 items-center justify-center rounded-2xl ${danger ? "bg-rose-50 text-rose-600" : "bg-indigo-50 text-indigo-600"}`}>
            <Icon size={20} />
          </div>
          <div>
            <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{eyebrow}</div>
            <div className="mt-1 text-base font-black text-slate-900">{title}</div>
          </div>
        </div>
        <ArrowRight size={17} className="text-slate-300 transition-transform group-hover:translate-x-1" />
      </div>
      <div className="mt-6 flex items-baseline gap-2">
        <span className={`text-4xl font-black tracking-tight ${danger ? "text-rose-600" : "text-slate-900"}`}>{value}</span>
        {suffix && <span className="text-xs font-bold text-slate-400">{suffix}</span>}
      </div>
      <div className="mt-3 text-xs font-semibold text-slate-500">{detail}</div>
    </Link>
  );
}

function ResearchLink({ href, label, icon: Icon }: { href: string; label: string; icon: LucideIcon }) {
  return (
    <Link
      href={href}
      className="group flex h-12 items-center gap-3 rounded-2xl bg-white px-5 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-slate-200 transition-all hover:bg-slate-50 hover:shadow-md"
    >
      <Icon size={18} className="text-indigo-600" />
      <span>{label}</span>
    </Link>
  );
}

function TaskCard({ task }: { task: ResearchTask }) {
  return (
    <article className="p-6 transition-colors hover:bg-slate-50/50">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <Badge label={priorityLabel(task.priority)} tone={task.priority} />
            <Badge label={task.task_type === "risk_review" ? "风险核验" : "验证事项"} tone={task.task_type === "risk_review" ? "risk" : "neutral"} />
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{task.trade_date}</span>
          </div>
          <h3 className="text-xl font-bold text-slate-900 tracking-tight leading-tight">{task.title}</h3>
        </div>
        <div className="text-right">
          <div className="text-2xl font-black text-slate-900">{task.priority_score.toFixed(1)}</div>
          <div className="text-[10px] font-bold uppercase tracking-widest text-slate-400">PRIORITY</div>
        </div>
      </div>
      
      <p className="mt-4 text-sm leading-relaxed text-slate-600 line-clamp-3">{task.detail}</p>
      
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MiniMetric label="最终得分" value={task.final_score.toFixed(1)} />
        <MiniMetric label="趋势趋势" value={task.trend_score.toFixed(1)} />
        <MiniMetric label="风险扣分" value={task.risk_penalty.toFixed(1)} danger={parseFloat(task.risk_penalty.toFixed(1)) > 0} />
        <MiniMetric label="RS排名" value={String(task.relative_strength_rank)} />
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-6">
        <div className="flex items-center gap-3">
          <Link 
            href={`/stocks/${encodeURIComponent(task.stock_code)}?from=/research`} 
            className="text-sm font-bold text-indigo-600 hover:text-indigo-700 transition-colors"
          >
            {task.stock_name} <span className="text-slate-400 font-medium ml-1">{task.stock_code}</span>
          </Link>
          <div className="h-4 w-px bg-slate-200" />
          <div className="text-[11px] font-semibold text-slate-500">
            {marketLabel(task.market)} / {boardLabel(task.board)} / {task.industry} / {task.rating}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <Flag active={task.is_ma_bullish} label="多头" />
          <Flag active={task.is_breakout_120d} label="120D" />
          <Flag active={task.is_breakout_250d} label="250D" />
        </div>
      </div>

      {task.source_refs.length > 0 && (
        <div className="mt-4 flex items-center gap-2 rounded-xl bg-slate-50 p-3 text-[11px] font-medium text-slate-500">
          <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Sources:</span>
          <span className="truncate">{task.source_refs.slice(0, 2).map((item) => item.title).join(" / ")}</span>
        </div>
      )}
    </article>
  );
}

function groupTasks(tasks: ResearchTask[]) {
  const groups = new Map<string, { stock_code: string; stock_name: string; market: string; board: string; industry: string; rating: string; final_score: number; highCount: number; riskCount: number; tasks: ResearchTask[] }>();
  for (const task of tasks) {
    const existing = groups.get(task.stock_code);
    if (existing) {
      existing.tasks.push(task);
      existing.highCount += task.priority === "high" ? 1 : 0;
      existing.riskCount += task.task_type === "risk_review" ? 1 : 0;
      continue;
    }
    groups.set(task.stock_code, {
      stock_code: task.stock_code,
      stock_name: task.stock_name,
      market: task.market,
      board: task.board,
      industry: task.industry,
      rating: task.rating,
      final_score: task.final_score,
      highCount: task.priority === "high" ? 1 : 0,
      riskCount: task.task_type === "risk_review" ? 1 : 0,
      tasks: [task]
    });
  }
  return [...groups.values()].sort((a, b) => b.final_score - a.final_score);
}

function Metric({ label, value, highlight, danger }: { label: string; value: string | number; highlight?: boolean; danger?: boolean }) {
  return (
    <div className="group rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 transition-all hover:shadow-lg hover:shadow-slate-200/50">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400 group-hover:text-slate-500 transition-colors">{label}</div>
      <div className={`mt-2 text-3xl font-black tracking-tight ${
        highlight ? "text-indigo-600" : danger ? "text-red-500" : "text-slate-900"
      }`}>
        {value}
      </div>
    </div>
  );
}

function MiniMetric({ label, value, danger }: { label: string; value: string; danger?: boolean }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-3 ring-1 ring-inset ring-slate-100/50">
      <div className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-1 font-bold ${danger ? "text-red-600" : "text-slate-900"}`}>{value}</div>
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: string }) {
  const getColors = () => {
    switch(tone) {
      case "high": return "bg-[#ef4444] text-white shadow-sm shadow-red-200";
      case "medium": return "bg-[#f97316] text-white shadow-sm shadow-orange-200";
      case "risk": return "bg-red-50 text-red-600 ring-1 ring-red-100";
      default: return "bg-slate-100 text-slate-600 ring-1 ring-slate-200";
    }
  };
  
  return (
    <span className={`inline-flex items-center rounded-lg px-2.5 py-1 text-[11px] font-bold uppercase tracking-tight ${getColors()}`}>
      {label}
    </span>
  );
}

function Flag({ active, label }: { active: boolean; label: string }) {
  return (
    <span className={`rounded-lg px-2.5 py-1 text-[11px] font-bold transition-all ${
      active 
        ? "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200 shadow-sm" 
        : "bg-slate-100 text-slate-400 ring-1 ring-slate-200 opacity-50"
    }`}>
      {label}
    </span>
  );
}

function priorityLabel(value: string) {
  if (value === "high") return "HIGH PRIORITY";
  if (value === "medium") return "MEDIUM";
  return "LOW";
}

function pct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}
