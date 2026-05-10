"use client";

import { useMemo } from "react";
import type { ChainEdge, ChainNode, ChainNodeDetail } from "@/lib/api";

type IndustryChainMapProps = {
  detail: ChainNodeDetail | null;
  onSelect: (nodeKey: string) => void;
  allNodes?: ChainNode[];
  allEdges?: ChainEdge[];
  selectedNodeKey?: string | null;
};

type RelationRole = "focus" | "upstream" | "downstream" | "bridge" | "peer";

type RenderNode = {
  node: ChainNode;
  role: RelationRole;
  depth: number;
  x: number;
  y: number;
  r: number;
  heat: number;
  intensity: number;
  degree: number;
  label: boolean;
};

type RenderLink = {
  edge: ChainEdge;
  source: RenderNode;
  target: RenderNode;
  intensity: number;
  active: boolean;
};

type GraphModel = {
  focus: ChainNode | null;
  nodes: RenderNode[];
  links: RenderLink[];
  counts: Record<RelationRole, number>;
  maxDepth: number;
};

const VIEW_WIDTH = 1120;
const VIEW_HEIGHT = 760;
const CX = 560;
const CY = 374;
const ROLE_STYLES: Record<RelationRole, { label: string; color: string; stroke: string; start: number; end: number }> = {
  focus: { label: "当前节点", color: "#f97316", stroke: "#c2410c", start: 0, end: 360 },
  upstream: { label: "上游输入", color: "#f59e0b", stroke: "#b45309", start: 128, end: 252 },
  downstream: { label: "下游扩散", color: "#ef4444", stroke: "#b91c1c", start: -52, end: 72 },
  bridge: { label: "桥接循环", color: "#8b5cf6", stroke: "#6d28d9", start: 252, end: 336 },
  peer: { label: "同层联动", color: "#14b8a6", stroke: "#0f766e", start: 76, end: 126 }
};

