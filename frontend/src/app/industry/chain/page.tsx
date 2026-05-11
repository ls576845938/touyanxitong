"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
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
  TrendingUp,
  LayoutDashboard,
  Filter,
  MonitorPlay
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ErrorState } from "@/components/ErrorState";
import { IndustryChainMap } from "@/components/IndustryChainMap";
import { IndustryGraphMap } from "@/components/IndustryGraphMap";
import { IndustryMetroSankeyMap } from "@/components/IndustryMetroSankeyMap";
import { IndustryPlaneHeatMap } from "@/components/IndustryPlaneHeatMap";
import { IndustryUniverseOverview } from "@/components/IndustryUniverseOverview";
import { LoadingState } from "@/components/LoadingState";
import { WorldIndustryHeatMap } from "@/components/WorldIndustryHeatMap";
import { api, type ChainLayer, type ChainMappedIndustry, type ChainNode, type ChainNodeDetail, type ChainTimelinePoint } from "@/lib/api";
import { MARKET_OPTIONS, marketLabel } from "@/lib/markets";

type ViewMode = "universe" | "metro" | "graph" | "focus" | "heatmap" | "geo";

const VIEW_OPTIONS: { key: ViewMode; label: string; icon: any }[] = [
  { key: "universe", label: "宇宙总览", icon: LayoutDashboard },
  { key: "metro", label: "地铁主图", icon: Activity },
  { key: "graph", label: "球面关系", icon: Layers3 },
  { key: "focus", label: "聚焦链路", icon: MonitorPlay },
  { key: "heatmap", label: "平面谱系", icon: Boxes },
  { key: "geo", label: "地理分布", icon: Globe2 }
];

