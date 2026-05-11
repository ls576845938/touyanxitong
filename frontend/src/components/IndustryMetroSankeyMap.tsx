"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { GitBranch, RadioTower, Info, Zap, Activity } from "lucide-react";
import type { ChainEdge, ChainNode } from "@/lib/api";

type IndustryMetroSankeyMapProps = {
  nodes: ChainNode[];
  edges: ChainEdge[];
  selectedNodeKey: string | null;
  onSelect: (nodeKey: string) => void;
};

type ChainBlueprint = {
  key: string;
  name: string;
  shortName: string;
  color: string;
  muted: string;
  nodeKeys: string[];
};

type ChainLine = ChainBlueprint & {
  nodes: ChainNode[];
  heat: number;
  intensity: number;
  selected: boolean;
};

type Station = {
  id: string;
  node: ChainNode;
  chain: ChainLine;
  x: number;
  y: number;
  r: number;
  stageIndex: number;
  order: number;
  heat: number;
  intensity: number;
  selected: boolean;
};

type Segment = {
  key: string;
  source: Station;
  target: Station;
  chain: ChainLine;
  width: number;
  intensity: number;
  direct: boolean;
};

const WIDTH = 1400;
const HEIGHT = 800;
const LEFT = 100;
const TOP = 120;
const STAGE_GAP = 180;
const LINE_GAP = 100;

const STAGES = [
  { key: "resource", label: "资源/能源", layers: ["自然资源", "公共品与能源"] },
  { key: "material", label: "基础材料", layers: ["基础材料"] },
  { key: "component", label: "核心零部件", layers: ["通用零部件"] },
  { key: "system", label: "设备系统", layers: ["设备与系统"] },
  { key: "product", label: "终端产品", layers: ["终端产品"] },
  { key: "service", label: "渠道服务", layers: ["渠道与服务"] },
  { key: "recycle", label: "回收再生产", layers: ["回收与再生产"] }
];

const CHAINS: ChainBlueprint[] = [
  {
    key: "ai_compute",
    name: "AI 算力链",
    shortName: "AI算力",
    color: "#f97316",
    muted: "#ffedd5",
    nodeKeys: ["power_grid", "copper", "semiconductor_materials", "power_semiconductor", "hbm_memory", "gpu_advanced_package", "ai_servers", "software_cloud", "ai_compute"]
  },
  {
    key: "power_grid",
    name: "电力电网链",
    shortName: "电力",
    color: "#0ea5e9",
    muted: "#e0f2fe",
    nodeKeys: ["coal", "natural_gas", "solar_power", "wind_power", "power_grid", "energy_storage_system", "distributed_energy", "industrial_automation"]
  },
  {
    key: "semiconductor",
    name: "半导体链",
    shortName: "半导体",
    color: "#ef4444",
    muted: "#fee2e2",
    nodeKeys: ["specialty_chemicals", "semiconductor_materials", "semiconductor_equipment", "integrated_circuits", "hbm_memory", "enterprise_ssd", "optical_modules", "ai_servers"]
  },
  {
    key: "new_energy_vehicle",
    name: "新能源车链",
    shortName: "新能源车",
    color: "#10b981",
    muted: "#d1fae5",
    nodeKeys: ["lithium_ore", "nickel_ore", "battery_materials", "battery_cells", "power_semiconductor", "charging_swap", "new_energy_vehicle", "used_car_circulation", "battery_recycling"]
  },
  {
    key: "robotics",
    name: "机器人链",
    shortName: "机器人",
    color: "#8b5cf6",
    muted: "#f3e8ff",
    nodeKeys: ["rare_earth_ore", "steel", "industrial_bearings", "sensors", "machine_vision", "robotics_system", "industrial_robot", "software_cloud"]
  }
];

