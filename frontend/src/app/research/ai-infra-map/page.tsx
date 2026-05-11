"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Boxes,
  Database,
  Eye,
  Filter,
  Flame,
  GitBranch,
  Layers3,
  ListTree,
  Maximize2,
  Minimize2,
  Network,
  RotateCcw,
  Search, 
  ShieldAlert,
  Table2,
  Target,
  Zap,
  Share2,
  type LucideIcon
  } from "lucide-react";import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { TonePill, WorkbenchLink } from "@/components/Workbench";
import {
  AI_INFRA_CORE_FIELDS,
  AI_INFRA_MAIN_VARIABLES,
  AI_INFRA_TREE,
  AI_INFRA_VERSION,
  type AiInfraFlatNode,
  type AiInfraMetric,
  flattenAiInfraTree
} from "@/lib/ai-infra-knowledge-tree";
import { api, type ChainOverview, type ResearchDataGate, type ResearchHotTerm, type ResearchHotTerms } from "@/lib/api";
import { cn } from "@/lib/utils";

type ViewMode = "graph" | "lanes" | "matrix" | "evidence";

type NodeOverlay = {
  hotScore: number;
  hotTerms: ResearchHotTerm[];
  chainMatches: ChainOverview["nodes"];
  systemTags: string[];
};

type PointerState = {
  x: number;
  y: number;
  panX: number;
  panY: number;
};

const VIEW_MODES: Array<{ value: ViewMode; label: string; icon: LucideIcon }> = [
  { value: "graph", label: "知识图", icon: Network },
  { value: "lanes", label: "主链", icon: GitBranch },
  { value: "matrix", label: "矩阵", icon: Table2 },
  { value: "evidence", label: "口径", icon: Database }
];

const ROOT_COLORS = [
  "#0f766e",
  "#2563eb",
  "#7c3aed",
  "#d97706",
  "#dc2626",
  "#0891b2",
  "#65a30d",
  "#9333ea",
  "#be123c",
  "#ca8a04",
  "#475569"
];

const SVG_WIDTH = 2320;
const SVG_HEIGHT = 980;

