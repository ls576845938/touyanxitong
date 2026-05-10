"use client";

import { useMemo } from "react";
import { GitBranch, RadioTower } from "lucide-react";
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

const WIDTH = 1320;
const HEIGHT = 650;
const LEFT = 92;
const TOP = 112;
const STAGE_GAP = 178;

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
    muted: "#fed7aa",
    nodeKeys: ["power_grid", "copper", "semiconductor_materials", "power_semiconductor", "hbm_memory", "gpu_advanced_package", "ai_servers", "software_cloud", "ai_compute"]
  },
  {
    key: "power_grid",
    name: "电力电网链",
    shortName: "电力",
    color: "#0ea5e9",
    muted: "#bae6fd",
    nodeKeys: ["coal", "natural_gas", "solar_power", "wind_power", "power_grid", "energy_storage_system", "distributed_energy", "industrial_automation"]
  },
  {
    key: "semiconductor",
    name: "半导体链",
    shortName: "半导体",
    color: "#ef4444",
    muted: "#fecaca",
    nodeKeys: ["specialty_chemicals", "semiconductor_materials", "semiconductor_equipment", "integrated_circuits", "hbm_memory", "enterprise_ssd", "optical_modules", "ai_servers"]
  },
  {
    key: "new_energy_vehicle",
    name: "新能源车链",
    shortName: "新能源车",
    color: "#22c55e",
    muted: "#bbf7d0",
    nodeKeys: ["lithium_ore", "nickel_ore", "battery_materials", "battery_cells", "power_semiconductor", "charging_swap", "new_energy_vehicle", "used_car_circulation", "battery_recycling"]
  },
  {
    key: "robotics",
    name: "机器人链",
    shortName: "机器人",
    color: "#8b5cf6",
    muted: "#ddd6fe",
    nodeKeys: ["rare_earth_ore", "steel", "industrial_bearings", "sensors", "machine_vision", "robotics_system", "industrial_robot", "software_cloud"]
  },
  {
    key: "consumer_electronics",
    name: "消费电子链",
    shortName: "消费电子",
    color: "#14b8a6",
    muted: "#99f6e4",
    nodeKeys: ["petrochemicals", "display_glass", "pcb_fpc", "mlcc", "high_speed_connectors", "smart_devices", "ecommerce_retail", "electronics_recycling"]
  }
];

