"use client";

import { useMemo, useRef, useState, useEffect } from "react";
import { ArrowUpRight, RotateCcw, Sparkles, Activity, Shield, Zap, Globe } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { ChainEdge, ChainNode } from "@/lib/api";

type IndustryUniverseOverviewProps = {
  nodes: ChainNode[];
  edges: ChainEdge[];
  selectedNodeKey: string | null;
  onOpenChain: (nodeKey: string) => void;
};

type ClusterRule = {
  key: string;
  name: string;
  shortName: string;
  color: string;
  glow: string;
  nodeKeys?: string[];
  keywords: string[];
  priority: number;
};

type Vec3 = { x: number; y: number; z: number };
type Rotation = { x: number; y: number };

type UniverseCluster = {
  key: string;
  name: string;
  shortName: string;
  color: string;
  glow: string;
  nodes: ChainNode[];
  heat: number;
  intensity: number;
  hottestNode: ChainNode | null;
  stockCount: number;
  base: Vec3;
  r: number;
  selected: boolean;
  rank: number;
};

type ProjectedCluster = UniverseCluster & {
  sx: number;
  sy: number;
  depth: number;
  scale: number;
  opacity: number;
};

type ProjectedRelation = {
  key: string;
  source: ProjectedCluster;
  target: ProjectedCluster;
  weight: number;
};

const WIDTH = 1180;
const HEIGHT = 660;
const CENTER_X = 560;
const CENTER_Y = 330;
const SPHERE_RADIUS = 230;
const MAX_VISIBLE_CLUSTERS = 15;

const CLUSTER_RULES: ClusterRule[] = [
  { key: "power", name: "电力能源", shortName: "电力能源", color: "#0ea5e9", glow: "rgba(14, 165, 233, 0.4)", priority: 100, keywords: ["电力", "光伏", "储能"] },
  { key: "ai", name: "AI 算力", shortName: "AI算力", color: "#f97316", glow: "rgba(249, 115, 22, 0.4)", priority: 90, keywords: ["服务器", "算力", "GPU"] },
  { key: "semi", name: "半导体", shortName: "半导体", color: "#ef4444", glow: "rgba(239, 68, 68, 0.4)", priority: 80, keywords: ["芯片", "集成电路"] },
  { key: "auto", name: "新能源车", shortName: "新能源车", color: "#10b981", glow: "rgba(16, 185, 129, 0.4)", priority: 70, keywords: ["汽车", "锂电"] }
];

const FALLBACK_COLORS = ["#6366f1", "#8b5cf6", "#d946ef", "#ec4899", "#f43f5e", "#f97316", "#eab308", "#22c55e", "#06b6d4"];

