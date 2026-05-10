"use client";

import { useMemo } from "react";
import { ArrowRight, Flame, Network } from "lucide-react";
import type { ChainEdge, ChainNode } from "@/lib/api";

type IndustryPlaneHeatMapProps = {
  nodes: ChainNode[];
  edges: ChainEdge[];
  selectedNodeKey: string | null;
  activeLayer: string;
  query: string;
  onSelect: (nodeKey: string) => void;
};

type RenderNode = {
  node: ChainNode;
  layer: string;
  layerIndex: number;
  order: number;
  x: number;
  y: number;
  width: number;
  height: number;
  heat: number;
  intensity: number;
  visible: boolean;
  matched: boolean;
  connected: boolean;
  degree: number;
};

type RenderEdge = {
  edge: ChainEdge;
  source: RenderNode;
  target: RenderNode;
  intensity: number;
  active: boolean;
};

type LayerBand = {
  key: string;
  label: string;
  x: number;
  width: number;
  count: number;
  visibleCount: number;
  active: boolean;
};

type PlaneModel = {
  width: number;
  height: number;
  layers: LayerBand[];
  nodes: RenderNode[];
  edges: RenderEdge[];
  selectedName: string;
  visibleNodeCount: number;
  visibleEdgeCount: number;
  matchedNodeCount: number;
  maxHeat: number;
};

const PADDING_X = 56;
const PADDING_TOP = 92;
const PADDING_BOTTOM = 56;
const LAYER_GAP = 28;
const LAYER_WIDTH = 248;
const CARD_WIDTH = 212;
const CARD_HEIGHT = 84;
const CARD_GAP = 18;
const CARD_INSET_X = 18;

