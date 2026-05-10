"use client";

import { useMemo, useState } from "react";
import { ArrowUpRight, Sparkles } from "lucide-react";
import type { ChainEdge, ChainNode } from "@/lib/api";

type IndustryUniverseOverviewProps = {
  nodes: ChainNode[];
  edges: ChainEdge[];
  selectedNodeKey: string | null;
  onOpenChain: (nodeKey: string) => void;
};

type ClusterBlueprint = {
  key: string;
  name: string;
  shortName: string;
  color: string;
  glow: string;
  nodeKeys: string[];
};

type UniverseCluster = ClusterBlueprint & {
  nodes: ChainNode[];
  heat: number;
  intensity: number;
  hottestNode: ChainNode | null;
  x: number;
  y: number;
  r: number;
  z: number;
  selected: boolean;
};

type ClusterRelation = {
  key: string;
  source: UniverseCluster;
  target: UniverseCluster;
  weight: number;
};

const WIDTH = 1180;
const HEIGHT = 520;
const CENTER_X = WIDTH / 2;
const CENTER_Y = 268;

const CLUSTERS: ClusterBlueprint[] = [
  {
    key: "ai_compute",
    name: "AI 算力链",
    shortName: "AI算力",
    color: "#f97316",
    glow: "#fed7aa",
    nodeKeys: ["power_grid", "copper", "semiconductor_materials", "power_semiconductor", "hbm_memory", "gpu_advanced_package", "ai_servers", "software_cloud", "ai_compute"]
  },
  {
    key: "power_grid",
    name: "电力电网链",
    shortName: "电力电网",
    color: "#0ea5e9",
    glow: "#bae6fd",
    nodeKeys: ["coal", "natural_gas", "solar_power", "wind_power", "power_grid", "energy_storage_system", "distributed_energy", "industrial_automation"]
  },
  {
    key: "semiconductor",
    name: "半导体设备与器件链",
    shortName: "半导体",
    color: "#ef4444",
    glow: "#fecaca",
    nodeKeys: ["specialty_chemicals", "semiconductor_materials", "semiconductor_equipment", "integrated_circuits", "hbm_memory", "ddr5_memory", "nand_flash", "enterprise_ssd", "optical_modules"]
  },
  {
    key: "new_energy_vehicle",
    name: "新能源车链",
    shortName: "新能源车",
    color: "#22c55e",
    glow: "#bbf7d0",
    nodeKeys: ["lithium_ore", "nickel_ore", "battery_materials", "battery_cells", "power_semiconductor", "charging_swap", "new_energy_vehicle", "used_car_circulation", "battery_recycling"]
  },
  {
    key: "robotics",
    name: "机器人链",
    shortName: "机器人",
    color: "#8b5cf6",
    glow: "#ddd6fe",
    nodeKeys: ["rare_earth_ore", "steel", "industrial_bearings", "sensors", "machine_vision", "robotics_system", "industrial_robot", "software_cloud"]
  },
  {
    key: "consumer_electronics",
    name: "消费电子链",
    shortName: "消费电子",
    color: "#14b8a6",
    glow: "#99f6e4",
    nodeKeys: ["petrochemicals", "display_glass", "pcb_fpc", "mlcc", "high_speed_connectors", "smart_devices", "ecommerce_retail", "electronics_recycling"]
  }
];