export function IndustryChainMap({ detail, onSelect, allNodes, allEdges, selectedNodeKey }: IndustryChainMapProps) {
  const model = useMemo(
    () => buildGraph({ detail, allNodes, allEdges, selectedNodeKey }),
    [allEdges, allNodes, detail, selectedNodeKey]
  );

  if (!model.focus) {
    return <div className="flex h-[720px] items-center justify-center bg-white text-sm text-slate-500">未选择节点</div>;
  }

  return (
    <div className="h-[720px] min-h-[620px] w-full overflow-hidden bg-white">
      <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} role="img" aria-label={`${model.focus.name} 产业链关系场`} className="h-full w-full">
        <defs>
          <radialGradient id="focus-chain-bg" cx="50%" cy="48%" r="72%">
            <stop offset="0" stopColor="#fff7ed" />
            <stop offset="0.42" stopColor="#ffffff" />
            <stop offset="1" stopColor="#fffaf5" />
          </radialGradient>
          <linearGradient id="focus-chain-edge" x1="0" x2="1" y1="0" y2="0">
            <stop offset="0" stopColor="#facc15" />
            <stop offset="0.52" stopColor="#f97316" />
            <stop offset="1" stopColor="#dc2626" />
          </linearGradient>
          <filter id="focus-chain-shadow" x="-30%" y="-30%" width="160%" height="170%">
            <feDropShadow dx="0" dy="14" stdDeviation="14" floodColor="#7c2d12" floodOpacity="0.11" />
          </filter>
          <filter id="focus-chain-glow" x="-70%" y="-70%" width="240%" height="240%">
            <feGaussianBlur stdDeviation="10" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <rect width={VIEW_WIDTH} height={VIEW_HEIGHT} fill="url(#focus-chain-bg)" />
        <rect x="22" y="22" width={VIEW_WIDTH - 44} height={VIEW_HEIGHT - 44} rx="28" fill="#ffffff" fillOpacity="0.72" stroke="#f5dfcf" />

        <g opacity="0.72">
          {[132, 220, 308].map((radius) => (
            <circle key={radius} cx={CX} cy={CY} r={radius} fill="none" stroke="#f6e6d8" strokeWidth="1.2" />
          ))}
          <line x1={CX - 430} x2={CX + 430} y1={CY} y2={CY} stroke="#f7eadf" strokeDasharray="6 10" />
          <line x1={CX} x2={CX} y1={CY - 320} y2={CY + 320} stroke="#f7eadf" strokeDasharray="6 10" />
        </g>

        <g opacity="0.16">
          <path d={sectorPath(CX, CY, 88, 336, ROLE_STYLES.upstream.start, ROLE_STYLES.upstream.end)} fill={ROLE_STYLES.upstream.color} />
          <path d={sectorPath(CX, CY, 88, 336, ROLE_STYLES.downstream.start, ROLE_STYLES.downstream.end)} fill={ROLE_STYLES.downstream.color} />
          <path d={sectorPath(CX, CY, 92, 326, ROLE_STYLES.bridge.start, ROLE_STYLES.bridge.end)} fill={ROLE_STYLES.bridge.color} />
          <path d={sectorPath(CX, CY, 92, 310, ROLE_STYLES.peer.start, ROLE_STYLES.peer.end)} fill={ROLE_STYLES.peer.color} />
        </g>

        <g fill="none">
          {model.links.map((link, index) => (
            <path
              key={`${link.edge.source}-${link.edge.target}-${link.edge.relation_type ?? ""}-${index}`}
              d={linkPath(link.source, link.target)}
              stroke={link.active ? warmColor(link.intensity) : "url(#focus-chain-edge)"}
              strokeWidth={link.active ? 2.4 + link.intensity * 3.2 : 0.7 + link.intensity * 2.1}
              strokeOpacity={link.active ? 0.58 : 0.08 + link.intensity * 0.22}
              strokeLinecap="round"
            />
          ))}
        </g>

        <g>
          {model.nodes.filter((item) => item.role !== "focus").map((item) => (
            <BubbleNode key={item.node.node_key} item={item} onSelect={onSelect} />
          ))}
        </g>

        <FocusNode item={model.nodes.find((item) => item.role === "focus")} focus={model.focus} onSelect={onSelect} />
        <RoleLegend counts={model.counts} />
        <DepthBadge maxDepth={model.maxDepth} nodeCount={model.nodes.length} edgeCount={model.links.length} />
      </svg>
    </div>
  );
}

function FocusNode({ item, focus, onSelect }: { item?: RenderNode; focus: ChainNode; onSelect: (nodeKey: string) => void }) {
  const heat = nodeHeat(focus);
  const intensity = nodeIntensity(focus, Math.max(heat, 1));
  const color = warmColor(intensity);
  const x = item?.x ?? CX;
  const y = item?.y ?? CY;

  return (
    <g
      role="button"
      tabIndex={0}
      onClick={() => onSelect(focus.node_key)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(focus.node_key);
        }
      }}
      className="cursor-pointer outline-none"
    >
      <circle cx={x} cy={y} r="112" fill={color} opacity="0.14" filter="url(#focus-chain-glow)" />
      <circle cx={x} cy={y} r="72" fill="#ffffff" stroke={color} strokeWidth="2.6" filter="url(#focus-chain-shadow)" />
      <circle cx={x} cy={y} r="47" fill={color} opacity="0.16" />
      <circle cx={x} cy={y} r="17" fill={color} />
      <rect x={x - 124} y={y - 112} width="248" height="78" rx="18" fill="#ffffff" stroke="#fed7aa" filter="url(#focus-chain-shadow)" />
      <text x={x} y={y - 82} textAnchor="middle" fill="#111827" fontSize="19" fontWeight="850">
        {clipLabel(focus.name, 14)}
      </text>
      <text x={x} y={y - 58} textAnchor="middle" fill="#9a3412" fontSize="12" fontWeight="750">
        {focus.layer || focus.node_type || "产业节点"} / 热度 {heat.toFixed(1)}
      </text>
      <title>{`${focus.name}｜${focus.layer}｜热度 ${heat.toFixed(1)}`}</title>
    </g>
  );
}

