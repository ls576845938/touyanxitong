"use client";

import { useMemo, useState } from "react";
import { ArrowUpRight, Cpu, RadioTower, Sparkles } from "lucide-react";
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
  halo: string;
  nodeKeys?: string[];
  keywords: string[];
  priority: number;
};

type UniverseCluster = {
  key: string;
  name: string;
  shortName: string;
  color: string;
  halo: string;
  nodes: ChainNode[];
  heat: number;
  intensity: number;
  hottestNode: ChainNode | null;
  stockCount: number;
  x: number;
  y: number;
  r: number;
  z: number;
  selected: boolean;
  ring: number;
  rank: number;
};

type ClusterRelation = {
  key: string;
  source: UniverseCluster;
  target: UniverseCluster;
  weight: number;
};

const WIDTH = 1240;
const HEIGHT = 580;
const CENTER_X = 565;
const CENTER_Y = 292;
const MAX_VISIBLE_CLUSTERS = 12;

const CLUSTER_RULES: ClusterRule[] = [
  {
    key: "power_grid",
    name: "电力电网与新型能源",
    shortName: "电力电网",
    color: "#0ea5e9",
    halo: "#bae6fd",
    priority: 100,
    nodeKeys: ["power_grid", "thermal_power", "nuclear_power", "hydropower", "solar_power", "wind_power", "distributed_energy", "energy_storage_system", "charging_swap"],
    keywords: ["电力电网", "储能", "光伏", "风电", "核电", "火电", "水电", "分布式能源", "充换电"]
  },
  {
    key: "ai_compute",
    name: "AI 算力与云基础设施",
    shortName: "AI算力",
    color: "#f97316",
    halo: "#fed7aa",
    priority: 96,
    nodeKeys: ["ai_compute", "ai_servers", "gpu_advanced_package", "hbm_memory", "enterprise_ssd", "optical_modules", "telecom_equipment", "software_cloud"],
    keywords: ["AI算力", "AI 服务器", "GPU", "HBM", "企业 SSD", "光模块", "通信设备", "软件服务", "云"]
  },
  {
    key: "semiconductor",
    name: "半导体设备材料与器件",
    shortName: "半导体",
    color: "#ef4444",
    halo: "#fecaca",
    priority: 92,
    nodeKeys: ["semiconductor_materials", "semiconductor_equipment", "integrated_circuits", "power_semiconductor", "pcb_fpc", "mlcc", "high_speed_connectors", "abf_substrate"],
    keywords: ["半导体", "集成电路", "功率器件", "电子化学品", "PCB", "MLCC", "连接器", "ABF", "存储"]
  },
  {
    key: "ev_battery",
    name: "新能源车与电池系统",
    shortName: "新能源车",
    color: "#22c55e",
    halo: "#bbf7d0",
    priority: 88,
    nodeKeys: ["new_energy_vehicle", "battery_cells", "battery_materials", "battery_recycling", "lithium_ore", "nickel_ore", "charging_swap", "used_car_circulation"],
    keywords: ["新能源车", "电池", "锂", "镍", "充换电", "汽车零部件", "二手车"]
  },
  {
    key: "robotics",
    name: "机器人与工业自动化",
    shortName: "机器人",
    color: "#8b5cf6",
    halo: "#ddd6fe",
    priority: 84,
    nodeKeys: ["industrial_automation", "robotics_system", "industrial_robot", "sensors", "machine_vision", "industrial_bearings", "hydraulic_pneumatic"],
    keywords: ["机器人", "工业自动化", "传感器", "机器视觉", "轴承", "液压", "工程机械"]
  },
  {
    key: "oil_chemical",
    name: "油气炼化与化工材料",
    shortName: "油气化工",
    color: "#f59e0b",
    halo: "#fde68a",
    priority: 78,
    nodeKeys: ["crude_oil", "natural_gas", "lng_gas", "refinery_fuels", "petrochemicals", "specialty_chemicals", "plastics_rubber", "coal"],
    keywords: ["油气", "煤炭", "炼化", "化工材料", "塑料橡胶", "精细化工", "LNG"]
  },
  {
    key: "metals",
    name: "金属矿产与基础材料",
    shortName: "金属矿产",
    color: "#64748b",
    halo: "#cbd5e1",
    priority: 74,
    nodeKeys: ["iron_ore", "copper_ore", "bauxite", "steel", "aluminum", "copper", "rare_earth_ore", "lithium_ore", "nickel_ore"],
    keywords: ["有色金属", "钢铁", "铜", "铝", "铁矿", "稀土", "锂", "镍", "金属"]
  },
  {
    key: "healthcare",
    name: "医疗健康与生命科学",
    shortName: "医疗健康",
    color: "#ec4899",
    halo: "#fbcfe8",
    priority: 70,
    nodeKeys: ["innovative_drugs", "medical_devices", "diagnostics_ivd", "healthcare_services", "biotech_feedstock"],
    keywords: ["医疗器械", "创新药", "CXO", "诊断", "医疗服务", "生物"]
  },
  {
    key: "consumer_electronics",
    name: "消费电子与智能终端",
    shortName: "消费电子",
    color: "#14b8a6",
    halo: "#99f6e4",
    priority: 66,
    nodeKeys: ["smart_devices", "home_appliances", "display_glass", "pcb_fpc", "mlcc", "passive_components", "electronics_recycling"],
    keywords: ["消费电子", "家电", "智能设备", "显示", "被动元件", "电子回收"]
  },
  {
    key: "urban_system",
    name: "建筑城市与公共系统",
    shortName: "城市系统",
    color: "#a855f7",
    halo: "#e9d5ff",
    priority: 62,
    nodeKeys: ["building_construction", "cement_glass", "construction_machinery", "hvac_building_system", "water_utility", "scrap_steel_recycling"],
    keywords: ["建筑建材", "房地产", "工程机械", "环保水务", "城市更新", "暖通"]
  },
  {
    key: "consumer_service",
    name: "消费零售与互联网渠道",
    shortName: "消费渠道",
    color: "#06b6d4",
    halo: "#a5f3fc",
    priority: 58,
    nodeKeys: ["branded_food_beverage", "apparel_home", "ecommerce_retail", "internet_platform", "travel_hospitality", "corn_soybean"],
    keywords: ["食品饮料", "纺织服饰", "零售", "互联网平台", "旅游", "农业"]
  },
  {
    key: "logistics_finance",
    name: "物流航运与金融结算",
    shortName: "物流金融",
    color: "#2563eb",
    halo: "#bfdbfe",
    priority: 54,
    nodeKeys: ["logistics_express", "shipping_ports", "payments_fintech", "banking", "insurance", "brokerage_asset_mgmt"],
    keywords: ["物流快递", "航运港口", "支付", "银行", "保险", "券商", "金融"]
  }
];