export function IndustryUniverseOverview({ nodes, edges, selectedNodeKey, onOpenChain }: IndustryUniverseOverviewProps) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const model = useMemo(() => buildUniverse(nodes, edges, selectedNodeKey), [edges, nodes, selectedNodeKey]);
  const hovered = hoveredKey ? model.clusters.find((cluster) => cluster.key === hoveredKey) : null;
  const featured = hovered ?? model.clusters.find((cluster) => cluster.selected) ?? model.clusters[0] ?? null;

  return (
    <section className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#f7e9de] px-5 py-4">
        <div>
          <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
            <Sparkles size={18} className="text-orange-600" />
            产业宇宙总览图
          </div>
          <div className="mt-1 text-xs text-slate-500">只展示一级/二级产业簇，强关系线保留前 5%，用于判断全市场哪里在发热。</div>
        </div>
        <div className="rounded-full border border-[#f2dfd2] bg-[#fffaf5] px-3 py-1.5 text-xs font-semibold text-orange-700">
          {model.clusters.length} 个产业簇 / {model.relations.length} 条强关系
        </div>
      </div>

      <div className="grid gap-4 bg-[#fffdfa] p-4 xl:grid-cols-[minmax(0,1fr)_270px]">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-[520px] w-full rounded-lg bg-white" role="img" aria-label="产业宇宙总览图">
          <defs>
            <radialGradient id="universe-cover-bg" cx="50%" cy="48%" r="70%">
              <stop offset="0" stopColor="#fff7ed" />
              <stop offset="0.56" stopColor="#ffffff" />
              <stop offset="1" stopColor="#fffaf5" />
            </radialGradient>
            <filter id="universe-cover-glow" x="-70%" y="-70%" width="240%" height="240%">
              <feGaussianBlur stdDeviation="14" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="universe-cover-shadow" x="-40%" y="-40%" width="180%" height="190%">
              <feDropShadow dx="0" dy="16" stdDeviation="14" floodColor="#7c2d12" floodOpacity="0.11" />
            </filter>
          </defs>
          <rect width={WIDTH} height={HEIGHT} fill="url(#universe-cover-bg)" />
          {[112, 184, 256, 328].map((r, index) => (
            <ellipse
              key={r}
              cx={CENTER_X}
              cy={CENTER_Y}
              rx={r * 1.38}
              ry={r * 0.54}
              fill="none"
              stroke={index % 2 ? "#f8d9c6" : "#f1e4d8"}
              strokeWidth="1"
              strokeDasharray="5 12"
              opacity="0.78"
              transform={`rotate(${-14 + index * 8} ${CENTER_X} ${CENTER_Y})`}
            />
          ))}

          <g fill="none">
            {model.relations.map((relation) => {
              const active = relation.source.key === hoveredKey || relation.target.key === hoveredKey || relation.source.selected || relation.target.selected;
              return (
                <path
                  key={relation.key}
                  d={relationPath(relation.source, relation.target)}
                  stroke={active ? "#ea580c" : "#f97316"}
                  strokeWidth={active ? 2.2 + relation.weight * 2.6 : 1.1 + relation.weight * 1.8}
                  strokeOpacity={active ? 0.42 : 0.14}
                  strokeLinecap="round"
                />
              );
            })}
          </g>

          {model.clusters.map((cluster) => {
            const active = cluster.selected || cluster.key === hoveredKey;
            const scale = active ? 1.08 : 1;
            const glowOpacity = active ? 0.34 : 0.14 + cluster.intensity * 0.12;
            return (
              <g
                key={cluster.key}
                role="button"
                tabIndex={0}
                transform={`translate(${cluster.x} ${cluster.y}) scale(${scale})`}
                className="cursor-pointer outline-none transition-transform"
                onMouseEnter={() => setHoveredKey(cluster.key)}
                onMouseLeave={() => setHoveredKey(null)}
                onFocus={() => setHoveredKey(cluster.key)}
                onBlur={() => setHoveredKey(null)}
                onClick={() => cluster.hottestNode && onOpenChain(cluster.hottestNode.node_key)}
                onKeyDown={(event) => {
                  if ((event.key === "Enter" || event.key === " ") && cluster.hottestNode) {
                    event.preventDefault();
                    onOpenChain(cluster.hottestNode.node_key);
                  }
                }}
              >
                <circle r={cluster.r + 24} fill={cluster.color} opacity={glowOpacity} filter="url(#universe-cover-glow)" />
                <circle r={cluster.r} fill="#ffffff" stroke={cluster.color} strokeWidth={active ? 2.8 : 1.5} filter="url(#universe-cover-shadow)" />
                <circle r={Math.max(18, cluster.r * 0.48)} fill={warmColor(cluster.intensity)} opacity="0.94" />
                <circle cx={-cluster.r * 0.2} cy={-cluster.r * 0.28} r={Math.max(4, cluster.r * 0.12)} fill="#ffffff" opacity="0.75" />
                <text y={cluster.r + 27} textAnchor="middle" fill="#111827" fontSize="13" fontWeight="850">
                  {cluster.shortName}
                </text>
                <text y={cluster.r + 47} textAnchor="middle" fill="#9a3412" fontSize="11.5" fontWeight="800">
                  {cluster.heat.toFixed(1)}
                </text>
                <title>{`${cluster.name}｜热度 ${cluster.heat.toFixed(1)}｜点击进入链路图`}</title>
              </g>
            );
          })}
        </svg>

        <aside className="rounded-lg border border-[#f2dfd2] bg-white p-4">
          <div className="text-sm font-semibold text-slate-950">发热产业簇</div>
          <div className="mt-3 space-y-2">
            {model.clusters.slice(0, 6).map((cluster, index) => (
              <button
                key={cluster.key}
                type="button"
                onMouseEnter={() => setHoveredKey(cluster.key)}
                onMouseLeave={() => setHoveredKey(null)}
                onClick={() => cluster.hottestNode && onOpenChain(cluster.hottestNode.node_key)}
                className={`w-full rounded-md border p-3 text-left transition ${
                  cluster.selected ? "border-orange-500 bg-orange-50" : "border-[#f2dfd2] bg-white hover:border-orange-300 hover:bg-[#fffaf5]"
                }`}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="mono w-5 text-xs text-slate-400">{index + 1}</span>
                    <span className="truncate text-sm font-semibold text-slate-900">{cluster.shortName}</span>
                  </div>
                  <span className="mono text-xs font-semibold" style={{ color: warmColor(cluster.intensity) }}>{cluster.heat.toFixed(1)}</span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#ffedd5]">
                  <div className="h-full rounded-full" style={{ width: `${Math.max(cluster.intensity * 100, 8)}%`, backgroundColor: warmColor(cluster.intensity) }} />
                </div>
              </button>
            ))}
          </div>

          {featured ? (
            <div className="mt-4 rounded-lg border border-[#f2dfd2] bg-[#fffaf5] p-3">
              <div className="text-xs font-semibold text-slate-500">当前簇</div>
              <div className="mt-1 text-base font-semibold text-slate-950">{featured.name}</div>
              <div className="mt-2 text-xs leading-5 text-slate-600">
                最热节点：{featured.hottestNode?.name ?? "--"}。默认隐藏细分节点，只把强热度和强关系前置。
              </div>
              {featured.hottestNode ? (
                <button
                  type="button"
                  onClick={() => onOpenChain(featured.hottestNode!.node_key)}
                  className="mt-3 inline-flex h-9 items-center gap-2 rounded-md bg-orange-500 px-3 text-xs font-semibold text-white hover:bg-orange-600"
                >
                  进入链路图
                  <ArrowUpRight size={14} />
                </button>
              ) : null}
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function buildUniverse(nodes: ChainNode[], edges: ChainEdge[], selectedNodeKey: string | null) {
  const nodeMap = new Map(nodes.map((node) => [node.node_key, node]));
  const nodeCluster = new Map<string, string>();
  const rawClusters = CLUSTERS.map((cluster) => {
    const clusterNodes = cluster.nodeKeys.map((key) => nodeMap.get(key)).filter((node): node is ChainNode => Boolean(node));
    for (const node of clusterNodes) nodeCluster.set(node.node_key, cluster.key);
    const heatValues = clusterNodes.map(nodeHeat);
    const avgHeat = heatValues.reduce((sum, heat) => sum + heat, 0) / Math.max(heatValues.length, 1);
    const maxHeat = Math.max(...heatValues, 0);
    const heat = avgHeat * 0.72 + maxHeat * 0.28;
    const hottestNode = [...clusterNodes].sort((left, right) => nodeHeat(right) - nodeHeat(left))[0] ?? null;
    return {
      ...cluster,
      nodes: clusterNodes,
      heat,
      intensity: 0,
      hottestNode,
      x: 0,
      y: 0,
      r: 0,
      z: 0,
      selected: Boolean(selectedNodeKey && clusterNodes.some((node) => node.node_key === selectedNodeKey))
    };
  }).filter((cluster) => cluster.nodes.length);

  const maxHeat = Math.max(...rawClusters.map((cluster) => cluster.heat), 1);
  const clusters: UniverseCluster[] = rawClusters.map((cluster, index) => {
    const intensity = Math.min(cluster.heat / maxHeat, 1);
    const angle = (-96 + index * (360 / rawClusters.length)) * Math.PI / 180;
    const orbit = 136 + intensity * 108;
    const z = Math.sin(angle + 0.42);
    return {
      ...cluster,
      intensity,
      x: CENTER_X + Math.cos(angle) * orbit * 1.34,
      y: CENTER_Y + Math.sin(angle) * orbit * 0.58 - intensity * 22,
      r: 36 + intensity * 34,
      z
    };
  }).sort((left, right) => left.z - right.z);

  const clusterMap = new Map(clusters.map((cluster) => [cluster.key, cluster]));
  const relationMap = new Map<string, ClusterRelation>();
  for (const edge of edges) {
    const sourceKey = nodeCluster.get(edge.source);
    const targetKey = nodeCluster.get(edge.target);
    if (!sourceKey || !targetKey || sourceKey === targetKey) continue;
    const source = clusterMap.get(sourceKey);
    const target = clusterMap.get(targetKey);
    if (!source || !target) continue;
    const key = `${sourceKey}->${targetKey}`;
    const current = relationMap.get(key);
    const weight = edgeScore(edge);
    if (current) {
      current.weight += weight;
    } else {
      relationMap.set(key, { key, source, target, weight });
    }
  }

  const rawRelations = [...relationMap.values()].sort((left, right) => right.weight - left.weight);
  const keepCount = Math.max(3, Math.ceil(rawRelations.length * 0.05));
  const maxWeight = Math.max(...rawRelations.slice(0, keepCount).map((relation) => relation.weight), 1);
  const relations = rawRelations.slice(0, keepCount).map((relation) => ({
    ...relation,
    weight: Math.min(relation.weight / maxWeight, 1)
  }));

  return {
    clusters: clusters.sort((left, right) => right.heat - left.heat),
    relations
  };
}

function relationPath(source: UniverseCluster, target: UniverseCluster) {
  const midX = (source.x + target.x) / 2;
  const midY = (source.y + target.y) / 2;
  const controlX = CENTER_X + (midX - CENTER_X) * 0.18;
  const controlY = CENTER_Y + (midY - CENTER_Y) * 0.18 - 26;
  return `M ${source.x} ${source.y} Q ${controlX} ${controlY} ${target.x} ${target.y}`;
}

function edgeScore(edge: ChainEdge) {
  const heat = edge.heat ?? (edge.intensity ?? 0) * 100;
  return (edge.weight ?? 0.32) * 0.68 + heat / 100 * 0.32;
}

function nodeHeat(node: ChainNode) {
  return Math.max(node.heat ?? 0, node.momentum ?? 0, (node.intensity ?? 0) * 100);
}

function warmColor(intensity: number) {
  if (intensity >= 0.84) return "#b91c1c";
  if (intensity >= 0.62) return "#ea580c";
  if (intensity >= 0.36) return "#f59e0b";
  return "#facc15";
}