export default function IndustryChainPage() {
  const [market, setMarket] = useState("ALL");
  const [query, setQuery] = useState("");
  const [activeLayer, setActiveLayer] = useState("all");
  const [viewMode, setViewMode] = useState<ViewMode>("universe");
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
    return () => { cancelled = true; };
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
    return () => { cancelled = true; };
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
      .filter((node) => !lowered || [node.name, node.node_key, ...(node.industry_names ?? []), ...(node.tags ?? [])].join(" ").toLowerCase().includes(lowered))
      .sort((left, right) => nodeHeat(right) - nodeHeat(left));
  }, [activeLayer, overview, query]);

  const quickNodes = visibleNodes.slice(0, 16);
  const showFilters = viewMode !== "universe" && viewMode !== "metro";
  const stats = useMemo(() => ({
    snapshot: String(overview?.summary?.snapshot_date ?? "--"),
    upstream: currentDetail?.upstream.length ?? 0,
    downstream: countDownstreamNodes(overview?.edges ?? [], selectedNodeKey),
    regions: currentGeo?.regions.length ?? currentDetail?.regions?.length ?? overview?.regions?.length ?? 0
  }), [currentDetail, currentGeo, overview, selectedNodeKey]);

  if (loading) return <div className="min-h-screen bg-slate-50 flex items-center justify-center"><LoadingState label="正在初始化全球产业链实时热力引擎" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900 selection:bg-indigo-100 p-6 space-y-6">
      {/* Top Navigation Bar */}
      <header className="flex flex-wrap items-center justify-between gap-6 bg-white border border-slate-200 rounded-2xl px-8 py-5 shadow-sm">
        <div className="flex items-center gap-6">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-900 text-white shadow-xl shadow-slate-200">
            <Activity size={28} />
          </div>
          <div>
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-1">Global Market Intelligence</div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight">产业链热力地图</h1>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex bg-slate-100 p-1 rounded-xl border border-slate-200">
            {MARKET_OPTIONS.map((option) => (
              <button
                key={option}
                onClick={() => setMarket(option)}
                className={cn(
                  "px-4 py-2 rounded-lg text-xs font-bold transition-all",
                  market === option ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-900"
                )}
              >
                {marketLabel(option)}
              </button>
            ))}
          </div>
          <div className="h-8 w-[1px] bg-slate-200 mx-2" />
          <Link href="/industry/review" className="flex items-center gap-2 px-5 py-2.5 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-600 hover:border-indigo-500 hover:text-indigo-600 transition-all shadow-sm">
            <CalendarRange size={16} />
            赛道复盘
          </Link>
        </div>
      </header>

      {/* Main View Mode Toggles */}
      <nav className="flex flex-wrap gap-2 overflow-x-auto pb-1 no-scrollbar">
        {VIEW_OPTIONS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setViewMode(key)}
            className={cn(
              "flex items-center gap-2.5 px-6 py-3.5 rounded-2xl border font-bold text-sm transition-all whitespace-nowrap active:scale-95 shadow-sm",
              viewMode === key 
                ? "bg-slate-900 border-slate-900 text-white shadow-xl shadow-slate-200" 
                : "bg-white border-slate-200 text-slate-500 hover:border-slate-300 hover:bg-slate-50"
            )}
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </nav>

      {/* Filter and Selection Section */}
      <AnimatePresence mode="wait">
        {showFilters && (
          <motion.section 
            initial={{ opacity: 0, y: -20 }} 
            animate={{ opacity: 1, y: 0 }} 
            exit={{ opacity: 0, y: -20 }}
            className="grid gap-6 xl:grid-cols-[1fr_360px]"
          >
            <div className="bg-white border border-slate-200 rounded-3xl p-8 shadow-sm space-y-6">
              <div className="flex items-center gap-4">
                <div className="relative flex-1 group">
                  <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="按名称、行业或标签搜索产业节点..."
                    className="w-full h-14 pl-12 pr-6 rounded-2xl bg-slate-50 border border-slate-100 focus:bg-white focus:border-indigo-500 focus:ring-4 focus:ring-indigo-50/50 outline-none transition-all text-sm font-medium"
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  {layerOptions.map((layer) => (
                    <button
                      key={layer.key}
                      onClick={() => setActiveLayer(layer.key)}
                      className={cn(
                        "h-10 px-5 rounded-xl text-xs font-bold transition-all border",
                        activeLayer === layer.key 
                          ? "bg-indigo-50 border-indigo-200 text-indigo-700" 
                          : "bg-white border-slate-200 text-slate-500 hover:border-slate-300"
                      )}
                    >
                      {layer.label}
                      {layer.count !== undefined && <span className="ml-2 opacity-50">{layer.count}</span>}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 grid-cols-2 md:grid-cols-4 lg:grid-cols-8">
                {quickNodes.map((node) => {
                  const active = node.node_key === selectedNodeKey;
                  const intensity = normalizeIntensity(node);
                  return (
                    <button
                      key={node.node_key}
                      onClick={() => selectNode(node.node_key, "focus")}
                      className={cn(
                        "group relative p-4 rounded-2xl border text-left transition-all hover:shadow-lg active:scale-95",
                        active 
                          ? "bg-white border-orange-500 ring-2 ring-orange-100" 
                          : "bg-slate-50 border-transparent hover:bg-white hover:border-slate-300"
                      )}
                    >
                      <div className="absolute top-3 right-3 h-2 w-2 rounded-full" style={{ backgroundColor: heatColor(intensity) }} />
                      <div className="text-xs font-black text-slate-900 truncate mb-1">{node.name}</div>
                      <div className="text-[9px] font-bold text-slate-400 uppercase tracking-tighter truncate">{node.layer}</div>
                      <div className="mt-3 flex items-baseline gap-1">
                        <span className="text-xs font-black" style={{ color: heatColor(intensity) }}>{nodeHeat(node).toFixed(1)}</span>
                        <span className="text-[8px] font-bold text-slate-400 uppercase">HEAT</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-3xl p-8 shadow-sm flex flex-col">
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                  <Flame size={14} className="text-orange-500" />
                  Focus Analysis
                </h3>
                <HeatBadge intensity={selectedIntensity} compact />
              </div>
              <div className="flex-1">
                <div className="text-2xl font-black text-slate-900 leading-tight mb-2">{selectedNode?.name ?? "Select Node"}</div>
                <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider mb-6">
                  {selectedNode?.layer ?? "--"} 
                  <span className="opacity-30">/</span> 
                  {marketLabel(market)}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard label="快照版本" value={stats.snapshot} />
                  <MetricCard label="热度强度" value={selectedNode ? nodeHeat(selectedNode).toFixed(1) : "--"} highlighted />
                  <MetricCard label="上游接入" value={stats.upstream} />
                  <MetricCard label="下游覆盖" value={stats.downstream} />
                </div>
              </div>
              <button 
                onClick={() => setViewMode("focus")}
                className="mt-8 w-full flex items-center justify-center gap-2 h-12 bg-slate-900 text-white rounded-2xl text-xs font-black uppercase tracking-widest hover:bg-indigo-600 transition-all shadow-lg shadow-indigo-100"
              >
                Launch Deep Dive
                <ArrowUpRight size={16} />
              </button>
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      {/* Main Map Display Area */}
      <section className="relative">
        <AnimatePresence mode="wait">
          <motion.div
            key={viewMode}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 1.02 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            {viewMode === "universe" && (
              <IndustryUniverseOverview
                nodes={overview?.nodes ?? []}
                edges={overview?.edges ?? []}
                selectedNodeKey={selectedNodeKey}
                onOpenChain={(nodeKey) => selectNode(nodeKey, "metro")}
              />
            )}
            {viewMode === "metro" && (
              <IndustryMetroSankeyMap
                nodes={overview?.nodes ?? []}
                edges={overview?.edges ?? []}
                selectedNodeKey={selectedNodeKey}
                onSelect={(nodeKey) => selectNode(nodeKey, "metro")}
              />
            )}
            {viewMode === "graph" && (
              <IndustryGraphMap
                nodes={overview?.nodes ?? []}
                edges={overview?.edges ?? []}
                selectedNodeKey={selectedNodeKey}
                activeLayer={activeLayer}
                query={query}
                onSelect={(nodeKey) => selectNode(nodeKey, "graph")}
              />
            )}
            {viewMode === "heatmap" && (
              <IndustryPlaneHeatMap
                nodes={overview?.nodes ?? []}
                edges={overview?.edges ?? []}
                selectedNodeKey={selectedNodeKey}
                activeLayer={activeLayer}
                query={query}
                onSelect={(nodeKey) => selectNode(nodeKey, "focus")}
              />
            )}
            {viewMode === "geo" && (
              <div className="bg-white border border-slate-200 rounded-3xl p-8 shadow-sm">
                <div className="flex items-center justify-between mb-8">
                  <div>
                    <h2 className="text-xl font-black text-slate-900">全球产业地理分布</h2>
                    <p className="text-xs font-bold text-slate-400 uppercase mt-1 tracking-widest">{selectedNode?.name} Supply Chain Nodes</p>
                  </div>
                  <HeatBadge intensity={selectedIntensity} />
                </div>
                <WorldIndustryHeatMap geo={currentGeo} selectedNode={selectedNode} />
              </div>
            )}
            {viewMode === "focus" && (
              <div className="grid items-start gap-6 xl:grid-cols-[1fr_400px]">
                <div className="bg-white border border-slate-200 rounded-3xl overflow-hidden shadow-sm">
                  <div className="flex items-center justify-between px-8 py-6 border-b border-slate-100">
                    <div>
                      <h2 className="text-xl font-black text-slate-900 flex items-center gap-3">
                        <Activity className="text-orange-500" />
                        {selectedNode?.name ?? "产业节点"} 核心链路
                      </h2>
                      <p className="text-[10px] font-bold text-slate-400 uppercase mt-1 tracking-[0.2em]">{currentDetail?.heat_explanation?.slice(0, 2).join(" • ") || "Contextual Linkage Analysis"}</p>
                    </div>
                    <HeatBadge intensity={selectedIntensity} />
                  </div>
                  <div className="p-2">
                    <IndustryChainMap
                      detail={currentDetail}
                      allNodes={overview?.nodes ?? []}
                      allEdges={overview?.edges ?? []}
                      selectedNodeKey={selectedNodeKey}
                      onSelect={(nodeKey) => selectNode(nodeKey, "focus")}
                    />
                  </div>
                </div>

                <aside className="space-y-6">
                  <DetailPanel title="节点概览" icon={Building2}>
                    <div className="text-sm font-medium text-slate-600 leading-relaxed mb-6">{selectedNode?.description || "该节点暂无详细定义描述。"}</div>
                    <div className="flex flex-wrap gap-2 mb-6">
                      {(selectedNode?.tags ?? []).map(tag => (
                        <span key={tag} className="px-3 py-1 bg-slate-50 border border-slate-200 rounded-lg text-[10px] font-black text-slate-500 uppercase">{tag}</span>
                      ))}
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <SmallMetric label="热度" value={selectedNode ? nodeHeat(selectedNode).toFixed(1) : "--"} color={heatColor(selectedIntensity)} />
                      <SmallMetric label="动量" value={selectedNode?.momentum?.toFixed(1) ?? "--"} color="#6366f1" />
                      <SmallMetric label="强度" value={selectedNode ? `${Math.round(selectedIntensity * 100)}%` : "--"} color="#10b981" />
                      <SmallMetric label="龙头数" value={selectedNode?.stock_count ?? "--"} color="#f59e0b" />
                    </div>
                  </DetailPanel>

                  <DetailPanel title="关联龙头" icon={TrendingUp}>
                    <div className="space-y-2">
                      {(currentDetail?.leader_stocks ?? []).map((stock) => (
                        <Link key={stock.code} href={stockEvidenceHref(stock.code)} className="group flex items-center justify-between p-4 bg-slate-50 rounded-2xl border border-transparent hover:border-indigo-500 hover:bg-white transition-all shadow-sm">
                          <div>
                            <div className="text-xs font-black text-slate-900 group-hover:text-indigo-600 transition-colors">{stock.name}</div>
                            <div className="text-[9px] font-bold text-slate-400 mt-0.5">{stock.code} • {stock.market}</div>
                          </div>
                          <div className="text-right">
                            <div className="text-xs font-black text-indigo-600">{formatNumber(stock.final_score)}</div>
                            <ArrowUpRight size={12} className="ml-auto mt-0.5 text-slate-300 group-hover:text-indigo-400 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 transition-all" />
                          </div>
                        </Link>
                      ))}
                    </div>
                  </DetailPanel>
                </aside>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </section>

      {/* Bottom Timeline Section */}
      <footer className="bg-white border border-slate-200 rounded-3xl p-8 shadow-sm">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h3 className="text-lg font-black text-slate-900 flex items-center gap-3">
              <TrendingUp className="text-indigo-600" />
              热度迁移时间线
            </h3>
            <p className="text-xs font-bold text-slate-400 uppercase mt-1 tracking-widest">Historical Performance Propagation</p>
          </div>
          <div className="flex gap-1">
            {[1,2,3,4,5].map(i => <div key={i} className="h-1 w-6 rounded-full bg-slate-100" />)}
          </div>
        </div>
        <TimelineStrip items={currentTimeline?.timeline ?? []} />
      </footer>
    </main>
  );
}

function MetricCard({ label, value, highlighted = false }: { label: string; value: string | number; highlighted?: boolean }) {
  return (
    <div className={cn("p-4 rounded-2xl border transition-all", highlighted ? "bg-slate-900 border-slate-900" : "bg-slate-50 border-slate-100")}>
      <div className={cn("text-[9px] font-black uppercase tracking-widest mb-1", highlighted ? "text-slate-500" : "text-slate-400")}>{label}</div>
      <div className={cn("text-lg font-black tracking-tight", highlighted ? "text-white" : "text-slate-900")}>{value}</div>
    </div>
  );
}

function SmallMetric({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="bg-white border border-slate-100 p-3 rounded-xl shadow-sm">
      <div className="text-[9px] font-black text-slate-400 uppercase tracking-tighter mb-0.5">{label}</div>
      <div className="text-sm font-black" style={{ color }}>{value}</div>
    </div>
  );
}

function DetailPanel({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-slate-200 rounded-3xl p-6 shadow-sm">
      <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-50">
        <div className="p-2 rounded-lg bg-slate-50 text-slate-400"><Icon size={16} /></div>
        <h4 className="text-xs font-black text-slate-900 uppercase tracking-widest">{title}</h4>
      </div>
      {children}
    </div>
  );
}

function TimelineStrip({ items }: { items: ChainTimelinePoint[] }) {
  if (!items.length) return <div className="h-40 flex items-center justify-center text-slate-300 text-xs font-bold uppercase tracking-widest border border-dashed border-slate-100 rounded-2xl">Awaiting Time Series Data...</div>;
  const values = items.map(i => pointHeat(i));
  const max = Math.max(...values, 1);
  return (
    <div className="grid gap-3 grid-cols-2 md:grid-cols-3 lg:grid-cols-6 xl:grid-cols-9">
      {items.map((item, idx) => {
        const heat = pointHeat(item);
        const intensity = Math.min(heat / max, 1);
        return (
          <div key={idx} className="group relative bg-slate-50 rounded-2xl p-4 border border-transparent hover:bg-white hover:border-slate-200 transition-all hover:shadow-lg">
            <div className="text-[10px] font-black text-slate-400 group-hover:text-indigo-600 transition-colors">{pointDate(item)}</div>
            <div className="mt-4 flex items-end gap-3 h-16">
              <div className="w-1.5 rounded-full transition-all duration-500" style={{ height: `${Math.max(intensity * 100, 10)}%`, backgroundColor: heatColor(intensity) }} />
              <div className="flex-1">
                <div className="text-lg font-black text-slate-900 tabular-nums leading-none">{heat.toFixed(1)}</div>
                <div className="text-[8px] font-bold text-slate-400 uppercase mt-1 truncate">{item.label || "Normal"}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HeatBadge({ intensity, compact = false }: { intensity: number; compact?: boolean }) {
  return (
    <div className={cn("inline-flex items-center gap-2 bg-white border border-slate-200 rounded-full", compact ? "px-3 py-1.5" : "px-4 py-2.5 shadow-sm")}>
      <div className="h-2 w-2 rounded-full animate-pulse" style={{ backgroundColor: heatColor(intensity) }} />
      <span className="text-[10px] font-black text-slate-900 tracking-widest">{Math.round(intensity * 100)}% <span className="text-slate-400">热度</span></span>
    </div>
  );
}

// Utility Helpers
function heatColor(intensity: number) {
  if (intensity >= 0.8) return "#ef4444"; // Red
  if (intensity >= 0.45) return "#f97316"; // Orange
  return "#eab308"; // Yellow
}

function normalizeLayers(layers: Array<ChainLayer | string>, nodes: ChainNode[]): { key: string; label: string; count: number }[] {
  const normalized = layers.map((layer) => {
    const key = typeof layer === "string" ? normalizeLayerKey(layer) : normalizeLayerKey(layer.key);
    const label = typeof layer === "string" ? layer : layer.label;
    return { key, label, count: nodes.filter(n => normalizeLayerKey(n.layer) === key).length };
  });
  return [{ key: "all", label: "全部", count: nodes.length }, ...normalized];
}

function normalizeLayerKey(v: string) { return v.trim().toLowerCase().replace(/\s+/g, "_"); }
function pointDate(i: ChainTimelinePoint) { return i.trade_date ?? i.date ?? "--"; }
function pointHeat(i: ChainTimelinePoint) { return Math.max(i.heat ?? 0, i.momentum ?? 0, (i.intensity ?? 0) * 100); }
function nodeHeat(n: ChainNode) { return Math.max(n.heat ?? 0, n.momentum ?? 0, (n.intensity ?? 0) * 100); }
function normalizeIntensity(n: ChainNode | null) {
  if (!n) return 0;
  const v = n.intensity ?? (nodeHeat(n) > 1 ? nodeHeat(n) / 100 : nodeHeat(n));
  return Math.min(Math.max(v, 0), 1);
}
function formatNumber(v?: number | null) { return typeof v === "number" ? v.toFixed(1) : "--"; }
function stockEvidenceHref(c: string) { return `/stocks/${encodeURIComponent(c)}?from=${encodeURIComponent("/industry/chain")}`; }

function countDownstreamNodes(edges: Array<{ source: string; target: string }>, root: string | null) {
  if (!root) return 0;
  const adj = new Map<string, string[]>();
  edges.forEach(e => {
    const r = adj.get(e.source) ?? [];
    r.push(e.target);
    adj.set(e.source, r);
  });
  const visited = new Set([root]);
  const q = [root];
  const ds = new Set();
  while (q.length) {
    const c = q.shift()!;
    (adj.get(c) ?? []).forEach(t => {
      if (!visited.has(t)) {
        visited.add(t); ds.add(t); q.push(t);
      }
    });
  }
  return ds.size;
}
