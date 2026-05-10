"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Clipboard, FileText, Filter } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type ResearchBrief } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

export default function ResearchBriefPage() {
  const [brief, setBrief] = useState<ResearchBrief | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [watchOnly, setWatchOnly] = useState(true);
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

  if (loading) return <div className="page-shell"><LoadingState label="正在生成研究工作单" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;
  if (!brief) return <div className="page-shell"><ErrorState message="研究工作单为空" /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="label">Research Brief</div>
            <h1 className="mt-2 text-2xl font-semibold">每日研究工作单</h1>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
              将研究任务按优先级、股票和赛道汇总为可执行工作单。用于人工核验证据，不构成交易指令。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={copyMarkdown} className="inline-flex h-10 items-center gap-2 rounded-md bg-mint px-4 text-sm text-white">
              <Clipboard size={16} /> {copied ? "已复制" : "复制 Markdown"}
            </button>
            <Link href="/research" className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-4 text-sm hover:border-mint">
              <FileText size={16} /> 任务中心
            </Link>
          </div>
        </div>
      </section>

      <section className="panel p-4">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><Filter size={16} />工作单范围</div>
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
          <label className="ml-auto flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm">
            <input type="checkbox" checked={watchOnly} onChange={(event) => setWatchOnly(event.target.checked)} />
            仅观察池候选
          </label>
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

      <section className="grid gap-3 md:grid-cols-5">
        <Metric label="日期" value={brief.latest_date ?? "-"} />
        <Metric label="任务数" value={brief.summary.task_count} />
        <Metric label="涉及股票" value={brief.summary.stock_count} />
        <Metric label="高优先级" value={brief.summary.high_priority_count} />
        <Metric label="风险核验" value={brief.summary.risk_task_count} />
      </section>

      <section className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-4">
          <section className="panel p-5">
            <h2 className="text-lg font-semibold">重点股票</h2>
            <div className="mt-4 space-y-3">
              {brief.focus_stocks.slice(0, 10).map((row) => (
                <Link key={row.stock_code} href={`/stocks/${encodeURIComponent(row.stock_code)}?from=/research/brief`} className="block rounded-md border border-line bg-slate-50 p-3 hover:border-mint">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{row.stock_name}<span className="label ml-2">{row.stock_code}</span></div>
                      <div className="label mt-1">{marketLabel(row.market)} / {boardLabel(row.board)} / {row.industry} / {row.rating}</div>
                    </div>
                    <div className="mono text-right">
                      <div className="font-semibold">{row.final_score.toFixed(1)}</div>
                      <div className="label">任务 {row.task_count}</div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {row.top_task_titles.slice(0, 3).map((title) => <span key={`${row.stock_code}-${title}`} className="rounded-md bg-white px-2 py-1 text-xs">{title}</span>)}
                  </div>
                </Link>
              ))}
            </div>
          </section>

          <section className="panel p-5">
            <h2 className="text-lg font-semibold">赛道分布</h2>
            <div className="mt-4 space-y-3">
              {brief.focus_industries.map((row) => (
                <div key={row.industry} className="rounded-md border border-line bg-slate-50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="font-medium">{row.industry}</div>
                    <div className="mono text-sm font-semibold">{row.average_priority_score.toFixed(1)}</div>
                  </div>
                  <div className="label mt-1">任务 {row.task_count} / 股票 {row.stock_count} / 高优先级 {row.high_priority_count} / 风险 {row.risk_task_count}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {row.top_stocks.map((stock) => (
                      <Link key={`${row.industry}-${stock.stock_code}`} href={`/stocks/${encodeURIComponent(stock.stock_code)}?from=/research/brief`} className="rounded-md bg-white px-2 py-1 text-xs hover:text-mint">
                        {stock.stock_name} {stock.final_score.toFixed(1)}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <section className="panel overflow-hidden">
          <div className="border-b border-line p-5">
            <h2 className="text-lg font-semibold">Markdown 工作单</h2>
            <p className="mt-1 text-sm text-slate-600">用于当天投研记录、复盘和人工核验。</p>
          </div>
          <pre className="max-h-[920px] overflow-auto whitespace-pre-wrap bg-slate-50 p-5 text-sm leading-7 text-slate-800">
            {brief.markdown}
          </pre>
        </section>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="panel p-4">
      <div className="label">{label}</div>
      <div className="mono mt-2 text-xl font-semibold">{value}</div>
    </div>
  );
}
