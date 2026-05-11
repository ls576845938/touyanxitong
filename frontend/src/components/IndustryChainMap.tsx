"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Info, Zap, ChevronRight } from "lucide-react";
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
const CX = VIEW_WIDTH / 2;
const CY = VIEW_HEIGHT / 2;

const ROLE_CONFIG: Record<RelationRole, { label: string; color: string; start: number; end: number }> = {
  focus: { label: "当前焦点", color: "#0f172a", start: 0, end: 360 },
  upstream: { label: "上游输入", color: "#3b82f6", start: 135, end: 225 },
  downstream: { label: "下游扩散", color: "#10b981", start: -45, end: 45 },
  bridge: { label: "桥接通路", color: "#8b5cf6", start: 225, end: 315 },
  peer: { label: "同级互联", color: "#f59e0b", start: 45, end: 135 }
};

export function IndustryChainMap({ detail, onSelect, allNodes, allEdges, selectedNodeKey }: IndustryChainMapProps) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const model = useMemo(
    () => buildGraph({ detail, allNodes, allEdges, selectedNodeKey }),
    [allEdges, allNodes, detail, selectedNodeKey]
  );

  if (!model.focus) {
    return (
      <div className="flex h-[720px] items-center justify-center bg-slate-50 rounded-3xl border border-dashed border-slate-200">
        <div className="text-center">
          <div className="p-4 rounded-full bg-white shadow-sm inline-block mb-4 text-slate-300"><Info size={32} /></div>
          <p className="text-slate-400 font-bold uppercase tracking-widest text-xs">Waiting for Node Selection</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-[720px] w-full overflow-hidden bg-white select-none">
      <div className="absolute inset-0 pointer-events-none opacity-40" 
           style={{ backgroundImage: 'radial-gradient(#e2e8f0 1px, transparent 1px)', backgroundSize: '32px 32px' }} />
      
      <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} className="h-full w-full">
        <defs>
          <filter id="node-glow-chain" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Orbital Backgrounds */}
        <g opacity="0.04">
          {Object.entries(ROLE_CONFIG).map(([role, cfg]) => role !== 'focus' && (
            <path key={role} d={sectorPath(CX, CY, 100, 480, cfg.start, cfg.end)} fill={cfg.color} />
          ))}
        </g>

        {/* Connections */}
        <g>
          {model.links.map((link, idx) => {
            const isRelated = hoveredNode === link.source.node.node_key || hoveredNode === link.target.node.node_key;
            return (
              <motion.path
                key={`${link.edge.source}-${link.edge.target}-${idx}`}
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: isRelated ? 0.9 : link.active ? 0.4 : 0.1 }}
                d={linkPath(link.source, link.target)}
                fill="none"
                stroke={isRelated ? "#f97316" : "#cbd5e1"}
                strokeWidth={isRelated ? 3 : 1.5}
                transition={{ duration: 0.8, delay: idx * 0.002 }}
              />
            );
          })}
        </g>

        {/* Animated Heat Particles */}
        <g>
          {model.links.filter(l => l.active || hoveredNode === l.source.node.node_key).slice(0, 30).map((link, idx) => (
            <motion.circle key={`chain-p-${idx}`} r={2} fill={heatColor(link.intensity)} opacity={0.6}>
              <animateMotion dur={`${1.5 + Math.random() * 2}s`} repeatCount="indefinite" path={linkPath(link.source, link.target)} />
            </motion.circle>
          ))}
        </g>

        {/* Nodes */}
        <g>
          {model.nodes.map((item) => (
            <MapNode 
              key={item.node.node_key} 
              item={item} 
              onSelect={onSelect} 
              onHover={setHoveredNode}
              isHovered={hoveredNode === item.node.node_key}
            />
          ))}
        </g>
      </svg>

      {/* Overlays */}
      <div className="absolute top-8 left-8 flex flex-col gap-4 pointer-events-none">
        <div className="bg-white/90 backdrop-blur-xl border border-slate-200 p-5 rounded-2xl shadow-xl pointer-events-auto">
          <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
            <Zap size={12} className="text-indigo-600" />
            Relation Topology
          </div>
          <div className="space-y-2.5">
            {Object.entries(ROLE_CONFIG).map(([role, cfg]) => role !== 'focus' && (
              <div key={role} className="flex items-center justify-between gap-10">
                <div className="flex items-center gap-3">
                  <div className="h-2 w-2 rounded-full shadow-sm" style={{ backgroundColor: cfg.color }} />
                  <span className="text-[11px] font-black text-slate-700">{cfg.label}</span>
                </div>
                <span className="text-[10px] font-black text-slate-900 tabular-nums px-2 py-0.5 rounded-md bg-slate-50 border border-slate-100">{model.counts[role as RelationRole]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="absolute bottom-8 right-8 flex items-center gap-3">
        <div className="bg-slate-900 text-white px-6 py-3 rounded-2xl shadow-2xl flex items-center gap-6">
          <div className="flex flex-col">
            <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Max Depth</span>
            <span className="text-sm font-black italic">{model.maxDepth} Hops</span>
          </div>
          <div className="h-6 w-[1px] bg-white/20" />
          <div className="flex flex-col">
            <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">Visibility</span>
            <span className="text-sm font-black">{model.nodes.length} Nodes</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function MapNode({ item, onSelect, onHover, isHovered }: { item: RenderNode, onSelect: (k: string) => void, onHover: (k: string|null) => void, isHovered: boolean }) {
  const isFocus = item.role === "focus";
  const hColor = heatColor(item.intensity);
  
  return (
    <motion.g
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 25, delay: item.depth * 0.05 }}
      onMouseEnter={() => onHover(item.node.node_key)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onSelect(item.node.node_key)}
      className="cursor-pointer"
    >
      {/* Node Aura */}
      <motion.circle
        cx={item.x}
        cy={item.y}
        r={item.r * (isFocus ? 1.8 : 2.5)}
        fill={isFocus ? "#6366f1" : hColor}
        initial={{ opacity: 0 }}
        animate={{ opacity: isHovered ? 0.35 : 0.1 }}
      />

      {/* Core Node Card - Circle */}
      <circle
        cx={item.x}
        cy={item.y}
        r={item.r}
        fill={isFocus ? "#0f172a" : "white"}
        stroke={isFocus ? "#4338ca" : isHovered ? "#f97316" : hColor}
        strokeWidth={isHovered || isFocus ? 3 : 2}
        className="transition-all duration-300 shadow-lg"
      />

      {/* Heat Pulse Core */}
      {(item.intensity > 0.4 || isFocus) && (
        <motion.circle
          cx={item.x}
          cy={item.y}
          r={item.r * 0.35}
          fill={isFocus ? "#818cf8" : hColor}
          animate={{ scale: [1, 1.4, 1], opacity: [0.4, 0.8, 0.4] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
        />
      )}

      {/* Permanent Labels for High Clarity */}
      <motion.g
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transform={`translate(${item.x} ${item.y + item.r + 14})`}
      >
        {/* Label Background for Legibility */}
        <rect
          x={-Math.max(48, item.node.name.length * 7)}
          y={-12}
          width={Math.max(96, item.node.name.length * 14)}
          height={24}
          rx={12}
          fill={isFocus ? "#0f172a" : isHovered ? "white" : "rgba(255,255,255,0.9)"}
          stroke={isFocus ? "#0f172a" : isHovered ? "#f97316" : "#e2e8f0"}
          strokeWidth={isHovered ? 1.5 : 1}
          className="shadow-md transition-colors"
        />
        <text
          textAnchor="middle"
          fill={isFocus ? "white" : isHovered ? "#f97316" : "#0f172a"}
          fontSize={isFocus ? "11.5" : "11"}
          fontWeight="900"
          className="pointer-events-none tracking-tight"
        >
          {clipLabel(item.node.name, 14)}
        </text>
        
        {/* Sub-label for Heat */}
        <text
          y={22}
          textAnchor="middle"
          fill={hColor}
          fontSize="9"
          fontWeight="900"
          className="pointer-events-none tabular-nums"
        >
          {item.heat.toFixed(1)}
        </text>
      </motion.g>
    </motion.g>
  );
}

// Logic implementations

function sectorPath(cx: number, cy: number, inner: number, outer: number, startAngle: number, endAngle: number) {
  const startOuter = polarToCartesian(cx, cy, outer, startAngle);
  const endOuter = polarToCartesian(cx, cy, outer, endAngle);
  const startInner = polarToCartesian(cx, cy, inner, endAngle);
  const endInner = polarToCartesian(cx, cy, inner, startAngle);
  const largeArc = Math.abs(endAngle - startAngle) > 180 ? 1 : 0;
  return [`M ${startOuter.x} ${startOuter.y}`, `A ${outer} ${outer} 0 ${largeArc} 1 ${endOuter.x} ${endOuter.y}`, `L ${startInner.x} ${startInner.y}`, `A ${inner} ${inner} 0 ${largeArc} 0 ${endInner.x} ${endInner.y}`, "Z"].join(" ");
}

function polarToCartesian(cx: number, cy: number, radius: number, angle: number) {
  const rad = (angle * Math.PI) / 180;
  return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
}

function linkPath(source: RenderNode, target: RenderNode) {
  const sx = source.x; const sy = source.y;
  const tx = target.x; const ty = target.y;
  const dx = tx - sx; const dy = ty - sy;
  const dr = Math.sqrt(dx * dx + dy * dy);
  return `M${sx},${sy}A${dr},${dr} 0 0,1 ${tx},${ty}`;
}

function heatColor(i: number) {
  if (i >= 0.8) return "#ef4444";
  if (i >= 0.45) return "#f97316";
  return "#eab308";
}

function clipLabel(val: string, max: number) {
  return val.length > max ? `${val.slice(0, max)}..` : val;
}

function buildGraph({ detail, allNodes, allEdges, selectedNodeKey }: { detail: ChainNodeDetail | null; allNodes?: ChainNode[]; allEdges?: ChainEdge[]; selectedNodeKey?: string | null }): GraphModel {
  const focusKey = selectedNodeKey ?? detail?.node?.node_key ?? null;
  const detailNodes = detail?.node ? [detail.node, ...detail.upstream, ...detail.downstream, ...(detail.same_layer ?? [])] : [];
  const nodesSource = allNodes?.length ? allNodes : detailNodes;
  const edgesSource = allEdges?.length ? allEdges : detail?.edges ?? [];
  const emptyCounts: Record<RelationRole, number> = { focus: 0, upstream: 0, downstream: 0, bridge: 0, peer: 0 };

  if (!focusKey || !nodesSource.length) return { focus: null, nodes: [], links: [], counts: emptyCounts, maxDepth: 0 };

  const nodeMap = new Map(nodesSource.map(n => [n.node_key, n]));
  const focus = nodeMap.get(focusKey) ?? detail?.node ?? null;
  if (!focus) return { focus: null, nodes: [], links: [], counts: emptyCounts, maxDepth: 0 };

  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  const degree = new Map<string, number>();

  edgesSource.forEach(e => {
    if (nodeMap.has(e.source) && nodeMap.has(e.target)) {
      const o = outgoing.get(e.source) ?? []; o.push(e.target); outgoing.set(e.source, o);
      const i = incoming.get(e.target) ?? []; i.push(e.source); incoming.set(e.target, i);
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
  });

  const upDepths = traverseDepths(focus.node_key, incoming);
  const downDepths = traverseDepths(focus.node_key, outgoing);
  const relatedKeys = new Set([focus.node_key, ...upDepths.keys(), ...downDepths.keys()]);
  (detail?.same_layer ?? []).forEach(n => relatedKeys.add(n.node_key));

  const relatedNodes = [...relatedKeys].map(k => nodeMap.get(k)!).filter(Boolean);
  const maxHeat = Math.max(...relatedNodes.map(n => Math.max(n.heat??0, (n.intensity??0)*100)), 1);
  
  const counts = { ...emptyCounts };
  const renderNodes: RenderNode[] = [];
  
  renderNodes.push({
    node: focus, role: "focus", depth: 0, x: CX, y: CY, r: 34,
    heat: nodeHeat(focus), intensity: nodeIntensity(focus, maxHeat),
    degree: degree.get(focus.node_key) ?? 0, label: true
  });
  counts.focus = 1;

  const roles: RelationRole[] = ["upstream", "downstream", "bridge", "peer"];
  roles.forEach(role => {
    const group = relatedNodes.filter(n => n.node_key !== focus.node_key && relationRole(n.node_key, focus.node_key, upDepths, downDepths) === role);
    counts[role] = group.length;
    group.sort((a,b) => nodeHeat(b) - nodeHeat(a)).forEach((node, idx) => {
      const depth = upDepths.get(node.node_key) ?? downDepths.get(node.node_key) ?? 1;
      const pos = orbitalPos(role, idx, group.length, depth);
      renderNodes.push({
        node, role, depth, x: pos.x, y: pos.y,
        r: 10 + nodeIntensity(node, maxHeat) * 12 + Math.min(degree.get(node.node_key)??0, 10) * 0.6,
        heat: nodeHeat(node), intensity: nodeIntensity(node, maxHeat),
        degree: degree.get(node.node_key) ?? 0, label: true
      });
    });
  });

  const rNodeMap = new Map(renderNodes.map(n => [n.node.node_key, n]));
  const links = edgesSource.filter(e => rNodeMap.has(e.source) && rNodeMap.has(e.target)).map(e => ({
    edge: e, source: rNodeMap.get(e.source)!, target: rNodeMap.get(e.target)!,
    intensity: Math.max(normalize(e.intensity), normalize((e.heat ?? 0)/100)),
    active: e.source === focus.node_key || e.target === focus.node_key
  }));

  return { focus, nodes: renderNodes, links, counts, maxDepth: Math.max(0, ...renderNodes.map(n => n.depth)) };
}

function orbitalPos(role: RelationRole, idx: number, total: number, depth: number) {
  const cfg = ROLE_CONFIG[role];
  const angleSpan = cfg.end - cfg.start;
  const angle = cfg.start + (total <= 1 ? angleSpan/2 : (idx / (total-1)) * angleSpan);
  const radius = 160 + depth * 80 + (idx % 2 === 0 ? 25 : -15);
  const p = polarToCartesian(CX, CY, radius, angle);
  return {
    x: Math.max(80, Math.min(VIEW_WIDTH - 80, p.x)),
    y: Math.max(100, Math.min(VIEW_HEIGHT - 100, p.y))
  };
}

function traverseDepths(start: string, adj: Map<string, string[]>) {
  const d = new Map<string, number>(); const q = [{ k: start, v: 0 }];
  while(q.length) {
    const {k,v} = q.shift()!;
    (adj.get(k)??[]).forEach(n => {
      if(!d.has(n) || d.get(n)! > v+1) { d.set(n, v+1); q.push({k:n, v:v+1}); }
    });
  }
  return d;
}

function relationRole(k: string, f: string, u: Map<string, number>, d: Map<string, number>): RelationRole {
  if (u.has(k) && d.has(k)) return "bridge";
  if (u.has(k)) return "upstream";
  if (d.has(k)) return "downstream";
  return "peer";
}

function nodeHeat(n: ChainNode) { return Math.max(n.heat ?? 0, n.momentum ?? 0, (n.intensity ?? 0) * 100); }
function nodeIntensity(n: ChainNode, max: number) { return Math.min(Math.max(normalize(n.intensity) || (nodeHeat(n) / Math.max(max, 1)), 0), 1); }
function normalize(v: number | null | undefined) { return (typeof v === 'number' && !isNaN(v)) ? (v > 1 ? v/100 : v) : 0; }