export function IndustryUniverseOverview({ nodes, edges, selectedNodeKey, onOpenChain }: IndustryUniverseOverviewProps) {
  const [rotation, setRotation] = useState<Rotation>({ x: -0.3, y: -0.6 });
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const pointerRef = useRef<{ pointerId: number; startX: number; startY: number; origin: Rotation } | null>(null);
  const suppressClickRef = useRef(false);

  const model = useMemo(() => buildUniverse(nodes, edges, selectedNodeKey), [edges, nodes, selectedNodeKey]);
  const projection = useMemo(() => projectUniverse(model, rotation), [model, rotation]);
  const hovered = hoveredKey ? projection.clusters.find((c: ProjectedCluster) => c.key === hoveredKey) : null;
  const featured = hovered ?? projection.clusters.find((c: ProjectedCluster) => c.selected) ?? projection.clusters[0] ?? null;

  return (
    <section className="group relative overflow-hidden rounded-[40px] border border-slate-200 bg-white shadow-2xl">
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-white/80 backdrop-blur-xl px-10 py-7">
        <div className="flex items-center gap-6">
          <div className="flex h-16 w-16 items-center justify-center rounded-[24px] bg-slate-900 text-white shadow-2xl">
            <Globe className="animate-spin-slow" size={32} />
          </div>
          <div>
            <h2 className="text-2xl font-black tracking-tight text-slate-900">产业宇宙总览</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">Global Real-time Industry Mesh</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <DataTag label="产业簇" value={model.clusters.length} />
          <DataTag label="全域节点" value={model.coveredNodeCount} />
          <div className="h-8 w-[1px] bg-slate-200 mx-2" />
          <button onClick={() => setRotation({ x: -0.3, y: -0.6 })} className="px-6 h-12 rounded-2xl bg-slate-50 border border-slate-200 text-xs font-black text-slate-600 hover:bg-slate-900 hover:text-white transition-all shadow-sm active:scale-95">复位视角</button>
        </div>
      </div>

      <div className="relative grid gap-8 p-10 xl:grid-cols-[1fr_380px]">
        <div className="relative h-[720px] w-full rounded-[40px] bg-slate-50/50 border border-slate-100 shadow-inner overflow-hidden">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="h-full w-full select-none"
            onPointerDown={(e) => {
              if (e.pointerType === "mouse" && e.button !== 0) return;
              pointerRef.current = { pointerId: e.pointerId, startX: e.clientX, startY: e.clientY, origin: rotation };
              setDragging(true);
              e.currentTarget.setPointerCapture(e.pointerId);
            }}
            onPointerMove={(e) => {
              const p = pointerRef.current;
              if (!p || p.pointerId !== e.pointerId) return;
              const dx = e.clientX - p.startX; const dy = e.clientY - p.startY;
              if (Math.abs(dx) + Math.abs(dy) > 4) suppressClickRef.current = true;
              setRotation({ x: clamp(p.origin.x + dy * 0.006, -1.2, 1.2), y: p.origin.y + dx * 0.008 });
            }}
            onPointerUp={(e) => { pointerRef.current = null; setDragging(false); }}
            style={{ cursor: dragging ? "grabbing" : "grab", touchAction: "none" }}
          >
            <defs>
              <radialGradient id="grad-sphere" cx="40%" cy="30%" r="70%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="100%" stopColor="#f1f5f9" />
              </radialGradient>
              <filter id="glow-cluster" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="10" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Main Sphere */}
            <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS} fill="url(#grad-sphere)" stroke="#e2e8f0" strokeWidth="1" />
            
            {/* Relations */}
            <g>
              {projection.relations.map((rel: ProjectedRelation) => {
                const active = rel.source.key === hoveredKey || rel.target.key === hoveredKey || rel.source.selected || rel.target.selected;
                return (
                  <motion.path
                    key={rel.key}
                    d={projectedRelationPath(rel.source, rel.target)}
                    animate={{ opacity: active ? 0.9 : 0.1, stroke: active ? "#f97316" : "#cbd5e1", strokeWidth: active ? 2.5 : 1 }}
                    fill="none"
                  />
                );
              })}
            </g>

            {/* Clusters */}
            {projection.clusters.map((c: ProjectedCluster) => {
              const active = c.selected || c.key === hoveredKey;
              const hColor = heatColor(c.intensity);
              const labelAlways = c.rank < 10 || active;

              return (
                <motion.g
                  key={c.key}
                  animate={{ transform: `translate(${c.sx}px, ${c.sy}px) scale(${active ? c.scale * 1.2 : c.scale})`, opacity: c.opacity }}
                  className="cursor-pointer"
                  onMouseEnter={() => setHoveredKey(c.key)}
                  onMouseLeave={() => setHoveredKey(null)}
                  onClick={() => !suppressClickRef.current && c.hottestNode && onOpenChain(c.hottestNode.node_key)}
                >
                  <circle r={c.r * 1.5} fill={hColor} opacity={active ? 0.3 : 0.1} filter="url(#glow-cluster)" />
                  <circle r={c.r} fill="white" stroke={active ? "#0f172a" : hColor} strokeWidth={active ? 3 : 2} className="shadow-lg" />
                  <circle r={c.r * 0.4} fill={hColor} />
                  
                  {labelAlways && (
                    <g transform={`translate(0, ${c.r + 22})`}>
                       <rect x={-Math.max(50, c.shortName.length * 8)} y={-14} width={Math.max(100, c.shortName.length * 16)} height={28} rx={14} fill="white" stroke={active ? hColor : "#f1f5f9"} strokeWidth={active ? 2 : 1} className="shadow-xl" />
                       <text textAnchor="middle" y={5} fill="#0f172a" fontSize="13" fontWeight="900" className="pointer-events-none">{c.shortName}</text>
                    </g>
                  )}
                </motion.g>
              );
            })}
          </svg>
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 px-8 py-4 bg-white/90 backdrop-blur-xl border border-slate-200 rounded-full shadow-2xl text-[10px] font-black text-slate-500 uppercase tracking-widest">
            Interactive Global Infrastructure Radar Active
          </div>
        </div>

        <aside className="space-y-8 h-[720px] overflow-y-auto no-scrollbar pr-2">
          <div className="bg-white border border-slate-200 p-8 rounded-[40px] shadow-xl">
            <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 mb-8 flex items-center justify-between">
              Heat Ranking
              <span className="text-orange-500 flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-current animate-ping" />LIVE</span>
            </h3>
            <div className="space-y-4">
              {projection.clusters.slice(0, 10).map((c: ProjectedCluster) => (
                <button
                  key={c.key}
                  onMouseEnter={() => setHoveredKey(c.key)}
                  onMouseLeave={() => setHoveredKey(null)}
                  onClick={() => c.hottestNode && onOpenChain(c.hottestNode.node_key)}
                  className={cn(
                    "w-full group p-5 rounded-[24px] border transition-all text-left",
                    c.selected ? "bg-slate-900 border-slate-900 shadow-2xl scale-[1.02]" : "bg-slate-50 border-slate-100 hover:bg-white hover:border-orange-200"
                  )}
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className={cn("text-md font-black", c.selected ? "text-white" : "text-slate-900")}>{c.shortName}</span>
                    <span className="font-mono text-sm font-black" style={{ color: c.selected ? 'white' : heatColor(c.intensity) }}>{c.heat.toFixed(1)}</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                    <motion.div className="h-full rounded-full" initial={{ width: 0 }} animate={{ width: `${c.intensity*100}%` }} style={{ backgroundColor: heatColor(c.intensity) }} />
                  </div>
                </button>
              ))}
            </div>
          </div>

          <AnimatePresence mode="wait">
            {featured && (
              <motion.div key={featured.key} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="bg-slate-900 p-10 rounded-[40px] text-white shadow-2xl relative overflow-hidden">
                 <div className="relative z-10">
                    <div className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-4">Focused Node Analysis</div>
                    <h3 className="text-3xl font-black mb-8 leading-tight">{featured.name}</h3>
                    <div className="grid grid-cols-2 gap-6 mb-10">
                       <div className="bg-white/5 p-5 rounded-3xl border border-white/10 shadow-inner">
                          <div className="text-[9px] font-black text-slate-500 uppercase mb-2">Aggregate Heat</div>
                          <div className="text-2xl font-black" style={{ color: heatColor(featured.intensity) }}>{featured.heat.toFixed(1)}</div>
                       </div>
                       <div className="bg-white/5 p-5 rounded-3xl border border-white/10 shadow-inner">
                          <div className="text-[9px] font-black text-slate-500 uppercase mb-2">Node Coverage</div>
                          <div className="text-2xl font-black text-indigo-400">{featured.nodes.length}</div>
                       </div>
                    </div>
                    <button onClick={() => featured.hottestNode && onOpenChain(featured.hottestNode.node_key)} className="w-full py-5 bg-white text-slate-900 rounded-[20px] text-xs font-black uppercase tracking-widest hover:bg-orange-500 hover:text-white transition-all shadow-2xl flex items-center justify-center gap-3">
                       进入完整产业链视图 <ArrowUpRight size={20} />
                    </button>
                 </div>
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
      </div>
    </section>
  );
}