function BubbleNode({ item, onSelect }: { item: RenderNode; onSelect: (nodeKey: string) => void }) {
  const roleStyle = ROLE_STYLES[item.role];
  const heatColor = warmColor(item.intensity);
  const labelWidth = Math.max(56, Math.min(132, item.node.name.length * 13 + 22));
  const labelSide = item.x >= CX ? 1 : -1;
  const labelX = item.x + labelSide * (item.r + 10);
  const labelAnchor = labelSide > 0 ? "start" : "end";
  const labelRectX = labelSide > 0 ? labelX - 8 : labelX - labelWidth + 8;

  return (
    <g
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
      <circle cx={item.x} cy={item.y} r={item.r + 12} fill={roleStyle.color} opacity={0.08 + item.intensity * 0.07} />
      <circle cx={item.x} cy={item.y} r={item.r} fill="#ffffff" stroke={roleStyle.stroke} strokeWidth={1.1 + item.intensity * 1.2} filter="url(#focus-chain-shadow)" />
      <circle cx={item.x} cy={item.y} r={Math.max(item.r - 5, 5)} fill={heatColor} opacity="0.9" />
      <circle cx={item.x - item.r * 0.28} cy={item.y - item.r * 0.28} r={Math.max(item.r * 0.18, 2.2)} fill="#ffffff" opacity="0.65" />
      {item.label ? (
        <g>
          <rect x={labelRectX} y={item.y - 14} width={labelWidth} height="28" rx="9" fill="#ffffff" fillOpacity="0.95" stroke="#f3dfd2" />
          <text x={labelX} y={item.y + 4} textAnchor={labelAnchor} fill="#111827" fontSize="12" fontWeight="750">
            {clipLabel(item.node.name, 10)}
          </text>
        </g>
      ) : null}
      <title>{`${item.node.name}｜${ROLE_STYLES[item.role].label}｜${item.node.layer}｜热度 ${item.heat.toFixed(1)}`}</title>
    </g>
  );
}

function RoleLegend({ counts }: { counts: Record<RelationRole, number> }) {
  const rows: RelationRole[] = ["upstream", "downstream", "bridge", "peer"];
  return (
    <g transform="translate(34 42)">
      <rect width="164" height="132" rx="14" fill="#ffffff" fillOpacity="0.92" stroke="#f2dfd2" />
      <text x="14" y="24" fill="#111827" fontSize="12.5" fontWeight="850">
        聚焦关系场
      </text>
      {rows.map((role, index) => (
        <g key={role} transform={`translate(14 ${44 + index * 20})`}>
          <circle r="5.5" fill={ROLE_STYLES[role].color} />
          <text x="14" y="4" fill="#475569" fontSize="11.5" fontWeight="700">
            {ROLE_STYLES[role].label}
          </text>
          <text x="132" y="4" textAnchor="end" fill="#9a3412" fontSize="11.5" fontWeight="800">
            {counts[role] ?? 0}
          </text>
        </g>
      ))}
    </g>
  );
}

function DepthBadge({ maxDepth, nodeCount, edgeCount }: { maxDepth: number; nodeCount: number; edgeCount: number }) {
  return (
    <g transform="translate(838 42)">
      <rect width="248" height="74" rx="14" fill="#ffffff" fillOpacity="0.92" stroke="#f2dfd2" />
      <text x="16" y="26" fill="#111827" fontSize="12.5" fontWeight="850">
        相关上下游全链路
      </text>
      <text x="16" y="52" fill="#64748b" fontSize="12" fontWeight="650">
        {nodeCount} 节点 / {edgeCount} 关系 / 最远 {maxDepth} 跳
      </text>
    </g>
  );
}