export function IndustryPlaneHeatMap({
  nodes,
  edges,
  selectedNodeKey,
  activeLayer,
  query,
  onSelect
}: IndustryPlaneHeatMapProps) {
  const model = useMemo(
    () => buildPlaneModel(nodes, edges, selectedNodeKey, activeLayer, query),
    [activeLayer, edges, nodes, query, selectedNodeKey]
  );

  return (
    <div className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#f7e9de] px-5 py-4">
        <div>
          <div className="text-sm font-semibold text-slate-950">全产业链平面热力总图</div>
          <div className="mt-1 text-xs text-slate-500">
            {model.selectedName ? `${model.selectedName} 已高亮 / ` : ""}
            {model.visibleNodeCount} 个节点 / {model.visibleEdgeCount} 条关系 / {model.layers.length} 个层级
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <MetricPill icon={Network} label="可见节点" value={String(model.visibleNodeCount)} />
          <MetricPill icon={ArrowRight} label="可见连线" value={String(model.visibleEdgeCount)} />
          <MetricPill icon={Flame} label="命中查询" value={String(model.matchedNodeCount)} />
        </div>
      </div>

      <div className="overflow-x-auto overflow-y-hidden bg-[#fffdfa]">
        <svg
          viewBox={`0 0 ${model.width} ${model.height}`}
          role="img"
          aria-label="按产业层级平面展开的热力总图"
          className="block min-w-full"
          style={{ height: Math.min(model.height, 920) }}
        >
          <defs>
            <linearGradient id="plane-surface" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stopColor="#ffffff" />
              <stop offset="0.58" stopColor="#fffaf5" />
              <stop offset="1" stopColor="#fff5eb" />
            </linearGradient>
            <linearGradient id="plane-edge" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#facc15" />
              <stop offset="0.58" stopColor="#f97316" />
              <stop offset="1" stopColor="#dc2626" />
            </linearGradient>
            <filter id="plane-card-shadow" x="-20%" y="-20%" width="150%" height="170%">
              <feDropShadow dx="0" dy="12" stdDeviation="14" floodColor="#7c2d12" floodOpacity="0.08" />
            </filter>
          </defs>

          <rect width={model.width} height={model.height} fill="url(#plane-surface)" />

          {model.layers.map((layer) => (
            <g key={layer.key} transform={`translate(${layer.x} 0)`}>
              <rect
                x="0"
                y="28"
                width={layer.width}
                height={model.height - 56}
                rx="18"
                fill={layer.active ? "#fff7ed" : "#ffffff"}
                stroke={layer.active ? "#fdba74" : "#f3e1d4"}
                strokeWidth={layer.active ? 1.4 : 1}
              />
              <text x={layer.width / 2} y="58" textAnchor="middle" fill="#111827" fontSize="15" fontWeight="800">
                {layer.label}
              </text>
              <text x={layer.width / 2} y="78" textAnchor="middle" fill="#9a3412" fontSize="11.5" fontWeight="650">
                {layer.visibleCount}/{layer.count} 节点
              </text>
            </g>
          ))}

          <g fill="none">
            {model.edges.map((item) => {
              const sourceX = item.source.x + item.source.width;
              const sourceY = item.source.y + item.source.height / 2;
              const targetX = item.target.x;
              const targetY = item.target.y + item.target.height / 2;
              const curve = Math.max(48, (targetX - sourceX) * 0.42);
              return (
                <path
                  key={`${item.edge.source}-${item.edge.target}-${item.edge.relation_type ?? ""}-${item.edge.flow ?? ""}`}
                  d={`M ${sourceX} ${sourceY} C ${sourceX + curve} ${sourceY}, ${targetX - curve} ${targetY}, ${targetX} ${targetY}`}
                  stroke={item.active ? warmColor(item.intensity) : "url(#plane-edge)"}
                  strokeWidth={item.active ? 3 + item.intensity * 2.8 : 1.1 + item.intensity * 2.6}
                  strokeOpacity={item.active ? 0.78 : 0.16 + item.intensity * 0.28}
                  strokeLinecap="round"
                />
              );
            })}
          </g>

          <g>
            {model.nodes.map((item) => {
              const active = item.node.node_key === selectedNodeKey;
              const color = warmColor(item.intensity);
              const haloOpacity = active ? 0.16 : item.connected ? 0.12 : 0.08;
              return (
                <g
                  key={item.node.node_key}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(item.node.node_key)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(item.node.node_key);
                    }
                  }}
                  className="cursor-pointer outline-none"
                >
                  <rect
                    x={item.x - 10}
                    y={item.y - 10}
                    width={item.width + 20}
                    height={item.height + 20}
                    rx="24"
                    fill={color}
                    opacity={haloOpacity}
                  />
                  <rect
                    x={item.x}
                    y={item.y}
                    width={item.width}
                    height={item.height}
                    rx="18"
                    fill="#ffffff"
                    stroke={active ? "#ea580c" : item.connected ? "#fb923c" : item.matched ? "#fdba74" : "#f2dfd2"}
                    strokeWidth={active ? 2.4 : item.connected ? 1.7 : 1}
                    filter="url(#plane-card-shadow)"
                  />
                  <rect x={item.x} y={item.y} width="10" height={item.height} rx="5" fill={color} />
                  <text x={item.x + 24} y={item.y + 26} fill="#111827" fontSize="14" fontWeight="800">
                    {clipLabel(item.node.name, 14)}
                  </text>
                  <text x={item.x + 24} y={item.y + 46} fill="#9a3412" fontSize="11.5" fontWeight="650">
                    {clipLabel(item.node.node_type || item.layer, 16)}
                  </text>
                  <rect x={item.x + 24} y={item.y + 58} width="104" height="8" rx="4" fill="#ffedd5" />
                  <rect x={item.x + 24} y={item.y + 58} width={104 * Math.max(item.intensity, 0.08)} height="8" rx="4" fill={color} />
                  <text x={item.x + item.width - 16} y={item.y + 26} textAnchor="end" fill={color} fontSize="12" fontWeight="800">
                    {item.heat.toFixed(1)}
                  </text>
                  <text x={item.x + item.width - 16} y={item.y + 46} textAnchor="end" fill="#64748b" fontSize="11">
                    {formatAnchor(item.node)}
                  </text>
                  <title>{`${item.node.name}｜${item.layer}｜热度 ${item.heat.toFixed(1)}`}</title>
                </g>
              );
            })}
          </g>

          <g transform={`translate(${PADDING_X} ${model.height - 26})`}>
            <text fill="#94a3b8" fontSize="11.5">
              白底黄橙红热力：黄=温和，橙=升温，深橙=活跃，红=高热
            </text>
          </g>
        </svg>
      </div>
    </div>
  );
}