export default function AiInfraKnowledgeMapPage() {
  const rows = useMemo(() => flattenAiInfraTree(AI_INFRA_TREE), []);
  const roots = useMemo(() => rows.filter((node) => node.depth === 0), [rows]);
  const [hotTerms, setHotTerms] = useState<ResearchHotTerms | null>(null);
  const [chain, setChain] = useState<ChainOverview | null>(null);
  const [gate, setGate] = useState<ResearchDataGate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [rootFilter, setRootFilter] = useState("all");
  const [selectedId, setSelectedId] = useState("gpu-accelerator");
  const [mode, setMode] = useState<ViewMode>("graph");
  const [systemOnly, setSystemOnly] = useState(false);
  const [depthLimit, setDepthLimit] = useState(3);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      api.researchHotTerms({ window: "1d", limit: 80 }),
      api.chainOverview(),
      api.researchDataGate({ limit: 30 })
    ])
      .then(([hotResult, chainResult, gateResult]) => {
        if (cancelled) return;
        setHotTerms(hotResult.status === "fulfilled" ? hotResult.value : null);
        setChain(chainResult.status === "fulfilled" ? chainResult.value : null);
        setGate(gateResult.status === "fulfilled" ? gateResult.value : null);
        const failures = [hotResult, chainResult, gateResult].filter((item) => item.status === "rejected").length;
        setError(failures === 3 ? "系统动态数据全部读取失败，无法完成图谱增强。" : "");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const overlays = useMemo(() => buildOverlays(rows, hotTerms, chain), [chain, hotTerms, rows]);
  const selectedNode = useMemo(() => rows.find((node) => node.id === selectedId) ?? rows[0], [rows, selectedId]);
  const selectedOverlay = overlays[selectedNode.id] ?? emptyOverlay();
  const filteredRows = useMemo(() => {
    return rows.filter((node) => {
      if (rootFilter !== "all" && node.rootId !== rootFilter) return false;
      if (node.depth > depthLimit) return false;
      const overlay = overlays[node.id] ?? emptyOverlay();
      if (systemOnly && overlay.hotTerms.length === 0 && overlay.chainMatches.length === 0) return false;
      if (!query.trim()) return true;
      return nodeMatchesQuery(node, query);
    });
  }, [depthLimit, overlays, query, rootFilter, rows, systemOnly]);

  const metrics = useMemo(() => {
    const metricCount = rows.reduce((sum, node) => sum + (node.metrics?.length ?? 0), 0);
    const playerCount = rows.reduce((sum, node) => sum + (node.players?.reduce((inner, group) => inner + group.names.length, 0) ?? 0), 0);
    const hotLinked = rows.filter((node) => (overlays[node.id]?.hotTerms.length ?? 0) > 0).length;
    const chainLinked = rows.filter((node) => (overlays[node.id]?.chainMatches.length ?? 0) > 0).length;
    return { metricCount, playerCount, hotLinked, chainLinked };
  }, [overlays, rows]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在装载AI算力知识图谱" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-[1800px] space-y-6">
        <header className="grid gap-4 xl:grid-cols-[1fr_420px]">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-4xl">
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{AI_INFRA_VERSION}</div>
                <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950 lg:text-4xl">AI算力基础设施产业链知识图谱</h1>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
                  同一份知识树以图谱、主链泳道、全量矩阵和口径证据四种方式呈现；系统热词、产业链节点和数据门控作为动态增强层，只做研究辅助和风险提示。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <WorkbenchLink href="/research/hot-terms" label="热词雷达" />
                <WorkbenchLink href="/research/industry-chain" label="产业链工作台" />
              </div>
            </div>
            <div className="mt-6 grid gap-3 md:grid-cols-4">
              <Metric label="知识节点" value={rows.length} detail={`${roots.length}条主链 / ${metrics.metricCount}条口径`} />
              <Metric label="公司实体" value={metrics.playerCount} detail="全球龙头与中国映射合并计数" />
              <Metric label="热词命中" value={metrics.hotLinked} detail={`${hotTerms?.summary.term_count ?? 0}个系统热词参与匹配`} tone="hot" />
              <Metric label="图谱命中" value={metrics.chainLinked} detail={`${chain?.summary.node_count ?? 0}个系统产业节点可映射`} tone="system" />
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-amber-50 text-amber-700">
                <ShieldAlert size={20} />
              </div>
              <div>
                <div className="text-sm font-black text-slate-900">口径提示</div>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  市场份额可能混合收入、出货量、全球、中国或AI专用市场口径。本页保留原始口径描述，未核验的数据默认作为待验证证据，不进入确定性结论。
                </p>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <MiniStatus label="Data Gate" value={gate?.summary.fail_count ? "FAIL" : gate ? "CHECK" : "NA"} danger={(gate?.summary.fail_count ?? 0) > 0} />
              <MiniStatus label="Hot Terms" value={hotTerms ? "ON" : "NA"} />
              <MiniStatus label="Chain API" value={chain ? "ON" : "NA"} />
            </div>
          </div>
        </header>

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="space-y-4">
            <Toolbar
              mode={mode}
              setMode={setMode}
              query={query}
              setQuery={setQuery}
              roots={roots}
              rootFilter={rootFilter}
              setRootFilter={setRootFilter}
              systemOnly={systemOnly}
              setSystemOnly={setSystemOnly}
              depthLimit={depthLimit}
              setDepthLimit={setDepthLimit}
              resultCount={filteredRows.length}
            />

            {mode === "graph" ? (
              <KnowledgeGraph
                nodes={rows}
                visibleNodes={filteredRows}
                selectedId={selectedNode.id}
                overlays={overlays}
                onSelect={setSelectedId}
              />
            ) : null}

            {mode === "lanes" ? (
              <LaneView nodes={filteredRows} selectedId={selectedNode.id} overlays={overlays} onSelect={setSelectedId} />
            ) : null}

            {mode === "matrix" ? (
              <MatrixView nodes={filteredRows} selectedId={selectedNode.id} overlays={overlays} onSelect={setSelectedId} />
            ) : null}

            {mode === "evidence" ? (
              <EvidenceView nodes={filteredRows} overlays={overlays} selectedId={selectedNode.id} onSelect={setSelectedId} />
            ) : null}
          </div>

          <DetailPanel node={selectedNode} overlay={selectedOverlay} />
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center gap-2 text-sm font-black text-slate-900">
              <Target size={18} />
              七条主线变量
            </div>
            <div className="grid gap-3">
              {AI_INFRA_MAIN_VARIABLES.map((item, index) => (
                <div key={item.title} className="grid gap-3 rounded-2xl border border-slate-200 p-4 md:grid-cols-[44px_1fr]">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-sm font-black text-white">{index + 1}</div>
                  <div>
                    <div className="text-sm font-black text-slate-900">{item.title}</div>
                    <p className="mt-1 text-sm leading-6 text-slate-600">{item.summary}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="mb-4 flex items-center gap-2 text-sm font-black text-slate-900">
              <Boxes size={18} />
              后续数据表字段
            </div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
              {AI_INFRA_CORE_FIELDS.map((field) => (
                <div key={field} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700">{field}</div>
              ))}
            </div>
            <div className="mt-5 rounded-2xl border border-indigo-100 bg-indigo-50 p-4">
              <div className="text-xs font-black text-indigo-900">示例节点：1.6T光模块</div>
              <p className="mt-2 text-sm leading-6 text-indigo-900">
                上游 DSP、硅光芯片、激光器、光器件、PCB、封装；龙头中际旭创、新易盛、Coherent、Lumentum；客户 NVIDIA、Microsoft、Google、Meta、Amazon；跟踪800G出货、1.6T验证、毛利率和海外客户占比。
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function Toolbar({
  mode,
  setMode,
  query,
  setQuery,
  roots,
  rootFilter,
  setRootFilter,
  systemOnly,
  setSystemOnly,
  depthLimit,
  setDepthLimit,
  resultCount
}: {
  mode: ViewMode;
  setMode: (mode: ViewMode) => void;
  query: string;
  setQuery: (value: string) => void;
  roots: AiInfraFlatNode[];
  rootFilter: string;
  setRootFilter: (value: string) => void;
  systemOnly: boolean;
  setSystemOnly: (value: boolean) => void;
  depthLimit: number;
  setDepthLimit: (value: number) => void;
  resultCount: number;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-indigo-500" />
          <span className="text-xs font-bold text-slate-500">视图控制与筛选</span>
        </div>
        <Link 
          href="/research/ai-big-graph" 
          className="flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-1.5 text-xs font-black text-white shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-all"
        >
          <Share2 size={14} />
          进入 AI 大图谱 (新版)
        </Link>
      </div>
      <div className="grid gap-3 xl:grid-cols-[auto_minmax(220px,1fr)_220px_auto]">
        <div className="flex flex-wrap gap-2">
          {VIEW_MODES.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => setMode(item.value)}
                className={cn(
                  "inline-flex h-10 items-center gap-2 rounded-xl px-3 text-xs font-black transition-colors",
                  mode === item.value ? "bg-slate-950 text-white" : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                )}
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </div>
        <label className="flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3">
          <Search size={16} className="text-slate-400" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索节点、公司、指标、风险、关键字"
            className="min-w-0 flex-1 bg-transparent text-sm font-medium text-slate-700 outline-none placeholder:text-slate-400"
          />
        </label>
        <select
          value={rootFilter}
          onChange={(event) => setRootFilter(event.target.value)}
          className="h-10 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-bold text-slate-700 outline-none"
        >
          <option value="all">全部主链</option>
          {roots.map((root) => <option key={root.id} value={root.id}>{root.title}</option>)}
        </select>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSystemOnly(!systemOnly)}
            className={cn(
              "inline-flex h-10 items-center gap-2 rounded-xl px-3 text-xs font-black transition-colors",
              systemOnly ? "bg-indigo-600 text-white" : "bg-slate-50 text-slate-600 hover:bg-slate-100"
            )}
          >
            <Filter size={16} />
            系统命中
          </button>
          <select
            value={depthLimit}
            onChange={(event) => setDepthLimit(Number(event.target.value))}
            className="h-10 rounded-xl border border-slate-200 bg-slate-50 px-3 text-xs font-black text-slate-700 outline-none"
          >
            <option value={1}>1层</option>
            <option value={2}>2层</option>
            <option value={3}>全层级</option>
          </select>
          <div className="hidden h-10 items-center rounded-xl bg-slate-950 px-3 text-xs font-black text-white md:flex">{resultCount} nodes</div>
        </div>
      </div>
    </div>
  );
}

function KnowledgeGraph({
  nodes,
  visibleNodes,
  selectedId,
  overlays,
  onSelect
}: {
  nodes: AiInfraFlatNode[];
  visibleNodes: AiInfraFlatNode[];
  selectedId: string;
  overlays: Record<string, NodeOverlay>;
  onSelect: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(0.78);
  const [pan, setPan] = useState({ x: 12, y: 18 });
  const pointerRef = useRef<PointerState | null>(null);
  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const layout = useMemo(() => buildGraphLayout(nodes), [nodes]);
  const edges = useMemo(() => {
    const rows: Array<{ source: GraphPosition; target: GraphPosition; visible: boolean }> = [];
    for (const node of nodes) {
      if (!node.parentId) continue;
      const source = layout[node.parentId];
      const target = layout[node.id];
      if (source && target) rows.push({ source, target, visible: visibleIds.has(source.node.id) && visibleIds.has(target.node.id) });
    }
    return rows;
  }, [layout, nodes, visibleIds]);

  return (
    <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div>
          <div className="text-sm font-black text-slate-900">多层知识图</div>
          <div className="text-xs text-slate-500">滚轮缩放，拖拽平移，点击节点查看完整档案。</div>
        </div>
        <div className="flex gap-2">
          <IconButton icon={Minimize2} label="缩小" onClick={() => setZoom((value) => Math.max(0.48, value - 0.08))} />
          <IconButton icon={Maximize2} label="放大" onClick={() => setZoom((value) => Math.min(1.45, value + 0.08))} />
          <IconButton icon={RotateCcw} label="重置" onClick={() => { setZoom(0.78); setPan({ x: 12, y: 18 }); }} />
        </div>
      </div>
      <div className="h-[760px] bg-slate-50">
        <svg
          viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
          className="h-full w-full touch-none select-none"
          onWheel={(event) => {
            event.preventDefault();
            setZoom((value) => Math.max(0.48, Math.min(1.45, value + (event.deltaY > 0 ? -0.04 : 0.04))));
          }}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            pointerRef.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const pointer = pointerRef.current;
            if (!pointer) return;
            setPan({ x: pointer.panX + (event.clientX - pointer.x) / zoom, y: pointer.panY + (event.clientY - pointer.y) / zoom });
          }}
          onPointerUp={(event) => {
            pointerRef.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
        >
          <defs>
            <filter id="ai-node-shadow" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="8" stdDeviation="8" floodColor="#0f172a" floodOpacity="0.12" />
            </filter>
          </defs>
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            <g>
              {edges.map((edge) => (
                <path
                  key={`${edge.source.node.id}-${edge.target.node.id}`}
                  d={`M ${edge.source.x + 92} ${edge.source.y + 32} C ${edge.source.x + 92} ${edge.source.y + 92}, ${edge.target.x + 92} ${edge.target.y - 42}, ${edge.target.x + 92} ${edge.target.y}`}
                  fill="none"
                  stroke={edge.visible ? "#94a3b8" : "#e2e8f0"}
                  strokeWidth={edge.visible ? 1.8 : 1}
                  strokeDasharray={edge.visible ? "0" : "5 6"}
                />
              ))}
            </g>
            <g>
              {Object.values(layout).map((item) => {
                const visible = visibleIds.has(item.node.id);
                const selected = item.node.id === selectedId;
                const overlay = overlays[item.node.id] ?? emptyOverlay();
                return (
                  <GraphNodeCard
                    key={item.node.id}
                    item={item}
                    selected={selected}
                    visible={visible}
                    overlay={overlay}
                    onSelect={onSelect}
                  />
                );
              })}
            </g>
          </g>
        </svg>
      </div>
    </div>
  );
}

function GraphNodeCard({
  item,
  selected,
  visible,
  overlay,
  onSelect
}: {
  item: GraphPosition;
  selected: boolean;
  visible: boolean;
  overlay: NodeOverlay;
  onSelect: (id: string) => void;
}) {
  const color = ROOT_COLORS[item.rootIndex % ROOT_COLORS.length];
  const label = labelLines(item.node.title, item.node.depth === 0 ? 9 : 11);
  const hot = overlay.hotScore > 0;
  return (
    <g
      onClick={(event) => {
        event.stopPropagation();
        onSelect(item.node.id);
      }}
      className="cursor-pointer"
      opacity={visible ? 1 : 0.18}
      filter={visible ? "url(#ai-node-shadow)" : undefined}
    >
      <title>{item.node.path.join(" / ")}</title>
      <rect
        x={item.x}
        y={item.y}
        width={184}
        height={item.node.depth === 0 ? 74 : 64}
        rx={14}
        fill={selected ? "#0f172a" : "white"}
        stroke={selected ? "#0f172a" : hot ? "#f97316" : color}
        strokeWidth={selected ? 3 : hot ? 2.5 : 1.5}
      />
      <rect x={item.x} y={item.y} width={7} height={item.node.depth === 0 ? 74 : 64} rx={4} fill={hot ? "#f97316" : color} />
      <text x={item.x + 18} y={item.y + 25} fill={selected ? "white" : "#0f172a"} fontSize="13" fontWeight="900">
        {label.map((line, index) => <tspan key={line} x={item.x + 18} dy={index === 0 ? 0 : 16}>{line}</tspan>)}
      </text>
      <text x={item.x + 18} y={item.y + (item.node.depth === 0 ? 62 : 54)} fill={selected ? "#cbd5e1" : "#64748b"} fontSize="10" fontWeight="800">
        {item.node.layer}
      </text>
      {hot ? <circle cx={item.x + 164} cy={item.y + 18} r={8} fill="#f97316" /> : null}
      {overlay.chainMatches.length ? <circle cx={item.x + 164} cy={item.y + 42} r={7} fill="#2563eb" /> : null}
    </g>
  );
}

function LaneView({
  nodes,
  selectedId,
  overlays,
  onSelect
}: {
  nodes: AiInfraFlatNode[];
  selectedId: string;
  overlays: Record<string, NodeOverlay>;
  onSelect: (id: string) => void;
}) {
  const grouped = useMemo(() => {
    const map = new Map<string, AiInfraFlatNode[]>();
    for (const node of nodes) {
      const rootTitle = node.path[0] ?? node.title;
      map.set(rootTitle, [...(map.get(rootTitle) ?? []), node]);
    }
    return Array.from(map.entries());
  }, [nodes]);

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-sm font-black text-slate-900">
        <GitBranch size={18} />
        主链泳道
      </div>
      <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {grouped.map(([title, items], index) => (
          <div key={title} className="min-h-[220px] rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-black text-slate-900">{title}</div>
              <div className="h-2 w-16 rounded-full" style={{ backgroundColor: ROOT_COLORS[index % ROOT_COLORS.length] }} />
            </div>
            <div className="space-y-2">
              {items.map((node) => {
                const overlay = overlays[node.id] ?? emptyOverlay();
                return (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => onSelect(node.id)}
                    className={cn(
                      "w-full rounded-xl border bg-white p-3 text-left transition-colors",
                      selectedId === node.id ? "border-slate-950 ring-2 ring-slate-950/10" : "border-slate-200 hover:border-slate-300"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-black text-slate-900">{node.title}</div>
                      <div className="flex gap-1">
                        {overlay.hotTerms.length ? <SignalDot tone="hot" /> : null}
                        {overlay.chainMatches.length ? <SignalDot tone="system" /> : null}
                      </div>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">{node.summary}</p>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MatrixView({
  nodes,
  selectedId,
  overlays,
  onSelect
}: {
  nodes: AiInfraFlatNode[];
  selectedId: string;
  overlays: Record<string, NodeOverlay>;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2 text-sm font-black text-slate-900">
          <Table2 size={18} />
          全量节点矩阵
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-[1180px] w-full border-collapse text-left">
          <thead className="bg-slate-50 text-[10px] uppercase tracking-widest text-slate-400">
            <tr>
              <th className="px-4 py-3">节点</th>
              <th className="px-4 py-3">层级</th>
              <th className="px-4 py-3">核心玩家</th>
              <th className="px-4 py-3">口径/份额</th>
              <th className="px-4 py-3">投研跟踪</th>
              <th className="px-4 py-3">系统增强</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {nodes.map((node) => {
              const overlay = overlays[node.id] ?? emptyOverlay();
              return (
                <tr
                  key={node.id}
                  onClick={() => onSelect(node.id)}
                  className={cn("cursor-pointer align-top transition-colors hover:bg-slate-50", selectedId === node.id ? "bg-indigo-50/70" : "bg-white")}
                >
                  <td className="px-4 py-4">
                    <div className="text-sm font-black text-slate-900">{node.title}</div>
                    <div className="mt-1 line-clamp-3 max-w-sm text-xs leading-5 text-slate-500">{node.summary}</div>
                  </td>
                  <td className="px-4 py-4 text-xs font-bold text-slate-600">{node.path.join(" / ")}</td>
                  <td className="px-4 py-4 text-xs leading-5 text-slate-600">{node.players?.slice(0, 2).map((group) => `${group.group}: ${group.names.slice(0, 5).join(", ")}`).join("；") || "待补充"}</td>
                  <td className="px-4 py-4 text-xs leading-5 text-slate-600">{node.metrics?.map((metric) => `${metric.label}: ${metric.value}`).join("；") || "无精确份额"}</td>
                  <td className="px-4 py-4 text-xs leading-5 text-slate-600">{node.trackingIndicators?.slice(0, 5).join(" / ") || "待跟踪"}</td>
                  <td className="px-4 py-4">
                    <div className="flex flex-wrap gap-1">
                      {overlay.hotTerms.slice(0, 3).map((term) => <TonePill key={term.term} label={term.term} tone="warn" />)}
                      {overlay.chainMatches.slice(0, 2).map((item) => <TonePill key={item.node_key} label={item.name} tone="pass" />)}
                      {!overlay.hotTerms.length && !overlay.chainMatches.length ? <span className="text-xs text-slate-400">无系统命中</span> : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EvidenceView({
  nodes,
  overlays,
  selectedId,
  onSelect
}: {
  nodes: AiInfraFlatNode[];
  overlays: Record<string, NodeOverlay>;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const metricRows = nodes.flatMap((node) => (node.metrics ?? []).map((metric) => ({ node, metric })));
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-sm font-black text-slate-900">
        <Database size={18} />
        证据口径与系统映射
      </div>
      <div className="grid gap-3">
        {metricRows.map(({ node, metric }, index) => {
          const overlay = overlays[node.id] ?? emptyOverlay();
          return (
            <button
              key={`${node.id}-${metric.label}-${index}`}
              type="button"
              onClick={() => onSelect(node.id)}
              className={cn(
                "rounded-2xl border p-4 text-left transition-colors",
                selectedId === node.id ? "border-slate-950 bg-slate-50" : "border-slate-200 hover:border-slate-300"
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-black text-slate-900">{node.title}</div>
                  <div className="mt-1 text-xs font-bold text-slate-500">{metric.label}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {metric.source ? <TonePill label={metric.source} /> : null}
                  {metric.scope ? <TonePill label={metric.scope} tone="pass" /> : null}
                  {overlay.hotTerms.length ? <TonePill label={`${overlay.hotTerms.length} hot`} tone="warn" /> : null}
                </div>
              </div>
              <div className="mt-3 text-sm font-black text-slate-900">{metric.value}</div>
              {metric.caution ? <p className="mt-2 text-sm leading-6 text-amber-800">{metric.caution}</p> : null}
            </button>
          );
        })}
        {!metricRows.length ? <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">当前筛选下没有口径数据</div> : null}
      </div>
    </div>
  );
}

function DetailPanel({ node, overlay }: { node: AiInfraFlatNode; overlay: NodeOverlay }) {
  return (
    <aside className="xl:sticky xl:top-24 xl:self-start">
      <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{node.path.join(" / ")}</div>
              <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">{node.title}</h2>
            </div>
            <TonePill label={node.layer} tone="neutral" />
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600">{node.summary}</p>
        </div>
        <div className="max-h-[calc(100vh-190px)] space-y-5 overflow-y-auto p-5">
          <DetailSignals overlay={overlay} />
          <DetailSection title="受益逻辑" items={node.logic} empty="暂无单独逻辑，见节点摘要。" icon={Zap} />
          <PlayerGroups groups={node.players} />
          <MetricGroups metrics={node.metrics} />
          <DetailSection title="投研关键" items={node.investmentKeys} empty="待补充投研关键。" icon={Eye} />
          <DetailSection title="关键跟踪指标" items={node.trackingIndicators} empty="待补充跟踪指标。" icon={Activity} />
          <DetailSection title="风险因素" items={node.risks} empty="待补充风险因素。" icon={AlertTriangle} danger />
          <RelationSection title="上游" items={node.upstream} />
          <RelationSection title="下游" items={node.downstream} />
          <RelationSection title="相关热词" items={node.relatedTerms} />
          {node.children?.length ? (
            <div>
              <div className="mb-2 text-xs font-black text-slate-900">子节点</div>
              <div className="flex flex-wrap gap-2">
                {node.children.map((child) => <TonePill key={child.id} label={child.title} />)}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}

function DetailSignals({ overlay }: { overlay: NodeOverlay }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex items-center gap-2 text-xs font-black text-slate-900">
        <Flame size={16} />
        系统动态增强
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <MiniStatus label="Hot" value={overlay.hotTerms.length} />
        <MiniStatus label="Chain" value={overlay.chainMatches.length} />
        <MiniStatus label="Score" value={overlay.hotScore.toFixed(0)} danger={overlay.hotScore > 80} />
      </div>
      <div className="mt-3 space-y-2">
        {overlay.hotTerms.slice(0, 4).map((term) => (
          <Link key={term.term} href="/research/hot-terms" className="block rounded-xl bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-indigo-50">
            {term.term} · score {term.score.toFixed(1)} · mentions {term.mentions}
          </Link>
        ))}
        {overlay.chainMatches.slice(0, 4).map((item) => (
          <Link key={item.node_key} href="/research/industry-chain" className="block rounded-xl bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-emerald-50">
            {item.name} · {item.layer} · heat {Number(item.heat ?? 0).toFixed(1)}
          </Link>
        ))}
        {!overlay.hotTerms.length && !overlay.chainMatches.length ? <div className="text-xs leading-5 text-slate-500">暂无系统热词或产业图谱命中，按静态知识树观察。</div> : null}
      </div>
    </div>
  );
}

function PlayerGroups({ groups }: { groups?: AiInfraFlatNode["players"] }) {
  if (!groups?.length) return <DetailSection title="核心玩家" empty="待补充核心玩家。" icon={Layers3} />;
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-black text-slate-900"><Layers3 size={16} />核心玩家</div>
      <div className="space-y-3">
        {groups.map((group) => (
          <div key={group.group} className="rounded-2xl border border-slate-200 p-3">
            <div className="text-xs font-black text-slate-900">{group.group}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {group.names.map((name) => <TonePill key={name} label={name} />)}
            </div>
            {group.note ? <p className="mt-2 text-xs leading-5 text-slate-500">{group.note}</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricGroups({ metrics }: { metrics?: AiInfraMetric[] }) {
  if (!metrics?.length) return <DetailSection title="市场口径" empty="无精确份额或规模口径，避免强行编数。" icon={Database} />;
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-black text-slate-900"><Database size={16} />市场口径</div>
      <div className="space-y-3">
        {metrics.map((metric) => (
          <div key={`${metric.label}-${metric.value}`} className="rounded-2xl border border-slate-200 p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="text-xs font-black text-slate-900">{metric.label}</div>
              <div className="flex flex-wrap gap-1">
                {metric.source ? <TonePill label={metric.source} /> : null}
                {metric.scope ? <TonePill label={metric.scope} tone="pass" /> : null}
              </div>
            </div>
            <div className="mt-2 text-sm font-black text-slate-900">{metric.value}</div>
            {metric.caution ? <p className="mt-2 text-xs leading-5 text-amber-800">{metric.caution}</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function DetailSection({ title, items, empty, icon: Icon, danger = false }: { title: string; items?: string[]; empty: string; icon: LucideIcon; danger?: boolean }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs font-black text-slate-900"><Icon size={16} />{title}</div>
      <div className="space-y-2">
        {(items?.length ? items : [empty]).map((item) => (
          <div key={item} className={cn("rounded-xl px-3 py-2 text-xs leading-5", danger ? "bg-rose-50 text-rose-900" : "bg-slate-50 text-slate-600")}>{item}</div>
        ))}
      </div>
    </div>
  );
}

function RelationSection({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="mb-2 text-xs font-black text-slate-900">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.map((item) => <TonePill key={item} label={item} />)}
      </div>
    </div>
  );
}

type GraphPosition = {
  node: AiInfraFlatNode;
  x: number;
  y: number;
  rootIndex: number;
};

function buildGraphLayout(nodes: AiInfraFlatNode[]): Record<string, GraphPosition> {
  const roots = nodes.filter((node) => node.depth === 0);
  const layout: Record<string, GraphPosition> = {};
  roots.forEach((root, rootIndex) => {
    const x = 82 + rootIndex * 202;
    layout[root.id] = { node: root, x, y: 40, rootIndex };
    const descendants = nodes.filter((node) => node.rootId === root.id && node.depth > 0);
    descendants.forEach((node, index) => {
      layout[node.id] = {
        node,
        x,
        y: 148 + index * 86,
        rootIndex
      };
    });
  });
  return layout;
}

function buildOverlays(rows: AiInfraFlatNode[], hotTerms: ResearchHotTerms | null, chain: ChainOverview | null): Record<string, NodeOverlay> {
  const overlays: Record<string, NodeOverlay> = {};
  for (const node of rows) {
    const tokens = nodeTokens(node);
    const matchedHotTerms = (hotTerms?.hot_terms ?? [])
      .filter((term) => tokens.some((token) => containsEither(term.term, token) || term.industries.some((industry) => containsEither(industry.label, token))))
      .slice(0, 8);
    const matchedChainNodes = (chain?.nodes ?? [])
      .filter((item) => tokens.some((token) => containsEither(item.name, token) || containsEither(item.layer, token) || item.industry_names?.some((name) => containsEither(name, token))))
      .slice(0, 8);
    overlays[node.id] = {
      hotScore: matchedHotTerms.reduce((sum, term) => sum + term.score, 0),
      hotTerms: matchedHotTerms,
      chainMatches: matchedChainNodes,
      systemTags: [...matchedHotTerms.map((term) => term.term), ...matchedChainNodes.map((item) => item.name)]
    };
  }
  return overlays;
}

function nodeMatchesQuery(node: AiInfraFlatNode, query: string): boolean {
  const q = query.trim().toLowerCase();
  const content = [
    node.title,
    node.layer,
    node.summary,
    ...node.path,
    ...(node.relatedTerms ?? []),
    ...(node.investmentKeys ?? []),
    ...(node.risks ?? []),
    ...(node.trackingIndicators ?? []),
    ...(node.players?.flatMap((group) => [group.group, group.note ?? "", ...group.names]) ?? []),
    ...(node.metrics?.flatMap((metric) => [metric.label, metric.value, metric.scope ?? "", metric.source ?? "", metric.caution ?? ""]) ?? [])
  ].join(" ").toLowerCase();
  return content.includes(q);
}

function nodeTokens(node: AiInfraFlatNode): string[] {
  const raw = [
    node.title,
    node.layer,
    ...node.path,
    ...(node.relatedTerms ?? []),
    ...(node.players?.flatMap((group) => group.names) ?? [])
  ];
  return Array.from(new Set(raw.flatMap((item) => splitToken(item)).filter((item) => item.length >= 2))).slice(0, 80);
}

function splitToken(value: string): string[] {
  return value
    .replace(/[()/,，、：:|]/g, " ")
    .split(/\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function containsEither(a: string, b: string): boolean {
  const left = a.toLowerCase();
  const right = b.toLowerCase();
  if (!left || !right) return false;
  return left.includes(right) || right.includes(left);
}

function emptyOverlay(): NodeOverlay {
  return { hotScore: 0, hotTerms: [], chainMatches: [], systemTags: [] };
}

function Metric({ label, value, detail, tone = "neutral" }: { label: string; value: string | number; detail: string; tone?: "neutral" | "hot" | "system" }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className={cn("mt-2 text-2xl font-black", tone === "hot" ? "text-orange-600" : tone === "system" ? "text-indigo-600" : "text-slate-950")}>{value}</div>
      <div className="mt-1 text-xs leading-5 text-slate-500">{detail}</div>
    </div>
  );
}

function MiniStatus({ label, value, danger = false }: { label: string; value: string | number; danger?: boolean }) {
  return (
    <div className={cn("rounded-xl px-3 py-2", danger ? "bg-rose-50 text-rose-700" : "bg-slate-50 text-slate-700")}>
      <div className="text-[9px] font-black uppercase tracking-widest opacity-70">{label}</div>
      <div className="mt-1 text-sm font-black">{value}</div>
    </div>
  );
}

function SignalDot({ tone }: { tone: "hot" | "system" }) {
  return <span className={cn("h-2.5 w-2.5 rounded-full", tone === "hot" ? "bg-orange-500" : "bg-indigo-500")} />;
}

function IconButton({ icon: Icon, label, onClick }: { icon: LucideIcon; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      title={label}
      onClick={onClick}
      className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-slate-50 text-slate-600 transition-colors hover:bg-slate-100"
    >
      <Icon size={16} />
    </button>
  );
}

function labelLines(value: string, maxLength: number): string[] {
  if (value.length <= maxLength) return [value];
  const first = value.slice(0, maxLength);
  const second = value.slice(maxLength, maxLength * 2 - 1);
  return [first, second.length === maxLength - 1 && value.length > maxLength * 2 - 1 ? `${second}...` : second].filter(Boolean);
}

