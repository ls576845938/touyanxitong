"use client";

import { useMemo, useRef, useState } from "react";
import { ArrowUpRight, RotateCcw, Sparkles } from "lucide-react";
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

type Vec3 = {
  x: number;
  y: number;
  z: number;
};

type Rotation = {
  x: number;
  y: number;
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

type ClusterRelation = {
  key: string;
  source: string;
  target: string;
  weight: number;
};

type ProjectedRelation = {
  key: string;
  source: ProjectedCluster;
  target: ProjectedCluster;
  weight: number;
  depth: number;
};

type PointerState = {
  pointerId: number;
  startX: number;
  startY: number;
  origin: Rotation;
};

const WIDTH = 1180;
const HEIGHT = 620;
const CENTER_X = 560;
const CENTER_Y = 310;
const SPHERE_RADIUS = 226;
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
  const [rotation, setRotation] = useState<Rotation>({ x: -0.28, y: -0.62 });
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const pointerRef = useRef<PointerState | null>(null);
  const suppressClickRef = useRef(false);

  const model = useMemo(() => buildUniverse(nodes, edges, selectedNodeKey), [edges, nodes, selectedNodeKey]);
  const projection = useMemo(() => projectUniverse(model, rotation), [model, rotation]);
  const hovered = hoveredKey ? projection.clusters.find((cluster) => cluster.key === hoveredKey) : null;
  const featured = hovered ?? projection.clusters.find((cluster) => cluster.selected) ?? projection.clusters[0] ?? null;

  const resetRotation = () => setRotation({ x: -0.28, y: -0.62 });

  return (
    <section className="overflow-hidden rounded-lg border border-[#dbeafe] bg-white shadow-[0_22px_70px_rgba(15,23,42,0.08)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e0f2fe] bg-white px-5 py-4">
        <div>
          <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
            <Sparkles size={18} className="text-orange-600" />
            产业宇宙总览图
          </div>
          <div className="mt-1 text-xs text-slate-500">按住球面拖动旋转，点击产业簇进入地铁链路。</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <DataPill label="产业簇" value={model.clusters.length} />
          <DataPill label="强关系" value={model.relations.length} />
          <DataPill label="覆盖节点" value={model.coveredNodeCount} />
          <button
            type="button"
            onClick={resetRotation}
            className="inline-flex h-9 items-center gap-2 rounded-full border border-[#dbeafe] bg-[#f8fbff] px-3 text-xs font-semibold text-slate-700 hover:border-orange-300"
          >
            <RotateCcw size={14} />
            复位
          </button>
        </div>
      </div>

      <div className="grid gap-4 bg-[#f8fbff] p-4 xl:grid-cols-[minmax(0,1fr)_292px]">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-[620px] w-full select-none rounded-lg border border-[#dbeafe] bg-white"
          role="img"
          aria-label="可旋转 3D 产业宇宙总览图"
          onPointerDown={(event) => {
            if (event.pointerType === "mouse" && event.button !== 0) return;
            pointerRef.current = {
              pointerId: event.pointerId,
              startX: event.clientX,
              startY: event.clientY,
              origin: rotation
            };
            suppressClickRef.current = false;
            setDragging(true);
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const pointer = pointerRef.current;
            if (!pointer || pointer.pointerId !== event.pointerId) return;
            const dx = event.clientX - pointer.startX;
            const dy = event.clientY - pointer.startY;
            if (Math.abs(dx) + Math.abs(dy) > 4) suppressClickRef.current = true;
            setRotation({
              x: clamp(pointer.origin.x + dy * 0.006, -1.16, 1.16),
              y: pointer.origin.y + dx * 0.008
            });
          }}
          onPointerUp={(event) => {
            if (pointerRef.current?.pointerId === event.pointerId) pointerRef.current = null;
            setDragging(false);
          }}
          onPointerCancel={() => {
            pointerRef.current = null;
            setDragging(false);
          }}
          style={{ cursor: dragging ? "grabbing" : "grab", touchAction: "none" }}
        >
          <defs>
            <radialGradient id="industry-sphere-bg" cx="48%" cy="36%" r="70%">
              <stop offset="0" stopColor="#ffffff" />
              <stop offset="0.58" stopColor="#f8fbff" />
              <stop offset="1" stopColor="#e8f3ff" />
            </radialGradient>
            <radialGradient id="industry-sphere-gloss" cx="35%" cy="26%" r="40%">
              <stop offset="0" stopColor="#ffffff" stopOpacity="0.82" />
              <stop offset="0.62" stopColor="#ffffff" stopOpacity="0.16" />
              <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
            </radialGradient>
            <clipPath id="industry-universe-clip">
              <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS + 8} />
            </clipPath>
            <filter id="industry-universe-glow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="10" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="industry-universe-shadow" x="-40%" y="-40%" width="180%" height="190%">
              <feDropShadow dx="0" dy="18" stdDeviation="16" floodColor="#0f172a" floodOpacity="0.14" />
            </filter>
          </defs>

          <rect width={WIDTH} height={HEIGHT} fill="#fbfdff" />
          <ellipse cx={CENTER_X} cy={CENTER_Y + SPHERE_RADIUS + 32} rx={SPHERE_RADIUS * 0.96} ry="31" fill="#bfdbfe" opacity="0.26" />
          <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS} fill="url(#industry-sphere-bg)" stroke="#c7ddff" filter="url(#industry-universe-shadow)" />

          <g clipPath="url(#industry-universe-clip)">
            {[-58, -28, 0, 28, 58].map((offset) => (
              <ellipse
                key={`lat-${offset}`}
                cx={CENTER_X}
                cy={CENTER_Y + offset * 0.9}
                rx={SPHERE_RADIUS * Math.cos(Math.abs(offset) / 90)}
                ry={Math.max(12, SPHERE_RADIUS * 0.12 * Math.cos(Math.abs(offset) / 100))}
                fill="none"
                stroke="#bcd7ff"
                strokeWidth="1"
                strokeDasharray="4 10"
                opacity="0.36"
              />
            ))}
            {[-60, -30, 0, 30, 60].map((angle) => (
              <ellipse
                key={`lng-${angle}`}
                cx={CENTER_X}
                cy={CENTER_Y}
                rx={SPHERE_RADIUS * 0.18}
                ry={SPHERE_RADIUS}
                fill="none"
                stroke="#d7e7ff"
                strokeWidth="1"
                strokeDasharray="4 12"
                opacity="0.34"
                transform={`rotate(${angle + rotation.y * 18} ${CENTER_X} ${CENTER_Y})`}
              />
            ))}

            <g fill="none">
              {projection.relations.map((relation) => {
                const active = relation.source.key === hoveredKey || relation.target.key === hoveredKey || relation.source.selected || relation.target.selected;
                return (
                  <path
                    key={relation.key}
                    d={projectedRelationPath(relation.source, relation.target)}
                    stroke={active ? "#f97316" : "#60a5fa"}
                    strokeWidth={active ? 1.9 + relation.weight * 2.1 : 0.8 + relation.weight * 1.4}
                    strokeOpacity={active ? 0.58 : 0.15 + relation.weight * 0.12}
                    strokeLinecap="round"
                  />
                );
              })}
            </g>

            {projection.clusters.map((cluster) => {
              const active = cluster.selected || cluster.key === hoveredKey;
              const labelVisible = active || cluster.rank < 7 || cluster.depth > 0.38;
              return (
                <g
                  key={cluster.key}
                  role="button"
                  tabIndex={0}
                  transform={`translate(${cluster.sx} ${cluster.sy}) scale(${active ? cluster.scale * 1.08 : cluster.scale})`}
                  className="cursor-pointer outline-none"
                  opacity={active ? 1 : cluster.opacity}
                  onMouseEnter={() => setHoveredKey(cluster.key)}
                  onMouseLeave={() => setHoveredKey(null)}
                  onFocus={() => setHoveredKey(cluster.key)}
                  onBlur={() => setHoveredKey(null)}
                  onClick={() => {
                    if (!suppressClickRef.current && cluster.hottestNode) onOpenChain(cluster.hottestNode.node_key);
                  }}
                  onKeyDown={(event) => {
                    if ((event.key === "Enter" || event.key === " ") && cluster.hottestNode) {
                      event.preventDefault();
                      onOpenChain(cluster.hottestNode.node_key);
                    }
                  }}
                >
                  <circle r={cluster.r + 18} fill={cluster.color} opacity={active ? 0.28 : 0.1 + cluster.intensity * 0.12} filter="url(#industry-universe-glow)" />
                  <circle r={cluster.r} fill="#ffffff" stroke={active ? "#0f172a" : cluster.color} strokeWidth={active ? 2.6 : 1.4} />
                  <circle r={Math.max(10, cluster.r * 0.32)} fill={warmColor(cluster.intensity)} />
                  <text y="4" textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="900">
                    {cluster.rank + 1}
                  </text>
                  {labelVisible ? (
                    <g transform={`translate(${-Math.max(50, cluster.shortName.length * 7.4)} ${cluster.r + 11})`}>
                      <rect width={Math.max(100, cluster.shortName.length * 14.8)} height="30" rx="9" fill="#ffffff" fillOpacity="0.96" stroke="#dbeafe" />
                      <text x={Math.max(50, cluster.shortName.length * 7.4)} y="13" textAnchor="middle" fill="#0f172a" fontSize="11.5" fontWeight="850">
                        {cluster.shortName}
                      </text>
                      <text x={Math.max(50, cluster.shortName.length * 7.4)} y="25" textAnchor="middle" fill="#ea580c" fontSize="9.5" fontWeight="800">
                        {cluster.heat.toFixed(1)}
                      </text>
                    </g>
                  ) : null}
                  <title>{`${cluster.name}｜热度 ${cluster.heat.toFixed(1)}｜拖动旋转，点击进入链路`}</title>
                </g>
              );
            })}
          </g>

          <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS} fill="url(#industry-sphere-gloss)" pointerEvents="none" />
          <text x={CENTER_X} y={CENTER_Y + SPHERE_RADIUS + 74} textAnchor="middle" fill="#64748b" fontSize="12" fontWeight="700">
            鼠标按住拖动 / 手机触屏拖动旋转
          </text>
        </svg>

        <aside className="space-y-3">
          <section className="rounded-lg border border-[#dbeafe] bg-white p-4 shadow-[0_12px_32px_rgba(15,23,42,0.05)]">
            <div className="text-sm font-semibold text-slate-950">发热产业簇</div>
            <div className="mt-3 space-y-2">
              {projection.clusters.slice(0, 8).map((cluster) => (
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
    .sort((left, right) => right.heat - left.heat || right.priority - left.priority)
    .slice(0, MAX_VISIBLE_CLUSTERS);

  const maxHeat = Math.max(...rawClusters.map((cluster) => cluster.heat), 1);
  const clusters = rawClusters.map((cluster, index) => placeCluster(cluster, index, rawClusters.length, maxHeat));
  const nodeCluster = assignNodesToVisibleClusters(clusters);
  const relations = buildRelations(clusters, edges, nodeCluster);

  return {
    clusters,
    relations,
    coveredNodeCount: new Set(clusters.flatMap((cluster) => cluster.nodes.map((node) => node.node_key))).size
  };
}

function projectUniverse(model: ReturnType<typeof buildUniverse>, rotation: Rotation) {
  const clusters = model.clusters
    .map((cluster) => projectCluster(cluster, rotation))
    .sort((left, right) => left.depth - right.depth);
  const clusterMap = new Map(clusters.map((cluster) => [cluster.key, cluster]));
  const relations = model.relations
    .map((relation) => {
      const source = clusterMap.get(relation.source);
      const target = clusterMap.get(relation.target);
      if (!source || !target) return null;
      return {
        key: relation.key,
        source,
        target,
        weight: relation.weight,
        depth: (source.depth + target.depth) / 2
      };
    })
    .filter((relation): relation is ProjectedRelation => Boolean(relation))
    .sort((left, right) => left.depth - right.depth);
  return { clusters, relations };
}

function projectCluster(cluster: UniverseCluster, rotation: Rotation): ProjectedCluster {
  const point = rotatePoint(cluster.base, rotation);
  const depth = (point.z + SPHERE_RADIUS) / (SPHERE_RADIUS * 2);
  const perspective = 0.72 + depth * 0.48;
  return {
    ...cluster,
    sx: CENTER_X + point.x * perspective,
    sy: CENTER_Y + point.y * perspective,
    depth,
    scale: 0.72 + depth * 0.48,
    opacity: 0.34 + depth * 0.66
  };
}

function rotatePoint(point: Vec3, rotation: Rotation): Vec3 {
  const cosY = Math.cos(rotation.y);
  const sinY = Math.sin(rotation.y);
  const x1 = point.x * cosY + point.z * sinY;
  const z1 = -point.x * sinY + point.z * cosY;
  const cosX = Math.cos(rotation.x);
  const sinX = Math.sin(rotation.x);
  return {
    x: x1,
    y: point.y * cosX - z1 * sinX,
    z: point.y * sinX + z1 * cosX
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
    base: { x: 0, y: 0, z: 0 },
    r: 0,
    selected: Boolean(selectedNodeKey && clusterNodes.some((node) => node.node_key === selectedNodeKey)),
    rank: 0,
    priority: rule.priority
  };
}

function placeCluster(cluster: ReturnType<typeof clusterFromNodes>, index: number, total: number, maxHeat: number): UniverseCluster {
  const intensity = Math.min(Math.max(cluster.heat / maxHeat, 0), 1);
  const phi = Math.acos(1 - 2 * ((index + 0.5) / Math.max(total, 1)));
  const theta = index * Math.PI * (3 - Math.sqrt(5));
  const radius = SPHERE_RADIUS * (0.72 + intensity * 0.2);
  return {
    ...cluster,
    intensity,
    base: {
      x: Math.cos(theta) * Math.sin(phi) * radius,
      y: Math.sin(theta) * Math.sin(phi) * radius,
      z: Math.cos(phi) * radius
    },
    r: 17 + intensity * 18 + Math.min(cluster.stockCount, 48) * 0.08,
    rank: index
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
  const visibleKeys = new Set(clusters.map((cluster) => cluster.key));
  const relationMap = new Map<string, ClusterRelation>();

  for (const edge of edges) {
    const source = nodeCluster.get(edge.source);
    const target = nodeCluster.get(edge.target);
    if (!source || !target || source === target || !visibleKeys.has(source) || !visibleKeys.has(target)) continue;
    const key = `${source}->${target}`;
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

function projectedRelationPath(source: ProjectedCluster, target: ProjectedCluster) {
  const controlX = CENTER_X + ((source.sx + target.sx) / 2 - CENTER_X) * 0.24;
  const controlY = CENTER_Y + ((source.sy + target.sy) / 2 - CENTER_Y) * 0.24;
  return `M ${source.sx} ${source.sy} Q ${controlX} ${controlY} ${target.sx} ${target.sy}`;
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

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