function MetricPill({
  icon: Icon,
  label,
  value
}: {
  icon: typeof Flame;
  label: string;
  value: string;
}) {
  return (
    <div className="inline-flex items-center gap-2 rounded-md border border-[#f2dfd2] bg-white px-3 py-2 text-slate-600">
      <Icon size={14} className="text-orange-600" />
      <span>{label}</span>
      <span className="font-semibold text-slate-950">{value}</span>
    </div>
  );
}

function buildPlaneModel(
  nodes: ChainNode[],
  edges: ChainEdge[],
  selectedNodeKey: string | null,
  activeLayer: string,
  query: string
): PlaneModel {
  const lowered = query.trim().toLowerCase();
  const maxHeat = Math.max(...nodes.map(nodeHeat), 1);
  const layers = orderLayers(nodes, edges);
  const layerIndexByKey = new Map(layers.map((layer, index) => [layer, index]));
  const selectionContext = buildSelectionContext(edges, selectedNodeKey);

  const adjacency = new Map<string, string[]>();
  const reverseAdjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const forward = adjacency.get(edge.source) ?? [];
    forward.push(edge.target);
    adjacency.set(edge.source, forward);
    const reverse = reverseAdjacency.get(edge.target) ?? [];
    reverse.push(edge.source);
    reverseAdjacency.set(edge.target, reverse);
  }

  const degreeByNode = new Map<string, number>();
  for (const node of nodes) {
    degreeByNode.set(node.node_key, (adjacency.get(node.node_key)?.length ?? 0) + (reverseAdjacency.get(node.node_key)?.length ?? 0));
  }

  const initialGroups = new Map<string, ChainNode[]>();
  for (const node of nodes) {
    const layer = node.layer || "未分类";
    const rows = initialGroups.get(layer) ?? [];
    rows.push(node);
    initialGroups.set(layer, rows);
  }

  const orderedGroups = refineNodeOrder(layers, initialGroups, adjacency, reverseAdjacency, degreeByNode);
  const renderNodes: RenderNode[] = [];
  const layerBands: LayerBand[] = [];
  let maxLayerHeight = 0;

  for (const [layerIndex, layer] of layers.entries()) {
    const group = orderedGroups.get(layer) ?? [];
    const active = activeLayer === "all" || normalizeLayerKey(layer) === activeLayer;
    const visibleGroup = group.filter((node) => {
      const matched = matchesNode(node, lowered);
      const layerVisible = activeLayer === "all" || normalizeLayerKey(node.layer) === activeLayer;
      const connected = selectionContext.has(node.node_key);
      return (!lowered || matched) && layerVisible || connected;
    });
    const count = group.length;
    const visibleCount = visibleGroup.length;
    const x = PADDING_X + layerIndex * (LAYER_WIDTH + LAYER_GAP);
    const height = Math.max(0, visibleCount) * (CARD_HEIGHT + CARD_GAP);
    maxLayerHeight = Math.max(maxLayerHeight, height);
    layerBands.push({
      key: normalizeLayerKey(layer),
      label: layer,
      x,
      width: LAYER_WIDTH,
      count,
      visibleCount,
      active
    });

    let order = 0;
    for (const node of group) {
      const matched = matchesNode(node, lowered);
      const layerVisible = activeLayer === "all" || normalizeLayerKey(node.layer) === activeLayer;
      const connected = selectionContext.has(node.node_key);
      const visible = ((!lowered || matched) && layerVisible) || connected;
      if (!visible) continue;
      const y = PADDING_TOP + order * (CARD_HEIGHT + CARD_GAP);
      renderNodes.push({
        node,
        layer,
        layerIndex,
        order,
        x: x + CARD_INSET_X,
        y,
        width: CARD_WIDTH,
        height: CARD_HEIGHT,
        heat: nodeHeat(node),
        intensity: normalizeIntensity(node, maxHeat),
        visible,
        matched,
        connected,
        degree: degreeByNode.get(node.node_key) ?? 0
      });
      order += 1;
    }
  }

  const nodeMap = new Map(renderNodes.map((node) => [node.node.node_key, node]));
  const renderEdges = edges.flatMap<RenderEdge>((edge) => {
    const source = nodeMap.get(edge.source);
    const target = nodeMap.get(edge.target);
    if (!source || !target) return [];
    const intensity = Math.min(
      Math.max(source.intensity, target.intensity, normalize(edge.intensity), normalize(edge.weight), normalize(edge.heat)),
      1
    );
    return [{
      edge,
      source,
      target,
      intensity,
      active: isEdgeActive(edge, selectedNodeKey)
    }];
  });

  const width = Math.max(1180, PADDING_X * 2 + layers.length * LAYER_WIDTH + Math.max(layers.length - 1, 0) * LAYER_GAP);
  const height = Math.max(560, PADDING_TOP + maxLayerHeight + PADDING_BOTTOM);

  return {
    width,
    height,
    layers: layerBands,
    nodes: renderNodes,
    edges: renderEdges,
    selectedName: nodes.find((node) => node.node_key === selectedNodeKey)?.name ?? "",
    visibleNodeCount: renderNodes.length,
    visibleEdgeCount: renderEdges.length,
    matchedNodeCount: renderNodes.filter((node) => node.matched).length,
    maxHeat
  };
}