function buildGraph({
  detail,
  allNodes,
  allEdges,
  selectedNodeKey
}: {
  detail: ChainNodeDetail | null;
  allNodes?: ChainNode[];
  allEdges?: ChainEdge[];
  selectedNodeKey?: string | null;
}): GraphModel {
  const focusKey = selectedNodeKey ?? detail?.node?.node_key ?? null;
  const detailNodes = collectDetailNodes(detail);
  const nodesSource = allNodes?.length ? mergeNodes(allNodes, detailNodes) : detailNodes;
  const edgesSource = allEdges?.length ? allEdges : detail?.edges ?? [];
  const emptyCounts: Record<RelationRole, number> = { focus: 0, upstream: 0, downstream: 0, bridge: 0, peer: 0 };

  if (!focusKey || !nodesSource.length) {
    return { focus: null, nodes: [], links: [], counts: emptyCounts, maxDepth: 0 };
  }

  const nodeMap = new Map(nodesSource.map((node) => [node.node_key, node]));
  const focus = nodeMap.get(focusKey) ?? detail?.node ?? null;
  if (!focus) {
    return { focus: null, nodes: [], links: [], counts: emptyCounts, maxDepth: 0 };
  }
  nodeMap.set(focus.node_key, mergeNode(nodeMap.get(focus.node_key), focus));

  const sanitizedEdges = edgesSource.filter((edge) => nodeMap.has(edge.source) && nodeMap.has(edge.target));
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  const degree = new Map<string, number>();

  for (const edge of sanitizedEdges) {
    appendMap(outgoing, edge.source, edge.target);
    appendMap(incoming, edge.target, edge.source);
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }

  const upstreamDepths = traverseDepths(focus.node_key, incoming);
  const downstreamDepths = traverseDepths(focus.node_key, outgoing);
  const relatedKeys = new Set<string>([focus.node_key, ...upstreamDepths.keys(), ...downstreamDepths.keys()]);

  for (const node of detail?.same_layer ?? []) {
    relatedKeys.add(node.node_key);
  }
  if (relatedKeys.size === 1 && detail) {
    for (const node of detail.upstream) relatedKeys.add(node.node_key);
    for (const node of detail.downstream) relatedKeys.add(node.node_key);
  }

  const relatedNodes = [...relatedKeys]
    .map((key) => nodeMap.get(key))
    .filter((node): node is ChainNode => Boolean(node));
  const maxHeat = Math.max(...relatedNodes.map(nodeHeat), 1);
  const roleGroups = groupByRole(relatedNodes, focus.node_key, upstreamDepths, downstreamDepths, detail);
  const counts = { ...emptyCounts };
  const renderNodes: RenderNode[] = [];

  renderNodes.push({
    node: focus,
    role: "focus",
    depth: 0,
    x: CX,
    y: CY,
    r: 72,
    heat: nodeHeat(focus),
    intensity: nodeIntensity(focus, maxHeat),
    degree: degree.get(focus.node_key) ?? 0,
    label: true
  });
  counts.focus = 1;

  for (const role of ["upstream", "downstream", "bridge", "peer"] as RelationRole[]) {
    const group = roleGroups.get(role) ?? [];
    counts[role] = group.length;
    const sorted = group.sort((left, right) => {
      const leftDepth = placementDepth(left.node_key, focus.node_key, upstreamDepths, downstreamDepths, detail);
      const rightDepth = placementDepth(right.node_key, focus.node_key, upstreamDepths, downstreamDepths, detail);
      if (leftDepth !== rightDepth) return leftDepth - rightDepth;
      const degreeGap = (degree.get(right.node_key) ?? 0) - (degree.get(left.node_key) ?? 0);
      if (degreeGap !== 0) return degreeGap;
      return nodeHeat(right) - nodeHeat(left);
    });

    sorted.forEach((node, index) => {
      const depth = placementDepth(node.node_key, focus.node_key, upstreamDepths, downstreamDepths, detail);
      const position = orbitalPosition(role, index, sorted.length, depth);
      const heat = nodeHeat(node);
      const intensity = nodeIntensity(node, maxHeat);
      const nodeDegree = degree.get(node.node_key) ?? 0;
      renderNodes.push({
        node,
        role,
        depth,
        x: position.x,
        y: position.y,
        r: 8 + intensity * 11 + Math.min(nodeDegree, 8) * 0.85 + (depth <= 1 ? 3 : 0),
        heat,
        intensity,
        degree: nodeDegree,
        label: depth <= 2 || intensity >= 0.55 || nodeDegree >= 4
      });
    });
  }

  const renderNodeMap = new Map(renderNodes.map((node) => [node.node.node_key, node]));
  const relatedEdges = sanitizedEdges.filter((edge) => renderNodeMap.has(edge.source) && renderNodeMap.has(edge.target));
  const links = relatedEdges.flatMap<RenderLink>((edge) => {
    const source = renderNodeMap.get(edge.source);
    const target = renderNodeMap.get(edge.target);
    if (!source || !target) return [];
    const intensity = Math.min(
      Math.max(source.intensity, target.intensity, normalize(edge.intensity), normalize(edge.heat), normalize(edge.weight)),
      1
    );
    return [{
      edge,
      source,
      target,
      intensity,
      active: edge.source === focus.node_key || edge.target === focus.node_key || source.depth <= 1 || target.depth <= 1
    }];
  });

  const maxDepth = Math.max(
    0,
    ...renderNodes.map((node) => node.depth)
  );

  return { focus, nodes: renderNodes, links, counts, maxDepth };
}

