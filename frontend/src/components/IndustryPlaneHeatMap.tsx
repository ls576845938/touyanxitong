"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { ArrowRight, Flame, Network, LayoutGrid, Info } from "lucide-react";
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
  maxHeat: number;
};

const PADDING_X = 60;
const PADDING_TOP = 100;
const PADDING_BOTTOM = 60;
const LAYER_GAP = 32;
const LAYER_WIDTH = 260;
const CARD_WIDTH = 220;
const CARD_HEIGHT = 72;
const CARD_GAP = 14;

export function IndustryPlaneHeatMap({ nodes, edges, selectedNodeKey, activeLayer, query, onSelect }: IndustryPlaneHeatMapProps) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const model = useMemo(
    () => buildPlaneModel(nodes, edges, selectedNodeKey, activeLayer, query),
    [activeLayer, edges, nodes, query, selectedNodeKey]
  );

  return (
    <div className="relative group bg-white overflow-hidden rounded-3xl border border-slate-200 shadow-2xl transition-all hover:border-slate-300">
      {/* Header Info */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-slate-50/50 backdrop-blur-md px-8 py-5">
        <div className="flex items-center gap-4">
          <div className="h-10 w-10 flex items-center justify-center rounded-xl bg-slate-900 text-white shadow-lg">
            <LayoutGrid size={20} />
          </div>
          <div>
            <h3 className="text-sm font-black uppercase tracking-widest text-slate-900">平面产业频谱总图</h3>
            <p className="text-[10px] font-bold text-slate-400 mt-0.5 uppercase tracking-tighter italic">Macro-Industrial Heat Matrix</p>
          </div>
        </div>
        <div className="flex gap-4">
          <MetricPill label="可见节点" value={model.nodes.length} color="#6366f1" />
          <MetricPill label="关联密度" value={model.edges.length} color="#10b981" />
        </div>
      </div>

      <div className="overflow-x-auto no-scrollbar bg-white">
        <svg viewBox={`0 0 ${model.width} ${model.height}`} className="block min-w-full" style={{ height: Math.min(model.height, 900) }}>
          <defs>
            <filter id="spectrum-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feOffset dx="0" dy="2" result="offsetBlur" />
              <feComposite in="SourceGraphic" in2="offsetBlur" operator="over" />
            </filter>
          </defs>

          {/* Layer Backgrounds */}
          {model.layers.map((layer) => (
            <g key={layer.key} transform={`translate(${layer.x} 0)`}>
              <rect x={0} y={40} width={layer.width} height={model.height - 80} rx={24} fill="#f8fafc" opacity={layer.active ? 1 : 0.4} />
              <text x={layer.width / 2} y={75} textAnchor="middle" fill="#94a3b8" fontSize="10" fontWeight="900" className="uppercase tracking-[0.2em]">{layer.label}</text>
            </g>
          ))}

          {/* Connections */}
          <g>
            {model.edges.map((item, idx) => {
              const sourceX = item.source.x + item.source.width;
              const sourceY = item.source.y + item.source.height / 2;
              const targetX = item.target.x;
              const targetY = item.target.y + item.target.height / 2;
              const isActive = item.active || hoveredNode === item.source.node.node_key || hoveredNode === item.target.node.node_key;
              return (
                <motion.path
                  key={idx}
                  d={`M ${sourceX} ${sourceY} C ${sourceX + 40} ${sourceY}, ${targetX - 40} ${targetY}, ${targetX} ${targetY}`}
                  fill="none"
                  stroke={isActive ? "#f97316" : "#e2e8f0"}
                  strokeWidth={isActive ? 2 : 0.8}
                  strokeOpacity={isActive ? 0.8 : 0.3}
                  initial={{ pathLength: 0 }}
                  animate={{ pathLength: 1 }}
                />
              );
            })}
          </g>

          {/* Nodes */}
          {model.nodes.map((item) => {
            const hColor = heatColor(item.intensity);
            const isTarget = item.node.node_key === selectedNodeKey;
            const isHovered = item.node.node_key === hoveredNode;
            
            return (
              <motion.g
                key={item.node.node_key}
                transform={`translate(${item.x} ${item.y})`}
                onClick={() => onSelect(item.node.node_key)}
                onMouseEnter={() => setHoveredNode(item.node.node_key)}
                onMouseLeave={() => setHoveredNode(null)}
                className="cursor-pointer"
                whileHover={{ y: -2 }}
              >
                {/* Node Card */}
                <rect
                  width={item.width}
                  height={item.height}
                  rx={16}
                  fill="white"
                  stroke={isTarget ? "#0f172a" : isHovered ? "#cbd5e1" : "#f1f5f9"}
                  strokeWidth={isTarget ? 2.5 : 1}
                  className="shadow-sm transition-colors duration-300"
                />
                
                {/* Heat Stripe */}
                <rect width={6} height={item.height} rx={3} fill={hColor} />
                
                {/* Labels */}
                <text x={18} y={24} fill="#1e293b" fontSize="11" fontWeight="800" className="uppercase tracking-tight">
                  {clipLabel(item.node.name, 12)}
                </text>
                <text x={18} y={42} fill="#94a3b8" fontSize="9" fontWeight="700" className="uppercase tracking-tighter italic">
                  {item.node.node_type || "Entity"}
                </text>
                
                {/* Heat Value */}
                <text x={item.width - 12} y={24} textAnchor="end" fill={hColor} fontSize="10" fontWeight="900" className="tabular-nums">
                  {item.heat.toFixed(1)}
                </text>

                {/* Progress Bar */}
                <rect x={18} y={52} width={item.width - 36} height={4} rx={2} fill="#f1f5f9" />
                <motion.rect 
                  x={18} y={52} 
                  width={(item.width - 36) * item.intensity} 
                  height={4} rx={2} 
                  fill={hColor}
                  initial={{ width: 0 }}
                  animate={{ width: (item.width - 36) * item.intensity }}
                />
              </motion.g>
            );
          })}
        </svg>
      </div>

      {/* Footer Legend */}
      <div className="absolute bottom-8 right-8 bg-slate-900/95 backdrop-blur-xl text-white px-6 py-4 rounded-2xl shadow-2xl flex items-center gap-6">
        <div className="flex items-center gap-3">
          <Info size={14} className="text-slate-500" />
          <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Heat Level</span>
        </div>
        <div className="flex gap-4">
          <LegendItem label="爆红" color="#ef4444" />
          <LegendItem label="活跃" color="#f97316" />
          <LegendItem label="温和" color="#eab308" />
        </div>
      </div>
    </div>
  );
}