export function IndustryMetroSankeyMap({ nodes, edges, selectedNodeKey, onSelect }: IndustryMetroSankeyMapProps) {
  const [hoveredLine, setHoveredLine] = useState<string | null>(null);
  const model = useMemo(() => buildMetro(nodes, edges, selectedNodeKey), [edges, nodes, selectedNodeKey]);
  const activeChainKey = hoveredLine ?? model.lines.find(l => l.selected)?.key ?? model.lines[0]?.key;

  return (
    <div className="relative group bg-slate-50 overflow-hidden rounded-3xl border border-slate-200 shadow-xl transition-all hover:border-slate-300">
      {/* Header Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white/80 backdrop-blur-md px-8 py-5">
        <div className="flex items-center gap-4">
          <div className="h-10 w-10 flex items-center justify-center rounded-xl bg-slate-900 text-white shadow-lg shadow-slate-200">
            <GitBranch size={20} />
          </div>
          <div>
            <h3 className="text-sm font-black uppercase tracking-widest text-slate-900">产业链地铁主图</h3>
            <p className="text-[10px] font-bold text-slate-400 mt-0.5 uppercase tracking-tighter italic">End-to-End Value Propagation Mesh</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {model.lines.map((line) => (
            <button
              key={line.key}
              onMouseEnter={() => setHoveredLine(line.key)}
              onMouseLeave={() => setHoveredLine(null)}
              onClick={() => {
                const hottest = [...line.nodes].sort((a, b) => nodeHeat(b) - nodeHeat(a))[0];
                if (hottest) onSelect(hottest.node_key);
              }}
              className={cn(
                "px-4 py-2 rounded-xl text-xs font-bold transition-all border flex items-center gap-2",
                activeChainKey === line.key 
                  ? "bg-slate-900 border-slate-900 text-white shadow-lg shadow-slate-200" 
                  : "bg-white border-slate-100 text-slate-500 hover:border-slate-200"
              )}
            >
              <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: line.color }} />
              {line.shortName}
            </button>
          ))}
        </div>
      </div>

      {/* Main SVG Area */}
      <div className="overflow-x-auto no-scrollbar scroll-smooth">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="block min-w-[1400px] h-[720px]">
          <defs>
            <filter id="metro-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Vertical Tracks */}
          {STAGES.map((stage, idx) => (
            <g key={stage.key}>
              <rect 
                x={stageX(idx) - 70} 
                y={60} 
                width={140} 
                height={HEIGHT - 100} 
                rx={24} 
                fill="white" 
                opacity={idx % 2 ? 0.4 : 0.8}
                className="shadow-inner"
              />
              <text x={stageX(idx)} y={85} textAnchor="middle" fill="#94a3b8" fontSize="10" fontWeight="900" className="uppercase tracking-[0.2em]">{stage.label}</text>
            </g>
          ))}

          {/* Links / Segments */}
          <g>
            {model.segments.map((seg) => {
              const isActive = seg.chain.key === activeChainKey;
              return (
                <motion.g key={seg.key} initial={{ opacity: 0 }} animate={{ opacity: isActive ? 1 : 0.15 }}>
                  <path
                    d={segmentPath(seg.source, seg.target)}
                    fill="none"
                    stroke={seg.chain.color}
                    strokeWidth={seg.width}
                    strokeLinecap="round"
                    className="transition-all duration-500"
                  />
                  {isActive && (
                    <circle r={2.5} fill="white">
                      <animateMotion dur="2.5s" repeatCount="indefinite" path={segmentPath(seg.source, seg.target)} />
                    </circle>
                  )}
                </motion.g>
              );
            })}
          </g>

          {/* Stations / Nodes */}
          {model.stations.map((st) => {
            const isActive = st.chain.key === activeChainKey || st.selected;
            const hColor = heatColor(st.intensity);
            return (
              <motion.g
                key={st.id}
                onClick={() => onSelect(st.node.node_key)}
                className="cursor-pointer"
                animate={{ opacity: isActive ? 1 : 0.2, scale: isActive ? 1 : 0.95 }}
                whileHover={{ scale: 1.1 }}
              >
                {/* Outer Glow */}
                <circle cx={st.x} cy={st.y} r={st.r * 1.8} fill={st.chain.color} opacity={st.selected ? 0.2 : 0.05} />
                {/* Station Body */}
                <circle cx={st.x} cy={st.y} r={st.r} fill="white" stroke={st.selected ? "#0f172a" : st.chain.color} strokeWidth={st.selected ? 3 : 1.5} />
                {/* Heat Indicator */}
                <circle cx={st.x} cy={st.y} r={st.r * 0.4} fill={hColor} />
                
                {/* Label */}
                {(isActive || st.intensity > 0.7) && (
                  <g transform={`translate(${st.x} ${st.y + st.r + 12})`}>
                    <rect x={-45} y={-10} width={90} height={20} rx={10} fill="white" stroke="#e2e8f0" className="shadow-sm" />
                    <text textAnchor="middle" fill="#1e293b" fontSize="9" fontWeight="900" className="uppercase tracking-tighter">{clipLabel(st.node.name, 10)}</text>
                  </g>
                )}
              </motion.g>
            );
          })}
        </svg>
      </div>

      {/* Floating Insights */}
      <div className="absolute bottom-10 left-10 flex gap-4 pointer-events-none">
        <div className="bg-white/90 backdrop-blur-xl border border-slate-200 p-6 rounded-3xl shadow-2xl pointer-events-auto min-w-[240px]">
          <div className="flex items-center gap-3 mb-4">
            <RadioTower size={16} className="text-orange-500" />
            <span className="text-xs font-black uppercase tracking-widest text-slate-900">Current Flow</span>
          </div>
          <div className="text-lg font-black text-slate-900 mb-1">{model.lines.find(l => l.key === activeChainKey)?.name}</div>
          <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-6">Real-time Node Saturation</div>
          
          <div className="space-y-3">
            <LegendRow label="高热爆红" color="#ef4444" />
            <LegendRow label="活跃扩张" color="#f97316" />
            <LegendRow label="稳健运行" color="#eab308" />
          </div>
        </div>
      </div>
    </div>
  );
}

