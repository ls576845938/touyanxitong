"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ClipboardCheck, FileText, Filter } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type ResearchTask, type ResearchTasks } from "@/lib/api";
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

export default function ResearchPage() {
  const [payload, setPayload] = useState<ResearchTasks | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [priority, setPriority] = useState("all");
  const [taskType, setTaskType] = useState("all");
  const [watchOnly, setWatchOnly] = useState(true);
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

  const grouped = useMemo(() => groupTasks(payload?.tasks ?? []), [payload]);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载研究任务中心" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="label">Research Tasks</div>
            <h1 className="mt-2 text-2xl font-semibold">研究任务中心</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
              将观察池候选的待验证事项和风险摘要转成每日投研清单。这里只做研究辅助，不输出买入、卖出、目标价或收益承诺。
            </p>
          </div>
          <Link href="/research/brief" className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-4 text-sm hover:border-mint">
            <FileText size={16} /> 今日工作单
          </Link>
        </div>
      </section>

      <section className="panel p-4">
        <div className="flex flex-wrap items-center gap-2">
          {MARKET_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setMarket(option);
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
                onClick={() => setBoard(option)}
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
          <div className="flex items-center gap-2 text-sm font-semibold"><Filter size={16} />任务筛选</div>
          <select className="h-10 rounded-md border border-line bg-white px-3 text-sm" value={priority} onChange={(event) => setPriority(event.target.value)}>
            {PRIORITIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <select className="h-10 rounded-md border border-line bg-white px-3 text-sm" value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            {TASK_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <label className="flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm">
            <input type="checkbox" checked={watchOnly} onChange={(event) => setWatchOnly(event.target.checked)} />
            仅观察池候选
          </label>
          <div className="label ml-auto">最新日期 {payload?.latest_date ?? "-"}</div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-5">
        <Metric label="任务数" value={payload?.summary.task_count ?? 0} />
        <Metric label="涉及股票" value={payload?.summary.stock_count ?? 0} />
        <Metric label="高优先级" value={payload?.summary.high_priority_count ?? 0} />
        <Metric label="验证事项" value={payload?.summary.question_task_count ?? 0} />
        <Metric label="风险核验" value={payload?.summary.risk_task_count ?? 0} />
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="panel p-5">
          <div className="mb-4 flex items-center gap-2 text-lg font-semibold"><ClipboardCheck size={18} />按股票分组</div>
          <div className="space-y-3">
            {grouped.map((group) => (
              <div key={group.stock_code} className="rounded-md border border-line bg-slate-50 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <Link href={`/stocks/${encodeURIComponent(group.stock_code)}?from=/research`} className="font-medium hover:text-mint">{group.stock_name}<span className="label ml-2">{group.stock_code}</span></Link>
                    <div className="label mt-1">{marketLabel(group.market)} / {boardLabel(group.board)} / {group.industry}</div>
                  </div>
                  <div className="mono text-right">
                    <div className="font-semibold">{group.final_score.toFixed(1)}</div>
                    <div className="label">{group.tasks.length} 项</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge label={`高 ${group.highCount}`} tone="high" />
                  <Badge label={`风险 ${group.riskCount}`} tone="risk" />
                  <Badge label={group.rating} tone="neutral" />
                </div>
              </div>
            ))}
            {grouped.length === 0 ? <div className="rounded-md border border-line bg-slate-50 p-3 text-sm text-slate-600">当前筛选范围没有研究任务。</div> : null}
          </div>
        </div>

        <div className="panel overflow-hidden">
          <div className="border-b border-line p-5">
            <h2 className="text-lg font-semibold">任务清单</h2>
            <p className="mt-1 text-sm text-slate-600">按优先级排序。点击股票进入证据链核验，点击赛道进入赛道详情。</p>
          </div>
          <div className="divide-y divide-line">
            {(payload?.tasks ?? []).map((task) => <TaskCard key={task.id} task={task} />)}
            {(payload?.tasks ?? []).length === 0 ? <div className="p-5 text-sm text-slate-600">当前无任务。</div> : null}
          </div>
        </div>
      </section>
    </div>
  );
}

function TaskCard({ task }: { task: ResearchTask }) {
  return (
    <article className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge label={priorityLabel(task.priority)} tone={task.priority} />
            <Badge label={task.task_type === "risk_review" ? "风险核验" : "验证事项"} tone={task.task_type === "risk_review" ? "risk" : "neutral"} />
            <span className="label">{task.trade_date}</span>
          </div>
          <h3 className="mt-2 text-base font-semibold">{task.title}</h3>
        </div>
        <div className="mono text-right">
          <div className="text-lg font-semibold">{task.priority_score.toFixed(1)}</div>
          <div className="label">优先级分</div>
        </div>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-700">{task.detail}</p>
      <div className="mt-4 grid gap-2 md:grid-cols-4">
        <MiniMetric label="最终分" value={task.final_score.toFixed(1)} />
        <MiniMetric label="趋势分" value={task.trend_score.toFixed(1)} />
        <MiniMetric label="风险扣分" value={task.risk_penalty.toFixed(1)} />
        <MiniMetric label="RS排名" value={String(task.relative_strength_rank)} />
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
        <div>
          <Link href={`/stocks/${encodeURIComponent(task.stock_code)}?from=/research`} className="font-medium text-mint">{task.stock_name} {task.stock_code}</Link>
          <span className="label ml-2">{marketLabel(task.market)} / {boardLabel(task.board)} / {task.industry} / {task.rating}</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <Flag active={task.is_ma_bullish} label="多头" />
          <Flag active={task.is_breakout_120d} label="120新高" />
          <Flag active={task.is_breakout_250d} label="250新高" />
        </div>
      </div>
      {task.source_refs.length ? (
        <div className="mt-3 rounded-md border border-line bg-slate-50 p-3 text-xs text-slate-600">
          证据来源：{task.source_refs.slice(0, 2).map((item) => item.title).join(" / ")}
        </div>
      ) : null}
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

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="panel p-4">
      <div className="label">{label}</div>
      <div className="mono mt-2 text-xl font-semibold">{value}</div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-slate-50 p-3">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{value}</div>
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: string }) {
  const className =
    tone === "high"
      ? "bg-rose text-white"
      : tone === "medium"
        ? "bg-amber text-white"
        : tone === "risk"
          ? "bg-rose/10 text-rose"
          : "bg-slate-100 text-slate-600";
  return <span className={`rounded-md px-2 py-1 text-xs font-medium ${className}`}>{label}</span>;
}

function Flag({ active, label }: { active: boolean; label: string }) {
  return <span className={`rounded-md px-2 py-1 ${active ? "bg-mint text-white" : "bg-slate-100 text-slate-500"}`}>{label}</span>;
}

function priorityLabel(value: string) {
  if (value === "high") return "高优先级";
  if (value === "medium") return "中优先级";
  return "低优先级";
}