function orderLayers(nodes: ChainNode[], edges: ChainEdge[]) {
  const layers = Array.from(new Set(nodes.map((node) => node.layer || "未分类")));
  const nodeLayer = new Map(nodes.map((node) => [node.node_key, node.layer || "未分类"]));
  const nextLayers = new Map<string, Set<string>>();
  const indegree = new Map<string, number>(layers.map((layer) => [layer, 0]));

  for (const edge of edges) {
    const sourceLayer = nodeLayer.get(edge.source);
    const targetLayer = nodeLayer.get(edge.target);
    if (!sourceLayer || !targetLayer || sourceLayer === targetLayer) continue;
    const bucket = nextLayers.get(sourceLayer) ?? new Set<string>();
    if (!bucket.has(targetLayer)) {
      bucket.add(targetLayer);
      nextLayers.set(sourceLayer, bucket);
      indegree.set(targetLayer, (indegree.get(targetLayer) ?? 0) + 1);
    }
  }

  const queue = layers.filter((layer) => (indegree.get(layer) ?? 0) === 0).sort((left, right) => left.localeCompare(right));
  const ordered: string[] = [];
  while (queue.length) {
    const layer = queue.shift();
    if (!layer) break;
    ordered.push(layer);
    for (const next of nextLayers.get(layer) ?? []) {
      indegree.set(next, (indegree.get(next) ?? 0) - 1);
      if ((indegree.get(next) ?? 0) === 0) {
        queue.push(next);
        queue.sort((left, right) => left.localeCompare(right));
      }
    }
  }

  for (const layer of layers.sort((left, right) => left.localeCompare(right))) {
    if (!ordered.includes(layer)) ordered.push(layer);
  }
  return ordered;
}

