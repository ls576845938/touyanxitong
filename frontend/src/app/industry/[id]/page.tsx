"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Newspaper, Tags } from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { IndustryDetailHeatChart } from "@/components/IndustryDetailHeatChart";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { api, type IndustryDetail, type IndustryDetailStock } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

export default function IndustryDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const market = searchParams.get("market") ?? "ALL";
  const [detail, setDetail] = useState<IndustryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const removedRoute = params.id === "chain-cockpit";

  useEffect(() => {
    if (removedRoute) {
      setLoading(false);
      setDetail(null);
      setError("");
      return;
    }
    setLoading(true);
    setError("");
    api.industryDetail(params.id, { market })
      .then(setDetail)
      .catch((err: Error) => setError(`赛道详情读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [params.id, market, removedRoute]);

  if (removedRoute) return <div className="page-shell"><ErrorState message="该页面已删除" /></div>;
  if (loading) return <div className="page-shell"><LoadingState label="正在加载赛道详情" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;
  if (!detail) return <div className="page-shell"><ErrorState message="赛道详情为空" /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="label">Industry Detail</div>
            <h1 className="mt-2 text-2xl font-semibold">{detail.industry.name}</h1>
            <div className="label mt-2">{detail.summary.market_label} 关联股票视图</div>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">{detail.industry.description}</p>
          </div>
          <div className="rounded-md bg-mint px-4 py-2 text-white">
            <div className="label text-white/80">最新热度</div>
            <div className="mono text-2xl font-semibold">{detail.latest_heat?.heat_score.toFixed(1) ?? "-"}</div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {detail.industry.keywords.map((keyword) => (
            <span key={keyword} className="rounded-md border border-line px-2 py-1 text-xs">{keyword}</span>
          ))}
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-5">
        <Metric label="关联股票" value={detail.summary.related_stock_count} />
        <Metric label="观察候选" value={detail.summary.watch_stock_count} />
        <Metric label="强观察" value={detail.summary.strong_watch_count} />
        <Metric label="相关新闻" value={detail.summary.recent_article_count} />
        <Metric label="热度变化" value={formatDelta(detail.latest_heat?.heat_score_delta)} />
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="panel p-5">
          <h2 className="text-lg font-semibold">热度历史</h2>
          <p className="mt-1 text-sm text-slate-600">热度分、7日热度和30日热度变化，用于判断赛道是否持续升温。</p>
          <div className="mt-4"><IndustryDetailHeatChart rows={detail.heat_history} /></div>
        </div>
        <div className="panel p-5">
          <div className="flex items-center gap-2 text-lg font-semibold"><Tags size={18} />最新热度拆解</div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
            <MiniMetric label="1日" value={detail.latest_heat?.heat_1d.toFixed(1) ?? "-"} />
            <MiniMetric label="7日" value={detail.latest_heat?.heat_7d.toFixed(1) ?? "-"} />
            <MiniMetric label="30日" value={detail.latest_heat?.heat_30d.toFixed(1) ?? "-"} />
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-600">{detail.latest_heat?.explanation ?? "暂无热度解释。"}</p>
          <div className="mt-4 space-y-2">
            {(detail.latest_heat?.top_articles ?? []).slice(0, 4).map((title) => (
              <div key={title} className="rounded-md border border-line bg-slate-50 p-3 text-sm">{title}</div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel overflow-hidden">
        <div className="border-b border-line p-5">
          <h2 className="text-lg font-semibold">赛道关联股票</h2>
          <p className="mt-1 text-sm text-slate-600">按最新评分排序。这里只是研究线索，不构成买卖建议。</p>
        </div>
        <StockTable rows={detail.related_stocks} industryId={params.id} />
      </section>

      <section className="panel p-5">
        <div className="mb-4 flex items-center gap-2 text-lg font-semibold"><Newspaper size={18} />相关新闻证据</div>
        <div className="grid gap-3 lg:grid-cols-2">
          {detail.recent_articles.map((article) => (
            <article key={article.source_url} className="rounded-md border border-line bg-slate-50 p-4">
              <div className="font-medium">{article.title}</div>
              <p className="mt-2 text-sm leading-6 text-slate-600">{article.summary}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {article.matched_keywords.slice(0, 6).map((keyword) => <span key={keyword} className="rounded-md bg-white px-2 py-1 text-xs">{keyword}</span>)}
              </div>
              <div className="label mt-3">{article.source} / {article.published_at.slice(0, 10)} / {article.source_url}</div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function StockTable({ rows, industryId }: { rows: IndustryDetailStock[]; industryId: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1080px] text-left text-sm">
        <thead className="bg-slate-50 text-slate-500">
          <tr>
            <th className="px-4 py-3">股票</th>
            <th className="px-4 py-3">市场</th>
            <th className="px-4 py-3">环节</th>
            <th className="px-4 py-3">评分</th>
            <th className="px-4 py-3 text-right">产业</th>
            <th className="px-4 py-3 text-right">公司</th>
            <th className="px-4 py-3 text-right">趋势</th>
            <th className="px-4 py-3 text-right">风险</th>
            <th className="px-4 py-3">形态</th>
            <th className="px-4 py-3">证据链</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.code} className="border-t border-line align-top">
              <td className="px-4 py-3">
                <div className="font-medium">{row.name}</div>
                <div className="label">{row.code}</div>
              </td>
              <td className="px-4 py-3">{marketLabel(row.market)}<div className="label">{boardLabel(row.board)} / {row.exchange}</div></td>
              <td className="px-4 py-3">{row.industry_level2}<Concepts items={row.concepts} /></td>
              <td className="px-4 py-3"><ScoreBadge score={row.final_score} rating={row.rating} /></td>
              <td className="mono px-4 py-3 text-right">{formatNumber(row.industry_score)}</td>
              <td className="mono px-4 py-3 text-right">{formatNumber(row.company_score)}</td>
              <td className="mono px-4 py-3 text-right">{formatNumber(row.trend_score)}</td>
              <td className="mono px-4 py-3 text-right">{formatNumber(row.risk_penalty)}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1.5">
                  <Flag active={row.is_ma_bullish} label="多头" />
                  <Flag active={row.is_breakout_120d} label="120新高" />
                  <Flag active={row.is_breakout_250d} label="250新高" />
                </div>
              </td>
              <td className="px-4 py-3"><Link href={`/stocks/${encodeURIComponent(row.code)}?from=/industry/${industryId}`} className="text-mint">查看</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Concepts({ items }: { items: string[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {items.slice(0, 4).map((item) => <span key={item} className="rounded-md border border-line px-2 py-1 text-xs text-slate-600">{item}</span>)}
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

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{value}</div>
    </div>
  );
}

function Flag({ active, label }: { active: boolean | null; label: string }) {
  return <span className={`rounded-md px-2 py-1 text-xs ${active ? "bg-mint text-white" : "bg-slate-100 text-slate-500"}`}>{label}</span>;
}

function formatNumber(value: number | null) {
  return value === null ? "-" : value.toFixed(1);
}

function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return "new";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}