function groupByRole(
  nodes: ChainNode[],
  focusKey: string,
  upstreamDepths: Map<string, number>,
  downstreamDepths: Map<string, number>,
  detail: ChainNodeDetail | null
) {
  const groups = new Map<RelationRole, ChainNode[]>();
  const sameLayerKeys = new Set((detail?.same_layer ?? []).map((node) => node.node_key));
  for (const node of nodes) {
    if (node.node_key === focusKey) continue;
    const role = relationRole(node.node_key, focusKey, upstreamDepths, downstreamDepths, sameLayerKeys);
    const rows = groups.get(role) ?? [];
    rows.push(node);
    groups.set(role, rows);
  }
  return groups;
}

function relationRole(
  nodeKey: string,
  focusKey: string,
  upstreamDepths: Map<string, number>,
  downstreamDepths: Map<string, number>,
  sameLayerKeys: Set<string>
): RelationRole {
  if (nodeKey === focusKey) return "focus";
  const isUpstream = upstreamDepths.has(nodeKey);
  const isDownstream = downstreamDepths.has(nodeKey);
  if (isUpstream && isDownstream) return "bridge";
  if (isUpstream) return "upstream";
  if (isDownstream) return "downstream";
  if (sameLayerKeys.has(nodeKey)) return "peer";
  return "peer";
}

function placementDepth(
  nodeKey: string,
  focusKey: string,
  upstreamDepths: Map<string, number>,
  downstreamDepths: Map<string, number>,
  detail: ChainNodeDetail | null
) {
  if (nodeKey === focusKey) return 0;
  const upstream = upstreamDepths.get(nodeKey);
  const downstream = downstreamDepths.get(nodeKey);
  if (upstream !== undefined && downstream !== undefined) return Math.min(upstream, downstream);
  if (upstream !== undefined) return upstream;
  if (downstream !== undefined) return downstream;
  const sameLayerIndex = (detail?.same_layer ?? []).findIndex((node) => node.node_key === nodeKey);
  return sameLayerIndex >= 0 ? 1 : 3;
}

function orbitalPosition(role: RelationRole, index: number, count: number, depth: number) {
  const style = ROLE_STYLES[role];
  const span = normalizeArc(style.end - style.start);
  const ratio = count <= 1 ? 0.5 : (index + 0.5) / count;
  const ripple = ((index % 3) - 1) * 8;
  const angle = style.start + span * ratio + (depth % 2 === 0 ? 4 : -4);
  const radius = Math.min(318, 118 + depth * 58 + Math.floor(index / Math.max(1, Math.ceil(count / 3))) * 11 + ripple);
  const point = polarToCartesian(CX, CY, radius, angle);
  return {
    x: clamp(point.x, 76, VIEW_WIDTH - 76),
    y: clamp(point.y, 104, VIEW_HEIGHT - 82)
  };
}

function collectDetailNodes(detail: ChainNodeDetail | null) {
  if (!detail?.node) return [];
  return mergeNodes([detail.node], [...detail.upstream, ...detail.downstream, ...(detail.same_layer ?? [])]);
}