function DataTag({ label, value }: { label: string, value: any }) {
  return (
    <div className="bg-slate-50 px-5 py-3 rounded-2xl border border-slate-100 flex items-center gap-3">
       <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">{label}</span>
       <span className="text-md font-black text-slate-900 tabular-nums">{value}</span>
    </div>
  );
}

function buildUniverse(nodes: ChainNode[], edges: ChainEdge[], selectedKey: string | null) {
  const assigned = new Set<string>();
  const rules = CLUSTER_RULES.map(rule => {
    const matched = nodes.filter(n => n.node_key === rule.key || rule.keywords.some(k => n.name.includes(k)));
    matched.forEach(n => assigned.add(n.node_key));
    return clusterFromNodes(rule, matched, selectedKey);
  });
  const fallback = buildFallback(nodes, selectedKey, assigned);
  const all = [...rules, ...fallback].filter(c => c.nodes.length).sort((a,b) => b.heat - a.heat).slice(0, MAX_VISIBLE_CLUSTERS);
  const maxHeat = Math.max(...all.map(c => c.heat), 1);
  const clusters = all.map((c, i) => placeCluster(c, i, all.length, maxHeat));
  const cMap = new Map(clusters.map((c: UniverseCluster) => [c.key, c]));
  const relations = edges.map((e, i) => {
    const s = clusters.find((c: UniverseCluster) => c.nodes.some((n: ChainNode) => n.node_key === e.source));
    const t = clusters.find((c: UniverseCluster) => c.nodes.some((n: ChainNode) => n.node_key === e.target));
    if (!s || !t || s.key === t.key) return null;
    return { key: `rel-${i}`, source: s, target: t, weight: e.weight || 0.5 };
  }).filter(Boolean).slice(0, 40);
  return { clusters, relations, coveredNodeCount: assigned.size };
}
function clusterFromNodes(rule: any, nodes: ChainNode[], selected: string | null) {
  const heat = nodes.reduce((s, n) => s + (n.heat || (n.intensity||0)*100), 0) / Math.max(nodes.length, 1);
  return { ...rule, nodes, heat, hottestNode: nodes.sort((a,b) => (b.heat||0) - (a.heat||0))[0] ?? null, stockCount: nodes.reduce((s,n) => s+(n.stock_count||0), 0), selected: !!selected && nodes.some(n => n.node_key === selected), intensity: 0, base: {x:0, y:0, z:0}, r: 0, rank: 0 };
}
function placeCluster(c: any, i: number, total: number, maxHeat: number) {
  const intensity = Math.min(c.heat / maxHeat, 1);
  const phi = Math.acos(1 - 2 * ((i + 0.5) / total)); const theta = i * Math.PI * (3 - Math.sqrt(5));
  const r = SPHERE_RADIUS * (0.8 + intensity * 0.1);
  return { ...c, intensity, base: { x: Math.cos(theta)*Math.sin(phi)*r, y: Math.sin(theta)*Math.sin(phi)*r, z: Math.cos(phi)*r }, r: 20 + intensity * 20, rank: i };
}
function buildFallback(nodes: ChainNode[], selected: string | null, assigned: Set<string>) {
  const buckets = new Map<string, ChainNode[]>();
  nodes.forEach(n => { if (!assigned.has(n.node_key)) { const l = n.layer || "其他"; buckets.set(l, [...(buckets.get(l)||[]), n]); } });
  return [...buckets.entries()].map(([name, ns], i) => clusterFromNodes({ key: `f-${i}`, name, shortName: name.slice(0,8), color: FALLBACK_COLORS[i%9], glow: "rgba(0,0,0,0.1)", priority: 0, keywords: [] }, ns, selected));
}
function projectUniverse(model: any, rot: Rotation) {
  const clusters = model.clusters.map((c: any) => {
    const p = rotatePoint(c.base, rot); const depth = (p.z + SPHERE_RADIUS) / (SPHERE_RADIUS * 2);
    return { ...c, sx: CENTER_X + p.x * (0.7 + depth * 0.5), sy: CENTER_Y + p.y * (0.7 + depth * 0.5), depth, scale: 0.7 + depth * 0.6, opacity: Math.max(0.1, depth) };
  }).sort((a: any, b: any) => a.depth - b.depth);
  const cMap = new Map(clusters.map((c: ProjectedCluster) => [c.key, c]));
  const relations = (model.relations || []).map((rel: any) => {
    const s = cMap.get(rel.source.key); const t = cMap.get(rel.target.key);
    if (!s || !t) return null;
    return { ...rel, source: s, target: t };
  }).filter(Boolean);
  return { clusters, relations };
}
function rotatePoint(p: Vec3, rot: Rotation) {
  const cY = Math.cos(rot.y); const sY = Math.sin(rot.y);
  const x1 = p.x * cY + p.z * sY; const z1 = -p.x * sY + p.z * cY;
  const cX = Math.cos(rot.x); const sX = Math.sin(rot.x);
  return { x: x1, y: p.y * cX - z1 * sX, z: p.y * sX + z1 * cX };
}
function projectedRelationPath(s: any, t: any) { const cX = CENTER_X + ((s.sx + t.sx)/2 - CENTER_X)*0.3; const cY = CENTER_Y + ((s.sy + t.sy)/2 - CENTER_Y)*0.3; return `M ${s.sx} ${s.sy} Q ${cX} ${cY} ${t.sx} ${t.sy}`; }
function heatColor(i: number) { if (i >= 0.8) return "#ef4444"; if (i >= 0.45) return "#f97316"; return "#eab308"; }
function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(max, v)); }
