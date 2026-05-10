"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  Building2,
  CalendarRange,
  CircleGauge,
  Flame,
  Globe2,
  Layers3,
  Search,
  TrendingUp
} from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { IndustryChainMap } from "@/components/IndustryChainMap";
import { IndustryGraphMap } from "@/components/IndustryGraphMap";
import { IndustryPlaneHeatMap } from "@/components/IndustryPlaneHeatMap";
import { LoadingState } from "@/components/LoadingState";
import { WorldIndustryHeatMap } from "@/components/WorldIndustryHeatMap";
import { api, type ChainLayer, type ChainMappedIndustry, type ChainNode, type ChainNodeDetail, type ChainTimelinePoint } from "@/lib/api";
import { MARKET_OPTIONS, marketLabel } from "@/lib/markets";

type LayerOption = {
  key: string;
  label: string;
  count?: number | null;
};

type ViewMode = "graph" | "focus" | "heatmap" | "geo";

const VIEW_OPTIONS: { key: ViewMode; label: string; icon: typeof Layers3 }[] = [
  { key: "graph", label: "总图热力", icon: Layers3 },
  { key: "focus", label: "聚焦链路", icon: Activity },
  { key: "heatmap", label: "平面总谱", icon: Boxes },
  { key: "geo", label: "世界分布", icon: Globe2 }
];