function mergeNodes(primary: ChainNode[], secondary: ChainNode[]) {
  const merged = new Map<string, ChainNode>();
  for (const node of [...primary, ...secondary]) {
    merged.set(node.node_key, mergeNode(merged.get(node.node_key), node));
  }
  return Array.from(merged.values());
}

function mergeNode(base: ChainNode | undefined, incoming: ChainNode) {
  if (!base) return incoming;
  return {
    ...base,
    ...incoming,
    industry_names: incoming.industry_names?.length ? incoming.industry_names : base.industry_names,
    tags: incoming.tags?.length ? incoming.tags : base.tags,
    anchor_companies: incoming.anchor_companies?.length ? incoming.anchor_companies : base.anchor_companies,
    indicators: incoming.indicators?.length ? incoming.indicators : base.indicators
  };
}

function appendMap(map: Map<string, string[]>, key: string, value: string) {
  const rows = map.get(key) ?? [];
  rows.push(value);
  map.set(key, rows);
}

function traverseDepths(focusKey: string, graph: Map<string, string[]>) {
  const distances = new Map<string, number>();
  const queue: Array<{ key: string; depth: number }> = [{ key: focusKey, depth: 0 }];

  while (queue.length) {
    const current = queue.shift();
    if (!current) continue;
    for (const neighbor of graph.get(current.key) ?? []) {
      const nextDepth = current.depth + 1;
      const existing = distances.get(neighbor);
      if (existing !== undefined && existing <= nextDepth) continue;
      distances.set(neighbor, nextDepth);
      queue.push({ key: neighbor, depth: nextDepth });
    }
  }

  distances.delete(focusKey);
  return distances;
}

function linkPath(source: RenderNode, target: RenderNode) {
  const sx = source.x;
  const sy = source.y;
  const tx = target.x;
  const ty = target.y;
  if (source.role === "focus" || target.role === "focus") {
    const dx = tx - sx;
    const dy = ty - sy;
    const bend = 0.16;
    const cx = (sx + tx) / 2 - dy * bend;
    const cy = (sy + ty) / 2 + dx * bend;
    return `M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`;
  }
  const c1x = sx + (CX - sx) * 0.34;
  const c1y = sy + (CY - sy) * 0.34;
  const c2x = tx + (CX - tx) * 0.34;
  const c2y = ty + (CY - ty) * 0.34;
  return `M ${sx} ${sy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${tx} ${ty}`;
}

function sectorPath(cx: number, cy: number, inner: number, outer: number, startAngle: number, endAngle: number) {
  const startOuter = polarToCartesian(cx, cy, outer, startAngle);
  const endOuter = polarToCartesian(cx, cy, outer, endAngle);
  const startInner = polarToCartesian(cx, cy, inner, endAngle);
  const endInner = polarToCartesian(cx, cy, inner, startAngle);
  const largeArc = Math.abs(normalizeArc(endAngle - startAngle)) > 180 ? 1 : 0;
  return [
    `M ${startOuter.x} ${startOuter.y}`,
    `A ${outer} ${outer} 0 ${largeArc} 1 ${endOuter.x} ${endOuter.y}`,
    `L ${startInner.x} ${startInner.y}`,
    `A ${inner} ${inner} 0 ${largeArc} 0 ${endInner.x} ${endInner.y}`,
    "Z"
  ].join(" ");
}

function polarToCartesian(cx: number, cy: number, radius: number, angle: number) {
  const radians = (angle * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(radians),
    y: cy + radius * Math.sin(radians)
  };
}

function normalizeArc(value: number) {
  return value < 0 ? value + 360 : value;
}

function nodeHeat(node: ChainNode) {
  return Math.max(node.heat ?? 0, node.momentum ?? 0, (node.intensity ?? 0) * 100);
}

function nodeIntensity(node: ChainNode, maxHeat: number) {
  const direct = normalize(node.intensity);
  if (direct > 0) return Math.min(Math.max(direct, 0), 1);
  return Math.min(Math.max(nodeHeat(node) / Math.max(maxHeat, 1), 0), 1);
}

function normalize(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return value > 1 ? value / 100 : value;
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

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