function MetricPill({ label, value, color }: { label: string, value: number|string, color: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-white rounded-xl border border-slate-100 shadow-sm">
      <span className="text-[9px] font-black text-slate-400 uppercase tracking-widest">{label}</span>
      <span className="text-xs font-black" style={{ color }}>{value}</span>
    </div>
  );
}

function LegendItem({ label, color }: { label: string, color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-[10px] font-bold text-slate-300">{label}</span>
    </div>
  );
}

// Logic implementations

function buildPlaneModel(nodes: ChainNode[], edges: ChainEdge[], selectedNodeKey: string | null, activeLayer: string, query: string): PlaneModel {
  const lowered = query.trim().toLowerCase();
  const maxHeat = Math.max(...nodes.map(n => nodeHeat(n)), 1);
  const layers = Array.from(new Set(nodes.map(n => n.layer || "未分类")));
  
  const layerBands: LayerBand[] = layers.map((l, idx) => {
    const lNodes = nodes.filter(n => n.layer === l);
    const visibleNodes = lNodes.filter(n => !lowered || n.name.toLowerCase().includes(lowered));
    return {
      key: normalizeLayerKey(l),
      label: l,
      x: PADDING_X + idx * (LAYER_WIDTH + LAYER_GAP),
      width: LAYER_WIDTH,
      count: lNodes.length,
      visibleCount: visibleNodes.length,
      active: activeLayer === "all" || normalizeLayerKey(l) === activeLayer
    };
  });

  const renderNodes: RenderNode[] = [];
  layerBands.forEach((band, lIdx) => {
    const lNodes = nodes.filter(n => n.layer === band.label)
      .filter(n => !lowered || n.name.toLowerCase().includes(lowered) || n.node_key === selectedNodeKey)
      .sort((a,b) => nodeHeat(b) - nodeHeat(a));
    
    lNodes.forEach((n, order) => {
      renderNodes.push({
        node: n, layer: band.label, layerIndex: lIdx, order,
        x: band.x + 20, y: PADDING_TOP + order * (CARD_HEIGHT + CARD_GAP),
        width: CARD_WIDTH, height: CARD_HEIGHT,
        heat: nodeHeat(n), intensity: nodeHeat(n) / maxHeat,
        visible: true, matched: true, connected: false, degree: 0
      });
    });
  });

  const nodeMap = new Map(renderNodes.map(rn => [rn.node.node_key, rn]));
  const renderEdges = edges.filter(e => nodeMap.has(e.source) && nodeMap.has(e.target)).map(e => ({
    edge: e, source: nodeMap.get(e.source)!, target: nodeMap.get(e.target)!,
    intensity: Math.max(normalize(e.intensity), normalize((e.heat ?? 0)/100)),
    active: e.source === selectedNodeKey || e.target === selectedNodeKey
  }));

  const height = Math.max(800, PADDING_TOP + Math.max(...layerBands.map(b => b.visibleCount)) * (CARD_HEIGHT + CARD_GAP) + PADDING_BOTTOM);
  const width = PADDING_X * 2 + layers.length * (LAYER_WIDTH + LAYER_GAP);

  return { width, height, layers: layerBands, nodes: renderNodes, edges: renderEdges, selectedName: "", maxHeat };
}

function normalizeLayerKey(v: string) { return v.trim().toLowerCase().replace(/\s+/g, "_"); }
function nodeHeat(n: ChainNode) { return Math.max(n.heat ?? 0, n.momentum ?? 0, (n.intensity ?? 0) * 100); }
function normalize(v: number | null | undefined) { return (typeof v === 'number' && !isNaN(v)) ? (v > 1 ? v/100 : v) : 0; }
function heatColor(i: number) {
  if (i >= 0.8) return "#ef4444";
  if (i >= 0.45) return "#f97316";
  return "#eab308";
}
function clipLabel(v: string, m: number) { return v.length > m ? `${v.slice(0, m)}..` : v; }