export default function IndustryChainPage() {
  const [market, setMarket] = useState("ALL");
  const [query, setQuery] = useState("");
  const [activeLayer, setActiveLayer] = useState("all");
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [focusNodeKey, setFocusNodeKey] = useState<string | null>(null);

  const [overview, setOverview] = useState<Awaited<ReturnType<typeof api.chainOverview>> | null>(null);
  const [detail, setDetail] = useState<ChainNodeDetail | null>(null);
  const [geo, setGeo] = useState<Awaited<ReturnType<typeof api.chainGeo>> | null>(null);
  const [timeline, setTimeline] = useState<Awaited<ReturnType<typeof api.chainTimeline>> | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [focusLoading, setFocusLoading] = useState(false);
  const [focusError, setFocusError] = useState("");

  const selectNode = (nodeKey: string, nextView: ViewMode = "graph") => {
    setFocusError("");
    setDetail((current) => (current?.node?.node_key === nodeKey ? current : null));
    setGeo((current) => (current?.node_key === nodeKey ? current : null));
    setTimeline((current) => (current?.node_key === nodeKey ? current : null));
    setFocusNodeKey(nodeKey);
    setViewMode(nextView);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setDetail(null);
    setGeo(null);
    setTimeline(null);

    api.chainOverview({ market })
      .then((payload) => {
        if (cancelled) return;
        setOverview(payload);
        setFocusNodeKey((current) => {
          if (current && payload.nodes.some((node) => node.node_key === current)) return current;
          return payload.default_focus_node_key ?? payload.nodes[0]?.node_key ?? null;
        });
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`产业链页面读取失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [market]);

  useEffect(() => {
    if (!focusNodeKey) return;
    let cancelled = false;
    setFocusLoading(true);
    setFocusError("");

    Promise.all([
      api.chainNode(focusNodeKey, { market }),
      api.chainGeo({ nodeKey: focusNodeKey, market }),
      api.chainTimeline({ nodeKey: focusNodeKey, limit: 18 })
    ])
      .then(([nodeDetail, nodeGeo, nodeTimeline]) => {
        if (cancelled) return;
        setDetail(nodeDetail);
        setGeo(nodeGeo);
        setTimeline(nodeTimeline);
      })
      .catch((err: Error) => {
        if (!cancelled) setFocusError(`节点详情读取失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setFocusLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [focusNodeKey, market]);

  const layerOptions = useMemo(() => normalizeLayers(overview?.layers ?? [], overview?.nodes ?? []), [overview]);
  const currentDetail = detail?.node?.node_key === focusNodeKey ? detail : null;
  const currentGeo = geo?.node_key === focusNodeKey ? geo : null;
  const currentTimeline = timeline?.node_key === focusNodeKey ? timeline : null;
  const selectedNode = useMemo(() => {
    return currentDetail?.node ?? overview?.nodes.find((node) => node.node_key === focusNodeKey) ?? null;
  }, [currentDetail, focusNodeKey, overview]);
  const selectedNodeKey = focusNodeKey ?? selectedNode?.node_key ?? null;
  const selectedIntensity = normalizeIntensity(selectedNode);
  const visibleNodes = useMemo(() => {
    const nodes = overview?.nodes ?? [];
    const lowered = query.trim().toLowerCase();
    return nodes
      .filter((node) => activeLayer === "all" || normalizeLayerKey(node.layer) === activeLayer)
      .filter((node) => {
        if (!lowered) return true;
        return [
          node.name,
          node.node_key,
          ...(node.industry_names ?? []),
          ...(node.tags ?? [])
        ]
          .join(" ")
          .toLowerCase()
          .includes(lowered);
      })
      .sort((left, right) => nodeHeat(right) - nodeHeat(left));
  }, [activeLayer, overview, query]);
  const quickNodes = visibleNodes.slice(0, 14);
  const mappedIndustries = (currentDetail?.mapped_industries ?? []).slice(0, 8);
  const leaderStocks = (currentDetail?.leader_stocks ?? []).slice(0, 8);
  const indicators = (currentDetail?.indicators?.length ? currentDetail.indicators : selectedNode?.indicators) ?? [];
  const downstreamChainCount = useMemo(() => {
    return countDownstreamNodes(overview?.edges ?? [], selectedNodeKey);
  }, [overview, selectedNodeKey]);
  const stats = useMemo(() => {
    return {
      snapshot: String(overview?.summary?.snapshot_date ?? "--"),
      upstream: currentDetail?.upstream.length ?? 0,
      downstream: downstreamChainCount,
      regions: currentGeo?.regions.length ?? currentDetail?.regions?.length ?? overview?.regions?.length ?? 0
    };
  }, [currentDetail, currentGeo, downstreamChainCount, overview]);

  if (loading) return <div className="page-shell"><LoadingState label="正在加载产业链页面" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <div className="page-shell space-y-5">
      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="label">Industry Chain</div>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">产业链热力地图</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/industry" className="inline-flex h-10 items-center gap-2 rounded-md border border-[#f2dfd2] px-3 text-sm hover:border-orange-300">
              <Layers3 size={16} />
              产业雷达
            </Link>
            <Link href="/industry/review" className="inline-flex h-10 items-center gap-2 rounded-md border border-[#f2dfd2] px-3 text-sm hover:border-orange-300">
              <CalendarRange size={16} />
              赛道复盘
            </Link>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          {MARKET_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setMarket(option)}
              className={`inline-flex h-10 items-center rounded-md border px-3 text-sm transition ${
                market === option ? "border-orange-500 bg-orange-500 text-white" : "border-[#f2dfd2] bg-white hover:border-orange-300"
              }`}
            >
              {marketLabel(option)}
            </button>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {VIEW_OPTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setViewMode(key)}
              className={`inline-flex h-10 items-center gap-2 rounded-md border px-3 text-sm transition ${
                viewMode === key ? "border-orange-500 bg-orange-50 text-orange-700" : "border-[#f2dfd2] bg-white text-slate-600 hover:border-orange-300"
              }`}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-[1fr_320px]">
          <div className="space-y-4">
            <div className="relative">
              <Search size={16} className="pointer-events-none absolute left-3 top-3 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索产业节点"
                className="h-11 w-full rounded-md border border-[#f2dfd2] bg-white pl-9 pr-3 text-sm outline-none focus:border-orange-400"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              {layerOptions.map((layer) => (
                <button
                  key={layer.key}
                  type="button"
                  onClick={() => setActiveLayer(layer.key)}
                  className={`inline-flex h-9 items-center rounded-md border px-3 text-sm transition ${
                    activeLayer === layer.key ? "border-orange-500 bg-orange-50 text-orange-700" : "border-[#f2dfd2] bg-white text-slate-600 hover:border-orange-300"
                  }`}
                >
                  {layer.label}
                  {typeof layer.count === "number" ? <span className="ml-2 text-xs text-slate-400">{layer.count}</span> : null}
                </button>
              ))}
            </div>

            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {quickNodes.map((node) => {
                const active = node.node_key === selectedNodeKey;
                const intensity = normalizeIntensity(node);
                return (
                  <button
                    key={node.node_key}
                    type="button"
                    onClick={() => selectNode(node.node_key, "graph")}
                    aria-pressed={active}
                    className={`rounded-lg border p-3 text-left transition ${
                      active ? "border-orange-500 bg-orange-50/80 shadow-[0_0_0_2px_rgba(249,115,22,0.12)]" : "border-[#f2dfd2] bg-white hover:border-orange-300 hover:bg-[#fffaf5]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-900">{node.name}</div>
                        <div className="mt-1 text-xs text-slate-500">{node.layer}</div>
                      </div>
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: warmColor(intensity) }} />
                    </div>
                    <div className="mono mt-3 text-sm font-semibold" style={{ color: warmColor(intensity) }}>
                      {nodeHeat(node).toFixed(1)}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rounded-lg border border-[#f2dfd2] bg-[#fffaf5] p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Flame size={16} className="text-orange-600" />
              焦点摘要
            </div>
            <div className="mt-3">
              <div className="text-lg font-semibold text-slate-950">{selectedNode?.name ?? "--"}</div>
              <div className="mt-1 text-xs text-slate-500">{selectedNode?.layer ?? "--"} / {marketLabel(market)}</div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2">
              <TopMetric label="快照" value={stats.snapshot} onClick={() => setViewMode("graph")} />
              <TopMetric label="热度" value={selectedNode ? nodeHeat(selectedNode).toFixed(1) : "--"} onClick={() => setViewMode("graph")} />
              <TopMetric label="上游" value={stats.upstream} onClick={() => setViewMode("focus")} />
              <TopMetric label="下游" value={stats.downstream} onClick={() => setViewMode("focus")} />
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-4">
        <StatCard icon={CalendarRange} label="快照日期" value={stats.snapshot} onClick={() => setViewMode("graph")} />
        <StatCard icon={Boxes} label="直接上游" value={stats.upstream} onClick={() => setViewMode("focus")} />
        <StatCard icon={ArrowRight} label="下游链" value={stats.downstream} onClick={() => setViewMode("focus")} />
        <StatCard icon={Globe2} label="区域触点" value={stats.regions} onClick={() => setViewMode("geo")} />
      </section>

      {viewMode === "graph" ? (
        <IndustryGraphMap
          nodes={overview?.nodes ?? []}
          edges={overview?.edges ?? []}
          selectedNodeKey={selectedNodeKey}
          activeLayer={activeLayer}
          query={query}
          onSelect={(nodeKey) => selectNode(nodeKey, "graph")}
        />
      ) : null}

      {viewMode === "heatmap" ? (
        <IndustryPlaneHeatMap
          nodes={overview?.nodes ?? []}
          edges={overview?.edges ?? []}
          selectedNodeKey={selectedNodeKey}
          activeLayer={activeLayer}
          query={query}
          onSelect={(nodeKey) => selectNode(nodeKey, "focus")}
        />
      ) : null}

      {viewMode === "focus" ? (
      <section className="grid items-start gap-4 xl:grid-cols-[1.5fr_0.74fr]">
        <div className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-white">
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#f7e9de] p-5">
            <div>
              <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
                <Activity size={18} className="text-orange-600" />
                {selectedNode?.name ?? "产业节点"}上下游
              </div>
              <div className="mt-1 text-xs text-slate-500">{currentDetail?.heat_explanation?.slice(0, 2).join(" / ") || selectedNode?.node_type || "聚焦当前节点上下游"}</div>
            </div>
            <HeatBadge intensity={selectedIntensity} />
          </div>
          {focusError ? <div className="p-5"><ErrorState message={focusError} /></div> : null}
          {focusLoading && !currentDetail ? <div className="p-5"><LoadingState label="正在加载节点结构" /></div> : null}
          {!focusLoading || currentDetail ? (
            <IndustryChainMap
              detail={currentDetail}
              allNodes={overview?.nodes ?? []}
              allEdges={overview?.edges ?? []}
              selectedNodeKey={selectedNodeKey}
              onSelect={(nodeKey) => selectNode(nodeKey, "focus")}
            />
          ) : null}
        </div>

        <aside className="space-y-4">
          <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="label">Node</div>
                <div className="mt-2 text-xl font-semibold text-slate-950">{selectedNode?.name ?? "--"}</div>
              </div>
              <HeatBadge intensity={selectedIntensity} compact />
            </div>

            {selectedNode?.description ? <div className="mt-4 text-sm leading-6 text-slate-600">{selectedNode.description}</div> : null}

            <div className="mt-4 flex flex-wrap gap-2">
              {(selectedNode?.tags ?? []).slice(0, 8).map((tag) => (
                <span key={tag} className="rounded-md border border-[#f2dfd2] px-2 py-1 text-xs text-slate-600">{tag}</span>
              ))}
            </div>

            <div className="mt-5 grid grid-cols-2 gap-2 text-sm">
              <MiniMetric label="热度" value={selectedNode ? nodeHeat(selectedNode).toFixed(1) : "--"} />
              <MiniMetric label="动量" value={selectedNode?.momentum?.toFixed(1) ?? "--"} />
              <MiniMetric label="强度" value={selectedNode ? `${Math.round(normalizeIntensity(selectedNode) * 100)}%` : "--"} />
              <MiniMetric label="股票数" value={selectedNode?.stock_count ?? "--"} />
            </div>
          </section>

          <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Layers3 size={16} className="text-orange-600" />
              映射行业
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {mappedIndustries.length ? mappedIndustries.map((item, index) => (
                <IndustryTag key={`${normalizeIndustryName(item)}-${index}`} item={item} />
              )) : <EmptyHint label="暂无映射行业" />}
            </div>
          </section>

          <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Building2 size={16} className="text-orange-600" />
              龙头上市企业
            </div>
            <div className="mt-3 space-y-2">
              {leaderStocks.length ? leaderStocks.map((stock) => (
                <Link
                  key={stock.code}
                  href={stockEvidenceHref(stock.code)}
                  aria-label={`查看 ${stock.name} 单股证据链`}
                  className="group block rounded-md border border-[#f2dfd2] bg-white p-3 transition hover:border-orange-300 hover:bg-[#fffaf5]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium text-slate-900">{stock.name}</div>
                      <div className="mt-1 text-xs text-slate-500">{stock.code} / {stock.market || "--"}</div>
                      <div className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-orange-700">
                        单股证据链
                        <ArrowUpRight size={13} className="transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                      </div>
                    </div>
                    <div className="mono text-right text-sm font-semibold text-orange-700">
                      {formatNumber(stock.final_score)}
                    </div>
                  </div>
                </Link>
              )) : <EmptyHint label="暂无龙头股票" />}
            </div>
          </section>

          <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <CircleGauge size={16} className="text-orange-600" />
              指标
            </div>
            <div className="mt-3 space-y-2">
              {indicators.length ? indicators.slice(0, 8).map((item) => (
                <div key={item.label} className="flex items-center justify-between rounded-md border border-[#f7e9de] px-3 py-2 text-sm">
                  <span className="text-slate-500">{item.label}</span>
                  <span className="mono font-semibold text-slate-900">{formatIndicator(item.value, item.unit)}</span>
                </div>
              )) : <EmptyHint label="暂无指标" />}
            </div>
          </section>
        </aside>
      </section>
      ) : null}

      {viewMode === "geo" ? (
      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
              <Globe2 size={18} className="text-orange-600" />
              世界产业分布
            </div>
            <div className="mt-1 text-xs text-slate-500">{selectedNode?.name ?? "--"} 区域热力与迁移路径</div>
          </div>
          <HeatBadge intensity={selectedIntensity} compact />
        </div>
        <WorldIndustryHeatMap geo={currentGeo} selectedNode={selectedNode} />
      </section>
      ) : null}

      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="mb-4 flex items-center gap-2 text-lg font-semibold text-slate-950">
          <TrendingUp size={18} className="text-orange-600" />
          热度迁移时间条
        </div>
        <TimelineStrip items={currentTimeline?.timeline ?? []} />
      </section>
    </div>
  );
}

function TimelineStrip({ items }: { items: ChainTimelinePoint[] }) {
  const values = items.map((item) => pointHeat(item));
  const max = Math.max(...values, 1);

  if (!items.length) return <EmptyHint label="暂无时间序列" />;

  return (
    <div className="grid gap-3 lg:grid-cols-6">
      {items.map((item, index) => {
        const heat = pointHeat(item);
        const intensity = Math.min(heat / max, 1);
        return (
          <div key={`${pointDate(item)}-${index}`} className="rounded-lg border border-[#f2dfd2] bg-[#fffaf5] p-3">
            <div className="mono text-xs font-semibold text-slate-600">{pointDate(item)}</div>
            <div className="mt-3 h-24 rounded-md bg-white p-2">
              <div className="flex h-full items-end gap-2">
                <div className="w-4 rounded-full" style={{ height: `${Math.max(intensity * 100, 16)}%`, backgroundColor: warmColor(intensity) }} />
                <div className="flex-1">
                  <div className="mono text-base font-semibold text-slate-900">{heat.toFixed(1)}</div>
                  <div className="mt-1 text-xs text-slate-500">{item.label || item.summary || "--"}</div>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  onClick
}: {
  icon: typeof CalendarRange;
  label: string;
  value: string | number;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg border border-[#f2dfd2] bg-white p-4 text-left transition hover:border-orange-300 hover:bg-[#fffaf5]"
    >
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <Icon size={16} className="text-orange-600" />
        {label}
      </div>
      <div className="mono mt-3 text-2xl font-semibold text-slate-950">{value}</div>
    </button>
  );
}

function TopMetric({ label, value, onClick }: { label: string; value: string | number; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md border border-[#f2dfd2] bg-white px-3 py-2 text-left transition hover:border-orange-300 hover:bg-[#fffaf5]"
    >
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mono mt-1 text-sm font-semibold text-slate-900">{value}</div>
    </button>
  );
}

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-[#f7e9de] bg-[#fffaf6] px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mono mt-1 font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function HeatBadge({ intensity, compact = false }: { intensity: number; compact?: boolean }) {
  const color = warmColor(intensity);
  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border border-[#f2dfd2] bg-white ${compact ? "px-2.5 py-1.5" : "px-3 py-2"}`}
    >
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      <span className="mono text-xs font-semibold text-slate-700">{Math.round(intensity * 100)}%</span>
    </div>
  );
}

function IndustryTag({ item }: { item: ChainMappedIndustry | string }) {
  const name = normalizeIndustryName(item);
  return (
    <span className="rounded-md border border-[#f2dfd2] bg-[#fffaf5] px-2 py-1 text-xs text-slate-700">
      {name}
    </span>
  );
}

function EmptyHint({ label }: { label: string }) {
  return <div className="rounded-md border border-dashed border-[#f2dfd2] px-3 py-3 text-sm text-slate-500">{label}</div>;
}

function normalizeLayers(layers: Array<ChainLayer | string>, nodes: ChainNode[]): LayerOption[] {
  const normalized = layers.map<LayerOption>((layer) => {
    if (typeof layer === "string") {
      return {
        key: normalizeLayerKey(layer),
        label: layer,
        count: nodes.filter((node) => normalizeLayerKey(node.layer) === normalizeLayerKey(layer)).length
      };
    }
    return {
      key: normalizeLayerKey(layer.key),
      label: layer.label,
      count: layer.count ?? nodes.filter((node) => normalizeLayerKey(node.layer) === normalizeLayerKey(layer.key)).length
    };
  });
  return [{ key: "all", label: "全部", count: nodes.length }, ...normalized];
}

function normalizeLayerKey(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function normalizeIndustryName(value: ChainMappedIndustry | string) {
  return typeof value === "string" ? value : value.name;
}

function pointDate(item: ChainTimelinePoint) {
  return item.trade_date ?? item.date ?? "--";
}

function pointHeat(item: ChainTimelinePoint) {
  return Math.max(item.heat ?? 0, item.momentum ?? 0, (item.intensity ?? 0) * 100);
}

function nodeHeat(node: ChainNode) {
  return Math.max(node.heat ?? 0, node.momentum ?? 0, (node.intensity ?? 0) * 100);
}

function countDownstreamNodes(edges: Array<{ source: string; target: string }>, selectedNodeKey: string | null) {
  if (!selectedNodeKey) return 0;
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const rows = adjacency.get(edge.source) ?? [];
    rows.push(edge.target);
    adjacency.set(edge.source, rows);
  }

  const visited = new Set<string>([selectedNodeKey]);
  const downstream = new Set<string>();
  const queue = [selectedNodeKey];
  while (queue.length) {
    const current = queue.shift();
    if (!current) break;
    for (const target of adjacency.get(current) ?? []) {
      if (target === selectedNodeKey || visited.has(target)) continue;
      visited.add(target);
      downstream.add(target);
      queue.push(target);
    }
  }
  return downstream.size;
}

function normalizeIntensity(node: ChainNode | null) {
  if (!node) return 0;
  const value = node.intensity ?? (nodeHeat(node) > 1 ? nodeHeat(node) / 100 : nodeHeat(node));
  return Math.min(Math.max(value, 0), 1);
}

function warmColor(intensity: number) {
  if (intensity >= 0.86) return "#b91c1c";
  if (intensity >= 0.64) return "#ea580c";
  if (intensity >= 0.38) return "#f59e0b";
  return "#facc15";
}

function formatNumber(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return value.toFixed(1);
}

function formatIndicator(value: string | number | null, unit?: string) {
  if (value === null || value === undefined || value === "") return "--";
  return `${value}${unit ?? ""}`;
}

function stockEvidenceHref(code: string) {
  return `/stocks/${encodeURIComponent(code)}?from=${encodeURIComponent("/industry/chain")}`;
}
