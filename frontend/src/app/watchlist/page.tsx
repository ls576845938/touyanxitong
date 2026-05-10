"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, CalendarDays, Repeat2 } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type WatchlistChangeRow, type WatchlistTimeline, type WatchlistTimelineItem, type WatchlistTopRow } from "@/lib/api";
import { A_BOARD_OPTIONS, MARKET_OPTIONS, boardLabel, marketLabel } from "@/lib/markets";

export default function WatchlistPage() {
  const [timeline, setTimeline] = useState<WatchlistTimeline | null>(null);
  const [market, setMarket] = useState("ALL");
  const [board, setBoard] = useState("all");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    api.watchlistTimeline({ market, board: market === "A" ? board : "all", limit: 30 })
      .then((payload) => {
        setTimeline(payload);
        setSelectedDate(payload.latest?.trade_date ?? null);
      })
      .catch((err: Error) => setError(`观察池复盘读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [market, board]);

  const selected = useMemo(() => {
    if (!timeline?.timeline.length) return null;
    return timeline.timeline.find((item) => item.trade_date === selectedDate) ?? timeline.timeline[0];
  }, [timeline, selectedDate]);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载观察池复盘" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="label">Watchlist Review</div>
        <h1 className="mt-2 text-2xl font-semibold">观察池复盘工作台</h1>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
          按交易日追踪观察池的新进、移出、评级变化和分数跃迁，帮助你先定位需要人工研究的变化，再进入单股证据链核验。
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

      {selected ? (
        <>
          <section className="grid gap-3 md:grid-cols-5">
            <Metric label="复盘日期" value={selected.trade_date} />
            <Metric label="当前观察" value={selected.summary.latest_watch_count} />
            <Metric label="新进" value={selected.summary.new_count} />
            <Metric label="移出" value={selected.summary.removed_count} />
            <Metric label="评级变化" value={selected.summary.upgraded_count + selected.summary.downgraded_count} />
          </section>

          <section className="grid gap-4 lg:grid-cols-[0.75fr_1.25fr]">
            <div className="panel p-4">
              <div className="mb-3 flex items-center gap-2 font-semibold"><CalendarDays size={18} />历史快照</div>
              <div className="space-y-2">
                {(timeline?.timeline ?? []).map((item) => (
                  <button
                    key={item.trade_date}
                    type="button"
                    onClick={() => setSelectedDate(item.trade_date)}
                    className={`w-full rounded-md border p-3 text-left ${
                      selected.trade_date === item.trade_date ? "border-mint bg-mint/10" : "border-line bg-white hover:border-mint"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="mono font-semibold">{item.trade_date}</div>
                      <div className="label">{item.previous_date ?? "首日"} 对比</div>
                    </div>
                    <div className="mt-2 grid grid-cols-4 gap-2 text-xs">
                      <MiniStat label="观察" value={item.summary.latest_watch_count} />
                      <MiniStat label="新进" value={item.summary.new_count} />
                      <MiniStat label="上升" value={item.summary.score_gainer_count} />
                      <MiniStat label="下降" value={item.summary.score_loser_count} />
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <section className="panel p-5">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-lg font-semibold"><Repeat2 size={18} />当日变化</div>
                    <p className="mt-1 text-sm text-slate-600">{selected.previous_date ?? "首日快照"} → {selected.trade_date}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-right text-sm">
                    <MiniStat label="分数增强" value={selected.summary.score_gainer_count} />
                    <MiniStat label="分数走弱" value={selected.summary.score_loser_count} />
                  </div>
                </div>
                <div className="grid gap-3 lg:grid-cols-2">
                  <ChangeSection title="新进观察" rows={selected.new_entries} />
                  <ChangeSection title="评级上调" rows={selected.upgraded} />
                  <ChangeSection title="评分上升" rows={selected.score_gainers} icon="up" />
                  <ChangeSection title="移出/降级" rows={[...selected.removed_entries, ...selected.downgraded]} icon="down" />
                </div>
              </section>

              <section className="panel overflow-hidden">
                <div className="border-b border-line p-5">
                  <h2 className="text-lg font-semibold">当前观察池 Top</h2>
                  <p className="mt-1 text-sm text-slate-600">按最新总分排序，点击股票进入证据链页面。</p>
                </div>
                <TopTable rows={selected.watchlist_top} />
              </section>
            </div>
          </section>
        </>
      ) : (
        <section className="panel p-5 text-sm text-slate-600">当前筛选范围没有可复盘的观察池记录。</section>
      )}
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

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-line bg-white px-2 py-1">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{value}</div>
    </div>
  );
}

function ChangeSection({ title, rows, icon = "up" }: { title: string; rows: WatchlistChangeRow[]; icon?: "up" | "down" }) {
  const Icon = icon === "up" ? ArrowUpRight : ArrowDownRight;
  return (
    <div className="rounded-md border border-line bg-slate-50 p-3">
      <div className="mb-2 flex items-center gap-2 font-medium"><Icon size={16} />{title}</div>
      <div className="space-y-2">
        {rows.slice(0, 8).map((row) => (
          <Link key={`${title}-${row.code}-${row.change_type}`} href={`/stocks/${encodeURIComponent(row.code)}?from=/watchlist`} className="block rounded-md bg-white px-3 py-2 text-sm hover:text-mint">
            <div className="flex items-center justify-between gap-3">
              <div className="font-medium">{row.name}<span className="label ml-2">{row.code}</span></div>
              <div className="mono font-semibold">{formatScore(row.final_score ?? row.previous_score)}</div>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>{marketLabel(row.market)} / {boardLabel(row.board)}</span>
              <span>{row.previous_rating ?? "-"} → {row.rating ?? "-"}</span>
              <span>{formatDelta(row.score_delta)}</span>
            </div>
          </Link>
        ))}
        {rows.length === 0 ? <div className="rounded-md bg-white px-3 py-2 text-sm text-slate-600">暂无变化。</div> : null}
      </div>
    </div>
  );
}

function TopTable({ rows }: { rows: WatchlistTopRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-4 py-3">股票</th>
            <th className="px-4 py-3">市场</th>
            <th className="px-4 py-3">产业</th>
            <th className="px-4 py-3">等级</th>
            <th className="px-4 py-3 text-right">总分</th>
            <th className="px-4 py-3 text-right">产业</th>
            <th className="px-4 py-3 text-right">公司</th>
            <th className="px-4 py-3 text-right">趋势</th>
            <th className="px-4 py-3 text-right">风险</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.code} className="border-t border-line">
              <td className="px-4 py-3 font-medium"><Link href={`/stocks/${encodeURIComponent(row.code)}?from=/watchlist`} className="hover:text-mint">{row.name}<span className="label ml-2">{row.code}</span></Link></td>
              <td className="px-4 py-3">{marketLabel(row.market)}<div className="label">{boardLabel(row.board)}</div></td>
              <td className="px-4 py-3">{row.industry}</td>
              <td className="px-4 py-3">{row.rating}</td>
              <td className="mono px-4 py-3 text-right font-semibold">{row.final_score.toFixed(1)}</td>
              <td className="mono px-4 py-3 text-right">{row.industry_score.toFixed(1)}</td>
              <td className="mono px-4 py-3 text-right">{row.company_score.toFixed(1)}</td>
              <td className="mono px-4 py-3 text-right">{row.trend_score.toFixed(1)}</td>
              <td className="mono px-4 py-3 text-right">{row.risk_penalty.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatScore(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : value.toFixed(1);
}

function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return "new";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}
