"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, ArrowRight, CheckCircle2, Database, History, RotateCcw } from "lucide-react";
import { CandleChart } from "@/components/CandleChart";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { ScoreBadge } from "@/components/ScoreBadge";
import { StockSearch } from "@/components/StockSearch";
import { api, type BarRow, type IngestionTask, type InstrumentNavigation, type SourceComparison, type StockEvidence, type StockHistory } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

export default function StockEvidencePage() {
  const params = useParams<{ code: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const code = params.code;
  const [evidence, setEvidence] = useState<StockEvidence | null>(null);
  const [history, setHistory] = useState<StockHistory | null>(null);
  const [bars, setBars] = useState<BarRow[]>([]);
  const [sourceComparison, setSourceComparison] = useState<SourceComparison | null>(null);
  const [navigation, setNavigation] = useState<InstrumentNavigation | null>(null);
  const [ingestionTask, setIngestionTask] = useState<IngestionTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError("");
    Promise.all([api.stockEvidence(code), api.stockHistory(code), api.stockBars(code), api.sourceComparison(code), api.instrumentNavigation(code)])
      .then(([evidenceData, historyData, barRows, sourceRows, navigationData]) => {
        setEvidence(evidenceData);
        setHistory(historyData);
        setBars(barRows);
        setSourceComparison(sourceRows);
        setNavigation(navigationData);
      })
      .catch((err: Error) => setError(`证据链读取失败：${err.message}`))
      .finally(() => setLoading(false));
  }, [code, refreshKey]);

  const ingestThisStock = () => {
    setIngesting(true);
    setError("");
    api.ingestStock(code)
      .then((task) => {
        setIngestionTask(task);
        setRefreshKey((value) => value + 1);
      })
      .catch((err: Error) => setError(`单票行情补齐失败：${err.message}`))
      .finally(() => setIngesting(false));
  };

  if (loading) return <div className="page-shell"><LoadingState label="正在加载单股证据链" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;
  if (!evidence) return <div className="page-shell"><ErrorState message="证据链为空" /></div>;
  const from = searchParams.get("from");

  return (
    <div className="page-shell space-y-5">
      <section className="panel p-4">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-center">
          <StockSearch placeholder="切换股票：输入代码或名称" />
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => router.back()} className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm hover:border-mint">
              <RotateCcw size={16} />返回上一页
            </button>
            {from && from !== "search" ? (
              <Link href={from} className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm hover:border-mint">
                <ArrowLeft size={16} />返回来源
              </Link>
            ) : null}
            {navigation?.previous ? (
              <Link href={`/stocks/${encodeURIComponent(navigation.previous.code)}?from=/stocks/${encodeURIComponent(code)}`} className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm hover:border-mint">
                <ArrowLeft size={16} />上一只
              </Link>
            ) : null}
            {navigation?.next ? (
              <Link href={`/stocks/${encodeURIComponent(navigation.next.code)}?from=/stocks/${encodeURIComponent(code)}`} className="inline-flex h-10 items-center gap-2 rounded-md border border-line px-3 text-sm hover:border-mint">
                下一只<ArrowRight size={16} />
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="label">Stock Evidence</div>
            <h1 className="mt-2 text-2xl font-semibold">{evidence.stock.name} <span className="text-slate-500">{evidence.stock.code}</span></h1>
            <div className="mt-2 text-sm text-slate-600">
              {marketLabel(evidence.stock.market)} / {boardLabel(evidence.stock.board)} / {evidence.stock.exchange} / {evidence.stock.industry_level1} / {evidence.stock.industry_level2}
            </div>
          </div>
          <ScoreBadge score={evidence.score.final_score} rating={evidence.score.rating} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {evidence.stock.concepts.map((concept) => (
            <span key={concept} className="rounded-md border border-line px-2 py-1 text-xs">{concept}</span>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2 text-sm">
          <a href="#chart" className="rounded-md border border-line px-3 py-2 hover:border-mint">K线与数据</a>
          <a href="#score" className="rounded-md border border-line px-3 py-2 hover:border-mint">评分拆解</a>
          <a href="#evidence" className="rounded-md border border-line px-3 py-2 hover:border-mint">证据链</a>
          <a href="#risk" className="rounded-md border border-line px-3 py-2 hover:border-mint">风险与待验证</a>
          <a href="#sources" className="rounded-md border border-line px-3 py-2 hover:border-mint">数据来源</a>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-4">
        <Metric label="评分可信度" value={`${evidence.score.confidence.level} / ${formatPct(evidence.score.confidence.combined_confidence)}`} />
        <Metric label="研究准入" value={evidence.score.research_gate.passed ? "通过" : "复核"} />
        <Metric label="基本面" value={`${fundamentalLabel(evidence.score.fundamental_summary.status)} ${formatPct(evidence.score.fundamental_summary.confidence)}`} />
        <Metric label="资讯证据" value={evidenceStatusLabel(evidence.score.news_evidence_status)} />
      </section>

      {bars.length === 0 ? (
        <section className="panel border-amber/40 bg-amber/10 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-semibold">该标的尚未下载可用 K 线</div>
              <p className="mt-1 text-sm text-slate-700">可以先补齐单票行情。任务完成后本页会刷新图表和数据源记录。</p>
            </div>
            <button type="button" onClick={ingestThisStock} disabled={ingesting} className="rounded-md bg-mint px-4 py-2 text-sm text-white disabled:opacity-50">
              {ingesting ? "正在补齐..." : "立即补齐"}
            </button>
          </div>
        </section>
      ) : null}

      <section className="grid gap-4 lg:grid-cols-[1.4fr_0.8fr]">
        <div id="chart" className="panel scroll-mt-4 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">K线趋势</h2>
            <button type="button" onClick={ingestThisStock} disabled={ingesting} className="rounded-md border border-line px-3 py-2 text-sm hover:border-mint disabled:opacity-50">
              {ingesting ? "正在补齐..." : "补齐该股票K线"}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
            {(sourceComparison?.sources ?? []).map((source) => (
              <span key={source.source} className="rounded-md border border-line bg-slate-50 px-2 py-1">
                {source.source}: {source.bars_count} 根 / {source.latest_trade_date ?? "-"}
              </span>
            ))}
            {(sourceComparison?.sources ?? []).length === 0 ? <span className="rounded-md border border-line bg-slate-50 px-2 py-1">暂无行情源记录</span> : null}
          </div>
          {ingestionTask ? (
            <div className="mt-3 rounded-md border border-line bg-slate-50 p-3 text-sm">
              任务 {ingestionTask.status}：requested {ingestionTask.requested} / processed {ingestionTask.processed} / failed {ingestionTask.failed}
              {ingestionTask.error ? <span className="ml-2 text-rose">{ingestionTask.error}</span> : null}
            </div>
          ) : null}
          <div className="mt-4"><CandleChart rows={bars} /></div>
        </div>
        <div id="score" className="panel scroll-mt-4 p-5">
          <h2 className="text-lg font-semibold">评分拆解</h2>
          <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
            <MiniConfidence label="数据源" value={evidence.score.confidence.source_confidence} />
            <MiniConfidence label="数据" value={evidence.score.confidence.data_confidence} />
            <MiniConfidence label="基本面" value={evidence.score.confidence.fundamental_confidence} />
            <MiniConfidence label="资讯" value={evidence.score.confidence.news_confidence} />
          </div>
          <div className="mt-4 space-y-3">
            <ScoreRow label="产业趋势" value={evidence.score.industry_score} />
            <ScoreRow label="公司质量" value={evidence.score.company_score} />
            <ScoreRow label="股价趋势" value={evidence.score.trend_score} />
            <ScoreRow label="信息催化" value={evidence.score.catalyst_score} />
            <ScoreRow label="风险扣分" value={evidence.score.risk_penalty} negative />
          </div>
          <p className="mt-5 text-sm leading-6 text-slate-600">{evidence.score.explanation}</p>
        </div>
      </section>

      <section className="panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold"><History size={18} />评分时间线</div>
            <p className="mt-2 text-sm text-slate-600">按交易日追踪评分、趋势事件、风险摘要和证据链变化，用于复盘观察池质量。</p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-right text-sm">
            <Metric label="快照" value={String(history?.history.length ?? 0)} />
            <Metric label="最新评分" value={formatNumber(history?.latest?.final_score)} />
            <Metric label="分数变化" value={formatDelta(history?.latest?.score_delta)} />
          </div>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-[980px] w-full text-left text-sm">
            <thead className="border-b border-line text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-3">日期</th>
                <th className="py-2 pr-3">等级</th>
                <th className="py-2 pr-3 text-right">总分</th>
                <th className="py-2 pr-3 text-right">变化</th>
                <th className="py-2 pr-3 text-right">趋势分</th>
                <th className="py-2 pr-3 text-right">RS排名</th>
                <th className="py-2 pr-3">趋势事件</th>
                <th className="py-2">证据摘要</th>
              </tr>
            </thead>
            <tbody>
              {(history?.history ?? []).map((row) => (
                <tr key={row.trade_date} className="border-b border-line/70 align-top">
                  <td className="py-3 pr-3 mono text-xs text-slate-600">{row.trade_date}</td>
                  <td className="py-3 pr-3 font-medium">{row.rating}</td>
                  <td className="py-3 pr-3 text-right mono">{formatNumber(row.final_score)}</td>
                  <td className={`py-3 pr-3 text-right mono ${deltaClass(row.score_delta)}`}>{formatDelta(row.score_delta)}</td>
                  <td className="py-3 pr-3 text-right mono">{formatNumber(row.trend_score)}</td>
                  <td className="py-3 pr-3 text-right mono">{row.relative_strength_rank ?? "-"}</td>
                  <td className="py-3 pr-3">
                    <div className="flex flex-wrap gap-1.5">
                      <Flag active={row.is_ma_bullish} label="均线多头" />
                      <Flag active={row.is_breakout_120d} label="120日突破" />
                      <Flag active={row.is_breakout_250d} label="250日突破" />
                    </div>
                    <div className="mt-2 text-xs text-slate-500">
                      放量 {formatNumber(row.volume_expansion_ratio)}x / 60日回撤 {formatNumber(row.max_drawdown_60d)}%
                    </div>
                  </td>
                  <td className="py-3 text-slate-700">
                    <div className="line-clamp-2 leading-6">{row.summary || row.score_explanation}</div>
                    {row.risk_summary ? <div className="mt-1 line-clamp-1 text-xs text-rose">{row.risk_summary}</div> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="evidence" className="grid scroll-mt-4 gap-4 lg:grid-cols-2">
        <EvidencePanel title="产业逻辑" text={evidence.evidence.industry_logic} />
        <EvidencePanel title="公司逻辑" text={evidence.evidence.company_logic} />
        <EvidencePanel title="趋势逻辑" text={evidence.evidence.trend_logic} />
        <EvidencePanel title="催化逻辑" text={evidence.evidence.catalyst_logic} />
      </section>

      <section id="risk" className="grid scroll-mt-4 gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="panel p-5">
          <div className="flex items-center gap-2 text-lg font-semibold text-rose"><AlertTriangle size={18} />风险提示</div>
          <p className="mt-4 text-sm leading-6 text-slate-700">{evidence.evidence.risk_summary}</p>
        </div>
        <div className="panel p-5">
          <div className="flex items-center gap-2 text-lg font-semibold"><CheckCircle2 size={18} />待验证事项</div>
          <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-700">
            {evidence.evidence.questions_to_verify.map((question) => <li key={question}>- {question}</li>)}
          </ul>
        </div>
      </section>

      <section id="sources" className="panel scroll-mt-4 p-5">
          <div className="flex items-center gap-2 text-lg font-semibold"><Database size={18} />证据与数据来源</div>
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          <MiniStatus label="证据状态" value={evidenceStatusLabel(evidence.evidence.evidence_status)} />
          <MiniStatus label="来源可信度" value={formatPct(evidence.score.confidence.source_confidence)} />
          <MiniStatus label="资讯可信度" value={formatPct(evidence.score.confidence.news_confidence)} />
        </div>
        <div className="mt-4 space-y-2 text-sm">
          {evidence.evidence.source_refs.map((ref) => (
            <div key={`${ref.source}-${ref.url}`} className="rounded-md border border-line p-3">
              <div className="font-medium">{ref.title}</div>
              <div className="label mt-1">{ref.source} / {ref.url}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line px-3 py-2">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{value}</div>
    </div>
  );
}

function ScoreRow({ label, value, negative = false }: { label: string; value: number | null; negative?: boolean }) {
  const width = Math.max(0, Math.min(100, ((value ?? 0) / (negative ? 10 : 30)) * 100));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span>{label}</span>
        <span className="mono font-semibold">{value?.toFixed(1) ?? "-"}</span>
      </div>
      <div className="h-2 rounded-full bg-slate-100">
        <div className={`h-2 rounded-full ${negative ? "bg-rose" : "bg-mint"}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function MiniConfidence({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-md bg-slate-50 px-3 py-2">
      <div className="label">{label}</div>
      <div className="mono mt-1 font-semibold">{formatPct(value)}</div>
    </div>
  );
}

function MiniStatus({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-slate-50 px-3 py-2 text-sm">
      <span className="label mr-2">{label}</span>{value}
    </div>
  );
}

function Flag({ active, label }: { active: boolean | null; label: string }) {
  return <span className={`rounded px-2 py-1 text-xs ${active ? "bg-mint/15 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{label}</span>;
}

function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "-" : value.toFixed(1);
}

function formatPct(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "-";
}

function fundamentalLabel(status: string) {
  if (status === "complete") return "完整";
  if (status === "partial") return "部分";
  return "未知";
}

function evidenceStatusLabel(status: string | null | undefined) {
  if (status === "active" || status === "sourced") return "来源充分";
  if (status === "partial" || status === "needs_verification") return "待验证";
  return "缺失";
}

function formatDelta(value: number | null | undefined) {
  if (value === null || value === undefined) return "首日";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function deltaClass(value: number | null | undefined) {
  if (value === null || value === undefined) return "text-slate-500";
  if (value > 0) return "text-emerald-700";
  if (value < 0) return "text-rose";
  return "text-slate-600";
}

function EvidencePanel({ title, text }: { title: string; text: string }) {
  return (
    <article className="panel p-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-slate-700">{text}</p>
    </article>
  );
}