function refineNodeOrder(
  layers: string[],
  initialGroups: Map<string, ChainNode[]>,
  adjacency: Map<string, string[]>,
  reverseAdjacency: Map<string, string[]>,
  degreeByNode: Map<string, number>
) {
  const orderedGroups = new Map<string, ChainNode[]>();
  for (const layer of layers) {
    const group = [...(initialGroups.get(layer) ?? [])].sort((left, right) => {
      return degreeSort(left, right, degreeByNode);
    });
    orderedGroups.set(layer, group);
  }

  for (let round = 0; round < 3; round += 1) {
    const position = new Map<string, number>();
    for (const layer of layers) {
      (orderedGroups.get(layer) ?? []).forEach((node, index) => {
        position.set(node.node_key, index);
      });
    }

    for (const layer of layers) {
      const group = [...(orderedGroups.get(layer) ?? [])];
      group.sort((left, right) => {
        const leftScore = barycenter(left.node_key, adjacency, reverseAdjacency, position);
        const rightScore = barycenter(right.node_key, adjacency, reverseAdjacency, position);
        if (leftScore !== rightScore) return leftScore - rightScore;
        return degreeSort(left, right, degreeByNode);
      });
      orderedGroups.set(layer, group);
    }
  }

  return orderedGroups;
}

function buildSelectionContext(edges: ChainEdge[], selectedNodeKey: string | null) {
  const context = new Set<string>();
  if (!selectedNodeKey) return context;
  context.add(selectedNodeKey);
  for (const edge of edges) {
    if (edge.source === selectedNodeKey) context.add(edge.target);
    if (edge.target === selectedNodeKey) context.add(edge.source);
  }
  return context;
}

function barycenter(
  nodeKey: string,
  adjacency: Map<string, string[]>,
  reverseAdjacency: Map<string, string[]>,
  position: Map<string, number>
) {
  const neighbors = [...(adjacency.get(nodeKey) ?? []), ...(reverseAdjacency.get(nodeKey) ?? [])];
  if (!neighbors.length) return Number.MAX_SAFE_INTEGER / 2;
  const scores = neighbors
    .map((key) => position.get(key))
    .filter((value): value is number => typeof value === "number");
  if (!scores.length) return Number.MAX_SAFE_INTEGER / 2;
  return scores.reduce((sum, value) => sum + value, 0) / scores.length;
}

function degreeSort(left: ChainNode, right: ChainNode, degreeByNode: Map<string, number>) {
  const degreeDelta = (degreeByNode.get(right.node_key) ?? 0) - (degreeByNode.get(left.node_key) ?? 0);
  if (degreeDelta !== 0) return degreeDelta;
  const heatDelta = nodeHeat(right) - nodeHeat(left);
  if (heatDelta !== 0) return heatDelta;
  return left.name.localeCompare(right.name);
}

function isEdgeActive(edge: ChainEdge, selectedNodeKey: string | null) {
  if (!selectedNodeKey) return false;
  return edge.source === selectedNodeKey || edge.target === selectedNodeKey;
}

function matchesNode(node: ChainNode, query: string) {
  if (!query) return true;
  return [node.name, node.node_key, node.layer, node.node_type, ...(node.industry_names ?? []), ...(node.tags ?? [])]
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function nodeHeat(node: ChainNode) {
  return Math.max(node.heat ?? 0, node.momentum ?? 0, (node.intensity ?? 0) * 100);
}

function normalizeIntensity(node: ChainNode, maxHeat: number) {
  const fromIntensity = normalize(node.intensity);
  if (fromIntensity > 0) return Math.min(Math.max(fromIntensity, 0), 1);
  return Math.min(Math.max(nodeHeat(node) / Math.max(maxHeat, 1), 0), 1);
}

function normalize(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return value > 1 ? value / 100 : value;
}

function normalizeLayerKey(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function warmColor(intensity: number) {
  if (intensity >= 0.86) return "#b91c1c";
  if (intensity >= 0.64) return "#ea580c";
  if (intensity >= 0.38) return "#f59e0b";
  return "#facc15";
}

function clipLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function formatAnchor(node: ChainNode) {
  if (node.anchor_companies?.length) return clipLabel(node.anchor_companies.slice(0, 2).join(" / "), 18);
  if (typeof node.stock_count === "number") return `${node.stock_count} 股`;
  return clipLabel(node.layer || "", 12);
}