export function IndustryMetroSankeyMap({ nodes, edges, selectedNodeKey, onSelect }: IndustryMetroSankeyMapProps) {
  const model = useMemo(() => buildMetro(nodes, edges, selectedNodeKey), [edges, nodes, selectedNodeKey]);
  const activeChain = model.lines.find((line) => line.selected) ?? model.lines[0] ?? null;

  return (
    <section className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#f7e9de] px-5 py-4">
        <div>
          <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
            <GitBranch size={18} className="text-orange-600" />
            产业链地铁 / 桑基主图
          </div>
          <div className="mt-1 text-xs text-slate-500">资源/能源 → 基础材料 → 核心零部件 → 设备系统 → 终端产品 → 渠道服务 → 回收再生产</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {model.lines.map((line) => (
            <button
              key={line.key}
              type="button"
              onClick={() => {
                const hottest = [...line.nodes].sort((left, right) => nodeHeat(right) - nodeHeat(left))[0];
                if (hottest) onSelect(hottest.node_key);
              }}
              className={`inline-flex h-9 items-center gap-2 rounded-md border px-3 text-xs font-semibold transition ${
                line.selected ? "border-orange-500 bg-orange-50 text-orange-700" : "border-[#f2dfd2] bg-white text-slate-600 hover:border-orange-300"
              }`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: line.color }} />
              {line.shortName}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto bg-[#fffdfa]">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="block min-w-[1080px]" style={{ height: HEIGHT }} role="img" aria-label="产业链地铁桑基图">
          <defs>
            <filter id="metro-sankey-shadow" x="-40%" y="-40%" width="180%" height="190%">
              <feDropShadow dx="0" dy="9" stdDeviation="8" floodColor="#7c2d12" floodOpacity="0.11" />
            </filter>
            <filter id="metro-sankey-glow" x="-70%" y="-70%" width="240%" height="240%">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <style>{`
              @keyframes metroFlow {
                from { stroke-dashoffset: 0; }
                to { stroke-dashoffset: -56; }
              }
              .metro-flow {
                animation: metroFlow 2.2s linear infinite;
              }
            `}</style>
          </defs>
          <rect width={WIDTH} height={HEIGHT} fill="#fffdfa" />
          {STAGES.map((stage, index) => {
            const x = stageX(index);
            return (
              <g key={stage.key}>
                <rect x={x - 64} y="52" width="128" height={HEIGHT - 98} rx="18" fill={index % 2 ? "#fff7ed" : "#ffffff"} stroke="#f5dfcf" />
                <text x={x} y="82" textAnchor="middle" fill="#111827" fontSize="13" fontWeight="850">{stage.label}</text>
              </g>
            );
          })}

          <g fill="none">
            {model.segments.map((segment) => {
              const active = segment.chain.key === activeChain?.key || segment.source.selected || segment.target.selected;
              return (
                <g key={segment.key} opacity={active ? 1 : 0.22}>
                  <path
                    d={segmentPath(segment.source, segment.target)}
                    stroke={segment.chain.muted}
                    strokeWidth={segment.width + 7}
                    strokeOpacity={active ? 0.32 : 0.12}
                    strokeLinecap="round"
                  />
                  <path
                    d={segmentPath(segment.source, segment.target)}
                    stroke={segment.chain.color}
                    strokeWidth={segment.width}
                    strokeOpacity={segment.direct ? (active ? 0.72 : 0.34) : (active ? 0.44 : 0.2)}
                    strokeLinecap="round"
                  />
                  {active ? (
                    <path
                      d={segmentPath(segment.source, segment.target)}
                      className="metro-flow"
                      stroke={warmColor(segment.intensity)}
                      strokeWidth={Math.max(2.2, segment.width * 0.35)}
                      strokeOpacity="0.92"
                      strokeDasharray="8 48"
                      strokeLinecap="round"
                    />
                  ) : null}
                </g>
              );
            })}
          </g>

          {model.lines.map((line) => {
            const y = lineY(model.lines.indexOf(line));
            return (
              <g key={`label-${line.key}`} opacity={line.key === activeChain?.key ? 1 : 0.48}>
                <text x="28" y={y + 4} fill={line.color} fontSize="12.5" fontWeight="850">{line.shortName}</text>
              </g>
            );
          })}

          {model.stations.map((station) => {
            const active = station.chain.key === activeChain?.key || station.selected;
            const border = momentumBorder(station.node);
            const labelVisible = active || station.intensity > 0.58 || station.selected;
            return (
              <g
                key={station.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelect(station.node.node_key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(station.node.node_key);
                  }
                }}
                className="cursor-pointer outline-none"
                opacity={active ? 1 : 0.48}
              >
                <circle cx={station.x} cy={station.y} r={station.r + 11} fill={station.chain.muted} opacity={station.selected ? 0.7 : 0.32} filter={station.selected ? "url(#metro-sankey-glow)" : undefined} />
                <circle cx={station.x} cy={station.y} r={station.r} fill={warmColor(station.intensity)} stroke={station.selected ? "#111827" : border.color} strokeWidth={station.selected ? 3.2 : border.width} filter="url(#metro-sankey-shadow)" />
                <circle cx={station.x - station.r * 0.24} cy={station.y - station.r * 0.26} r={Math.max(2.5, station.r * 0.17)} fill="#ffffff" opacity="0.7" />
                {labelVisible ? (
                  <g transform={`translate(${station.x - 54} ${station.y + station.r + 10})`}>
                    <rect width="108" height="27" rx="8" fill="#ffffff" fillOpacity="0.96" stroke="#f2dfd2" />
                    <text x="54" y="18" textAnchor="middle" fill="#111827" fontSize="11.5" fontWeight="750">{clipLabel(station.node.name, 8)}</text>
                  </g>
                ) : null}
                <title>{`${station.chain.name}｜${station.node.name}｜热度 ${station.heat.toFixed(1)}｜${border.label}`}</title>
              </g>
            );
          })}

          <Legend activeChain={activeChain} />
        </svg>
      </div>
    </section>
  );
}

function buildMetro(nodes: ChainNode[], edges: ChainEdge[], selectedNodeKey: string | null) {
  const nodeMap = new Map(nodes.map((node) => [node.node_key, node]));
  const rawLines = CHAINS.map((chain) => {
    const lineNodes = chain.nodeKeys.map((key) => nodeMap.get(key)).filter((node): node is ChainNode => Boolean(node));
    const heat = lineNodes.reduce((sum, node) => sum + nodeHeat(node), 0) / Math.max(lineNodes.length, 1);
    return {
      ...chain,
      nodes: lineNodes,
      heat,
      intensity: 0,
      selected: Boolean(selectedNodeKey && lineNodes.some((node) => node.node_key === selectedNodeKey))
    };
  }).filter((line) => line.nodes.length);

  const maxHeat = Math.max(...rawLines.map((line) => line.heat), 1);
  const lines: ChainLine[] = rawLines
    .map((line) => ({ ...line, intensity: Math.min(line.heat / maxHeat, 1) }))
    .sort((left, right) => Number(right.selected) - Number(left.selected) || right.heat - left.heat);

  if (!lines.some((line) => line.selected) && lines[0]) lines[0].selected = true;

  const stations: Station[] = [];
  const sameStageCounter = new Map<string, number>();
  lines.forEach((line, lineIndex) => {
    line.nodes.forEach((node, order) => {
      const stage = stageIndex(node);
      const counterKey = `${line.key}:${stage}`;
      const offset = sameStageCounter.get(counterKey) ?? 0;
      sameStageCounter.set(counterKey, offset + 1);
      const heat = nodeHeat(node);
      const intensity = nodeIntensity(node);
      stations.push({
        id: `${line.key}:${node.node_key}:${order}`,
        node,
        chain: line,
        x: stageX(stage) + (offset - 0.5) * 22,
        y: lineY(lineIndex) + (offset % 2 ? 16 : 0),
        r: 9 + intensity * 9 + Math.min(node.stock_count ?? 0, 14) * 0.35,
        stageIndex: stage,
        order,
        heat,
        intensity,
        selected: node.node_key === selectedNodeKey
      });
    });
  });

  const edgeMap = new Map(edges.map((edge) => [`${edge.source}->${edge.target}`, edge]));
  const segments: Segment[] = [];
  for (const line of lines) {
    const lineStations = stations.filter((station) => station.chain.key === line.key).sort((left, right) => left.order - right.order);
    lineStations.slice(0, -1).forEach((station, index) => {
      const next = lineStations[index + 1];
      const directEdge = edgeMap.get(`${station.node.node_key}->${next.node.node_key}`);
      const reverseEdge = edgeMap.get(`${next.node.node_key}->${station.node.node_key}`);
      const edge = directEdge ?? reverseEdge;
      const intensity = edge ? edgeIntensity(edge, station, next) : Math.min((station.intensity + next.intensity) / 2, 1);
      segments.push({
        key: `${line.key}:${station.node.node_key}->${next.node.node_key}:${index}`,
        source: station,
        target: next,
        chain: line,
        width: 4.6 + intensity * 7.6,
        intensity,
        direct: Boolean(directEdge)
      });
    });
  }

  return { lines, stations, segments };
}

function stageIndex(node: ChainNode) {
  const index = STAGES.findIndex((stage) => stage.layers.includes(node.layer));
  return index >= 0 ? index : STAGES.length - 1;
}

function stageX(index: number) {
  return LEFT + index * STAGE_GAP;
}

function lineY(index: number) {
  return TOP + index * 82;
}

function segmentPath(source: Station, target: Station) {
  const dx = Math.max(48, Math.abs(target.x - source.x) * 0.42);
  return `M ${source.x} ${source.y} C ${source.x + dx} ${source.y}, ${target.x - dx} ${target.y}, ${target.x} ${target.y}`;
}

function edgeIntensity(edge: ChainEdge, source: Station, target: Station) {
  const heat = edge.heat ?? (edge.intensity ?? 0) * 100;
  const edgeValue = Math.max(heat / 100, edge.weight ?? 0);
  return Math.min(Math.max(edgeValue * 0.62 + ((source.intensity + target.intensity) / 2) * 0.38, 0), 1);
}

function nodeHeat(node: ChainNode) {
  return Math.max(node.heat ?? 0, node.momentum ?? 0, (node.intensity ?? 0) * 100);
}

function nodeIntensity(node: ChainNode) {
  const value = node.intensity ?? nodeHeat(node) / 100;
  return Math.min(Math.max(value, 0), 1);
}

function momentumBorder(node: ChainNode) {
  const momentum = node.momentum ?? null;
  if (momentum === null) return { color: "#ffffff", width: 2, label: "动量未知" };
  if (momentum >= 66) return { color: "#dc2626", width: 3.2, label: "上涨加速" };
  if (momentum <= 30) return { color: "#64748b", width: 2.1, label: "动量回落" };
  return { color: "#f59e0b", width: 2.4, label: "横盘蓄势" };
}

function Legend({ activeChain }: { activeChain: ChainLine | null }) {
  return (
    <g transform="translate(1038 526)">
      <rect width="250" height="92" rx="14" fill="#ffffff" fillOpacity="0.95" stroke="#f2dfd2" />
      <g transform="translate(16 22)">
        <RadioTower size={15} color="#ea580c" />
        <text x="24" y="5" fill="#111827" fontSize="12" fontWeight="850">{activeChain?.name ?? "主路径"}</text>
      </g>
      <g transform="translate(18 48)">
        <circle r="5" fill="#dc2626" />
        <text x="14" y="4" fill="#64748b" fontSize="11.5" fontWeight="700">红边：上涨加速</text>
      </g>
      <g transform="translate(18 70)">
        <circle r="5" fill="#f59e0b" />
        <text x="14" y="4" fill="#64748b" fontSize="11.5" fontWeight="700">黄橙红：节点热度</text>
      </g>
    </g>
  );
}

function warmColor(intensity: number) {
  if (intensity >= 0.84) return "#b91c1c";
  if (intensity >= 0.62) return "#ea580c";
  if (intensity >= 0.36) return "#f59e0b";
  return "#facc15";
}

function clipLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}