const FALLBACK_COLORS = ["#f97316", "#0ea5e9", "#ef4444", "#22c55e", "#8b5cf6", "#14b8a6", "#f59e0b", "#ec4899"];

export function IndustryUniverseOverview({ nodes, edges, selectedNodeKey, onOpenChain }: IndustryUniverseOverviewProps) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const model = useMemo(() => buildUniverse(nodes, edges, selectedNodeKey), [edges, nodes, selectedNodeKey]);
  const hovered = hoveredKey ? model.clusters.find((cluster) => cluster.key === hoveredKey) : null;
  const featured = hovered ?? model.clusters.find((cluster) => cluster.selected) ?? model.clusters[0] ?? null;

  return (
    <section className="overflow-hidden rounded-lg border border-[#dbeafe] bg-white shadow-[0_22px_70px_rgba(15,23,42,0.08)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e0f2fe] bg-white px-5 py-4">
        <div>
          <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
            <Sparkles size={18} className="text-orange-600" />
            产业宇宙总览图
          </div>
          <div className="mt-1 text-xs text-slate-500">全市场产业簇热度扫描</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <DataPill label="产业簇" value={model.clusters.length} />
          <DataPill label="强关系" value={model.relations.length} />
          <DataPill label="覆盖节点" value={model.coveredNodeCount} />
        </div>
      </div>

      <div className="grid gap-4 bg-[#f8fbff] p-4 xl:grid-cols-[minmax(0,1fr)_292px]">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-[580px] w-full rounded-lg border border-[#dbeafe] bg-white" role="img" aria-label="产业宇宙总览图">
          <defs>
            <radialGradient id="tech-universe-bg" cx="52%" cy="46%" r="74%">
              <stop offset="0" stopColor="#ffffff" />
              <stop offset="0.52" stopColor="#f8fbff" />
              <stop offset="1" stopColor="#eef6ff" />
            </radialGradient>
            <linearGradient id="tech-axis" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stopColor="#38bdf8" stopOpacity="0.08" />
              <stop offset="0.45" stopColor="#f97316" stopOpacity="0.22" />
              <stop offset="1" stopColor="#ef4444" stopOpacity="0.06" />
            </linearGradient>
            <filter id="tech-cluster-glow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="16" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="tech-node-shadow" x="-50%" y="-50%" width="200%" height="210%">
              <feDropShadow dx="0" dy="18" stdDeviation="16" floodColor="#0f172a" floodOpacity="0.13" />
            </filter>
            <pattern id="tech-grid" width="36" height="36" patternUnits="userSpaceOnUse">
              <path d="M 36 0 L 0 0 0 36" fill="none" stroke="#dbeafe" strokeWidth="0.8" opacity="0.62" />
            </pattern>
          </defs>

          <rect width={WIDTH} height={HEIGHT} fill="url(#tech-universe-bg)" />
          <rect width={WIDTH} height={HEIGHT} fill="url(#tech-grid)" opacity="0.42" />
          <path d={`M 64 ${CENTER_Y + 126} C 278 ${CENTER_Y - 106}, 822 ${CENTER_Y - 120}, 1176 ${CENTER_Y + 98}`} fill="none" stroke="url(#tech-axis)" strokeWidth="56" strokeLinecap="round" />

          {[118, 196, 278, 356].map((r, index) => (
            <ellipse
              key={r}
              cx={CENTER_X}
              cy={CENTER_Y}
              rx={r * 1.42}
              ry={r * 0.48}
              fill="none"
              stroke={index === 2 ? "#fdba74" : "#93c5fd"}
              strokeWidth={index === 2 ? 1.4 : 1}
              strokeDasharray={index % 2 ? "6 13" : "2 11"}
              opacity={index === 2 ? 0.56 : 0.34}
              transform={`rotate(${-12 + index * 7} ${CENTER_X} ${CENTER_Y})`}
            />
          ))}

          <g transform={`translate(${CENTER_X - 92} ${CENTER_Y - 39})`}>
            <rect width="184" height="78" rx="22" fill="#ffffff" fillOpacity="0.92" stroke="#bfdbfe" />
            <g transform="translate(22 24)">
              <Cpu size={19} color="#f97316" />
              <text x="29" y="5" fill="#0f172a" fontSize="13" fontWeight="850">Market Heat Core</text>
              <text x="29" y="26" fill="#64748b" fontSize="11.5" fontWeight="700">全市场产业簇</text>
            </g>
          </g>

          <g fill="none">
            {model.relations.map((relation) => {
              const active = relation.source.key === hoveredKey || relation.target.key === hoveredKey || relation.source.selected || relation.target.selected;
              return (
                <path
                  key={relation.key}
                  d={relationPath(relation.source, relation.target)}
                  stroke={active ? "#f97316" : "#38bdf8"}
                  strokeWidth={active ? 2.2 + relation.weight * 3.4 : 0.9 + relation.weight * 2.2}
                  strokeOpacity={active ? 0.58 : 0.15}
                  strokeLinecap="round"
                  strokeDasharray={active ? "0" : "4 10"}
                />
              );
            })}
          </g>

          {model.clusters.map((cluster) => {
            const active = cluster.selected || cluster.key === hoveredKey;
            const front = cluster.rank < 4 || active;
            const labelVisible = front || cluster.rank < 9;
            const scale = active ? 1.12 : front ? 1.04 : 1;
            return (
              <g
                key={cluster.key}
                role="button"
                tabIndex={0}
                transform={`translate(${cluster.x} ${cluster.y}) scale(${scale})`}
                className="cursor-pointer outline-none"
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
                opacity={front ? 1 : 0.82}
              >
                <circle r={cluster.r + 31} fill={cluster.color} opacity={active ? 0.28 : 0.12 + cluster.intensity * 0.16} filter="url(#tech-cluster-glow)" />
                <circle r={cluster.r + 12} fill="#ffffff" stroke={cluster.halo} strokeWidth="9" opacity="0.9" />
                <circle r={cluster.r} fill="#ffffff" stroke={active ? "#0f172a" : cluster.color} strokeWidth={active ? 2.6 : 1.7} filter="url(#tech-node-shadow)" />
                <path d={gaugePath(cluster.r * 0.78)} fill="none" stroke={warmColor(cluster.intensity)} strokeWidth="7" strokeLinecap="round" />
                <circle r={Math.max(11, cluster.r * 0.27)} fill={warmColor(cluster.intensity)} opacity="0.96" />
                <text y="5" textAnchor="middle" fill="#ffffff" fontSize="10.5" fontWeight="900">
                  {cluster.rank + 1}
                </text>
                {labelVisible ? (
                  <g transform={`translate(${-Math.max(58, cluster.shortName.length * 8)} ${cluster.r + 15})`}>
                    <rect width={Math.max(116, cluster.shortName.length * 16)} height="34" rx="11" fill="#ffffff" fillOpacity="0.96" stroke="#dbeafe" />
                    <text x={Math.max(58, cluster.shortName.length * 8)} y="14" textAnchor="middle" fill="#0f172a" fontSize="12" fontWeight="850">
                      {cluster.shortName}
                    </text>
                    <text x={Math.max(58, cluster.shortName.length * 8)} y="28" textAnchor="middle" fill="#ea580c" fontSize="10.5" fontWeight="800">
                      {cluster.heat.toFixed(1)} / {cluster.nodes.length} 节点
                    </text>
                  </g>
                ) : null}
                <title>{`${cluster.name}｜热度 ${cluster.heat.toFixed(1)}｜最热节点 ${cluster.hottestNode?.name ?? "--"}`}</title>
              </g>
            );
          })}
        </svg>

        <aside className="space-y-3">
          <section className="rounded-lg border border-[#dbeafe] bg-white p-4 shadow-[0_12px_32px_rgba(15,23,42,0.05)]">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
              <RadioTower size={16} className="text-orange-600" />
              热点产业簇
            </div>
            <div className="mt-3 space-y-2">
              {model.clusters.slice(0, 8).map((cluster) => (
                <button
                  key={cluster.key}
                  type="button"
                  onMouseEnter={() => setHoveredKey(cluster.key)}
                  onMouseLeave={() => setHoveredKey(null)}
                  onClick={() => cluster.hottestNode && onOpenChain(cluster.hottestNode.node_key)}
                  className={`w-full rounded-md border p-3 text-left transition ${
                    cluster.selected ? "border-orange-500 bg-orange-50" : "border-[#dbeafe] bg-white hover:border-orange-300 hover:bg-[#fffaf5]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="mono w-5 text-xs text-slate-400">{cluster.rank + 1}</span>
                      <span className="truncate text-sm font-semibold text-slate-900">{cluster.shortName}</span>
                    </div>
                    <span className="mono text-xs font-semibold" style={{ color: warmColor(cluster.intensity) }}>{cluster.heat.toFixed(1)}</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#e0f2fe]">
                    <div className="h-full rounded-full" style={{ width: `${Math.max(cluster.intensity * 100, 9)}%`, backgroundColor: warmColor(cluster.intensity) }} />
                  </div>
                </button>
              ))}
            </div>
          </section>

          {featured ? (
            <section className="rounded-lg border border-[#dbeafe] bg-white p-4 shadow-[0_12px_32px_rgba(15,23,42,0.05)]">
              <div className="text-xs font-semibold uppercase text-slate-400">Selected Cluster</div>
              <div className="mt-2 text-lg font-semibold text-slate-950">{featured.name}</div>
              <div className="mt-3 grid grid-cols-3 gap-2">
                <MiniData label="热度" value={featured.heat.toFixed(1)} />
                <MiniData label="节点" value={featured.nodes.length} />
                <MiniData label="股票" value={featured.stockCount} />
              </div>
              <div className="mt-3 rounded-md bg-[#f8fbff] p-3 text-xs leading-5 text-slate-600">
                最热节点：<span className="font-semibold text-slate-900">{featured.hottestNode?.name ?? "--"}</span>
              </div>
              {featured.hottestNode ? (
                <button
                  type="button"
                  onClick={() => onOpenChain(featured.hottestNode!.node_key)}
                  className="mt-3 inline-flex h-9 items-center gap-2 rounded-md bg-slate-950 px-3 text-xs font-semibold text-white hover:bg-orange-600"
                >
                  进入地铁链路
                  <ArrowUpRight size={14} />
                </button>
              ) : null}
            </section>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function DataPill({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-full border border-[#dbeafe] bg-[#f8fbff] px-3 py-1.5 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="mono ml-2 font-semibold text-slate-950">{value}</span>
    </div>
  );
}

function MiniData({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-[#dbeafe] bg-[#f8fbff] px-2 py-2 text-center">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mono mt-1 text-sm font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function buildUniverse(nodes: ChainNode[], edges: ChainEdge[], selectedNodeKey: string | null) {
  const ruleClusters = buildRuleClusters(nodes, selectedNodeKey);
  const fallbackClusters = buildFallbackIndustryClusters(nodes, selectedNodeKey, ruleClusters.assignedNodeKeys);
  const rawClusters = [...ruleClusters.clusters, ...fallbackClusters]
    .filter((cluster) => cluster.nodes.length)
    .sort((left, right) => right.heat - left.heat || right.nodes.length - left.nodes.length)
    .slice(0, MAX_VISIBLE_CLUSTERS);

  const maxHeat = Math.max(...rawClusters.map((cluster) => cluster.heat), 1);
  const placed = rawClusters.map((cluster, index) => placeCluster(cluster, index, rawClusters.length, maxHeat));
  const nodeCluster = assignNodesToVisibleClusters(placed);
  const relations = buildRelations(placed, edges, nodeCluster);

  return {
    clusters: placed,
    relations,
    coveredNodeCount: new Set(placed.flatMap((cluster) => cluster.nodes.map((node) => node.node_key))).size
  };
}

function buildRuleClusters(nodes: ChainNode[], selectedNodeKey: string | null) {
  const assignedNodeKeys = new Set<string>();
  const clusters = CLUSTER_RULES.map((rule) => {
    const ruleNodeKeySet = new Set(rule.nodeKeys ?? []);
    const clusterNodes = nodes.filter((node) => ruleNodeKeySet.has(node.node_key) || rule.keywords.some((keyword) => nodeText(node).includes(keyword.toLowerCase())));
    for (const node of clusterNodes) assignedNodeKeys.add(node.node_key);
    return clusterFromNodes(rule, clusterNodes, selectedNodeKey);
  });

  return { clusters, assignedNodeKeys };
}

function buildFallbackIndustryClusters(nodes: ChainNode[], selectedNodeKey: string | null, assignedNodeKeys: Set<string>) {
  const buckets = new Map<string, ChainNode[]>();
  for (const node of nodes) {
    if (assignedNodeKeys.has(node.node_key)) continue;
    const industry = node.industry_names?.[0] || node.tags?.[0] || node.layer;
    if (!industry) continue;
    buckets.set(industry, [...(buckets.get(industry) ?? []), node]);
  }

  return [...buckets.entries()].map(([name, bucket], index) => clusterFromNodes({
    key: `industry_${safeKey(name)}`,
    name,
    shortName: name.length > 6 ? `${name.slice(0, 6)}` : name,
    color: FALLBACK_COLORS[index % FALLBACK_COLORS.length],
    halo: "#dbeafe",
    priority: 20 - index,
    keywords: []
  }, bucket, selectedNodeKey));
}

function clusterFromNodes(rule: ClusterRule, clusterNodes: ChainNode[], selectedNodeKey: string | null) {
  const heatValues = clusterNodes.map(nodeHeat);
  const avgHeat = heatValues.reduce((sum, heat) => sum + heat, 0) / Math.max(heatValues.length, 1);
  const maxHeat = Math.max(...heatValues, 0);
  const stockCount = clusterNodes.reduce((sum, node) => sum + (node.stock_count ?? 0), 0);
  const heat = avgHeat * 0.6 + maxHeat * 0.32 + Math.min(stockCount, 60) * 0.08;
  const hottestNode = [...clusterNodes].sort((left, right) => nodeHeat(right) - nodeHeat(left))[0] ?? null;
  return {
    key: rule.key,
    name: rule.name,
    shortName: rule.shortName,
    color: rule.color,
    halo: rule.halo,
    nodes: clusterNodes,
    heat,
    intensity: 0,
    hottestNode,
    stockCount,
    x: 0,
    y: 0,
    r: 0,
    z: 0,
    selected: Boolean(selectedNodeKey && clusterNodes.some((node) => node.node_key === selectedNodeKey)),
    ring: 0,
    rank: 0,
    priority: rule.priority
  };
}

function placeCluster(cluster: ReturnType<typeof clusterFromNodes>, index: number, total: number, maxHeat: number): UniverseCluster {
  const intensity = Math.min(Math.max(cluster.heat / maxHeat, 0), 1);
  const rank = index;
  const ring = index < 4 ? 0 : index < 8 ? 1 : 2;
  const ringIndex = ring === 0 ? index : ring === 1 ? index - 4 : index - 8;
  const ringCount = ring === 0 ? Math.min(4, total) : ring === 1 ? Math.min(4, Math.max(total - 4, 1)) : Math.max(total - 8, 1);
  const angleBase = ring === 0 ? -92 : ring === 1 ? -56 : -102;
  const angle = (angleBase + ringIndex * (360 / ringCount) + ring * 14) * Math.PI / 180;
  const orbit = ring === 0 ? 142 + intensity * 48 : ring === 1 ? 235 + intensity * 50 : 322 + intensity * 34;
  const x = CENTER_X + Math.cos(angle) * orbit * 1.34;
  const y = CENTER_Y + Math.sin(angle) * orbit * 0.52 - intensity * 24 + ring * 6;
  const z = Math.sin(angle) + intensity * 0.42 - ring * 0.08;
  return {
    ...cluster,
    intensity,
    x,
    y,
    r: 28 + intensity * 31 + Math.min(cluster.stockCount, 48) * 0.12,
    z,
    ring,
    rank
  };
}

function assignNodesToVisibleClusters(clusters: UniverseCluster[]) {
  const nodeCluster = new Map<string, string>();
  for (const cluster of clusters) {
    for (const node of cluster.nodes) {
      const current = nodeCluster.get(node.node_key);
      if (!current) {
        nodeCluster.set(node.node_key, cluster.key);
        continue;
      }
      const currentCluster = clusters.find((item) => item.key === current);
      if (!currentCluster || cluster.rank < currentCluster.rank) nodeCluster.set(node.node_key, cluster.key);
    }
  }
  return nodeCluster;
}

function buildRelations(clusters: UniverseCluster[], edges: ChainEdge[], nodeCluster: Map<string, string>) {
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
    const weight = edgeScore(edge);
    const current = relationMap.get(key);
    if (current) current.weight += weight;
    else relationMap.set(key, { key, source, target, weight });
  }

  const rawRelations = [...relationMap.values()].sort((left, right) => right.weight - left.weight);
  const keepCount = Math.max(4, Math.ceil(rawRelations.length * 0.05));
  const maxWeight = Math.max(...rawRelations.slice(0, keepCount).map((relation) => relation.weight), 1);
  return rawRelations.slice(0, keepCount).map((relation) => ({
    ...relation,
    weight: Math.min(relation.weight / maxWeight, 1)
  }));
}

function relationPath(source: UniverseCluster, target: UniverseCluster) {
  const midX = (source.x + target.x) / 2;
  const midY = (source.y + target.y) / 2;
  const bend = source.ring === target.ring ? -48 : 22;
  const controlX = CENTER_X + (midX - CENTER_X) * 0.28;
  const controlY = CENTER_Y + (midY - CENTER_Y) * 0.24 + bend;
  return `M ${source.x} ${source.y} Q ${controlX} ${controlY} ${target.x} ${target.y}`;
}

function gaugePath(radius: number) {
  return `M ${-radius * 0.76} ${radius * 0.3} A ${radius} ${radius} 0 1 1 ${radius * 0.72} ${radius * 0.38}`;
}

function nodeText(node: ChainNode) {
  return [node.node_key, node.name, node.layer, node.node_type, ...(node.industry_names ?? []), ...(node.tags ?? [])].join(" ").toLowerCase();
}

function safeKey(value: string) {
  return value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_\u4e00-\u9fa5]/g, "");
}

function edgeScore(edge: ChainEdge) {
  const heat = edge.heat ?? (edge.intensity ?? 0) * 100;
  return (edge.weight ?? 0.32) * 0.64 + heat / 100 * 0.36;
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