function LegendRow({ label, color }: { label: string, color: string }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
        <span className="text-[10px] font-bold text-slate-600">{label}</span>
      </div>
      <div className="h-1 w-12 rounded-full bg-slate-100">
        <div className="h-full rounded-full" style={{ width: '70%', backgroundColor: color }} />
      </div>
    </div>
  );
}

// Logic implementations

function buildMetro(nodes: ChainNode[], edges: ChainEdge[], selectedNodeKey: string | null) {
  const nodeMap = new Map(nodes.map(n => [n.node_key, n]));
  const lines = CHAINS.map(c => {
    const lNodes = c.nodeKeys.map(k => nodeMap.get(k)!).filter(Boolean);
    const heat = lNodes.reduce((s, n) => s + nodeHeat(n), 0) / Math.max(lNodes.length, 1);
    return { ...c, nodes: lNodes, heat, intensity: 0, selected: !!selectedNodeKey && lNodes.some(n => n.node_key === selectedNodeKey) };
  }).filter(l => l.nodes.length);

  const maxHeat = Math.max(...lines.map(l => l.heat), 1);
  lines.forEach(l => l.intensity = l.heat / maxHeat);
  
  const stations: Station[] = [];
  const sameStageMap = new Map<string, number>();

  lines.forEach((l, lIdx) => {
    l.nodes.forEach((n, order) => {
      const stage = stageIndex(n);
      const count = sameStageMap.get(`${l.key}:${stage}`) ?? 0;
      sameStageMap.set(`${l.key}:${stage}`, count + 1);
      
      stations.push({
        id: `${l.key}:${n.node_key}`, node: n, chain: l,
        x: stageX(stage) + (count * 20),
        y: TOP + (lIdx * LINE_GAP) + (count % 2 ? 15 : -15),
        r: 8 + nodeIntensity(n) * 10,
        stageIndex: stage, order, heat: nodeHeat(n), intensity: nodeIntensity(n),
        selected: n.node_key === selectedNodeKey
      });
    });
  });

  const segments: Segment[] = [];
  lines.forEach(l => {
    const lStations = stations.filter(s => s.chain.key === l.key).sort((a,b) => a.order - b.order);
    lStations.slice(0, -1).forEach((s, i) => {
      segments.push({
        key: `${l.key}:${i}`, source: s, target: lStations[i+1], chain: l,
        width: 3 + Math.max(s.intensity, lStations[i+1].intensity) * 8,
        intensity: (s.intensity + lStations[i+1].intensity) / 2, direct: true
      });
    });
  });

  return { lines, stations, segments };
}

function stageIndex(n: ChainNode) {
  const i = STAGES.findIndex(s => s.layers.includes(n.layer));
  return i >= 0 ? i : STAGES.length - 1;
}
function stageX(i: number) { return LEFT + i * STAGE_GAP; }
function segmentPath(s: Station, t: Station) {
  const dx = Math.abs(t.x - s.x) * 0.5;
  return `M${s.x},${s.y}C${s.x+dx},${s.y} ${t.x-dx},${t.y} ${t.x},${t.y}`;
}
function heatColor(i: number) {
  if (i >= 0.8) return "#ef4444";
  if (i >= 0.45) return "#f97316";
  return "#eab308";
}
function nodeHeat(n: ChainNode) { return Math.max(n.heat ?? 0, n.momentum ?? 0, (n.intensity ?? 0) * 100); }
function nodeIntensity(n: ChainNode) { return Math.min(Math.max(n.intensity ?? nodeHeat(n)/100, 0), 1); }
function clipLabel(v: string, m: number) { return v.length > m ? `${v.slice(0, m)}..` : v; }
