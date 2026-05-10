"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Building2,
  CalendarRange,
  CircleGauge,
  Flame,
  Globe2,
  Layers3,
  Network,
  Search
} from "lucide-react";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type ChainEdge, type ChainGeo, type ChainNode, type ChainNodeDetail, type ChainOverview, type ChainRegion, type ChainTimelinePoint } from "@/lib/api";

type ChainBlueprint = {
  key: string;
  name: string;
  shortName: string;
  color: string;
  glow: string;
  nodeKeys: string[];
};

type ChainSummary = ChainBlueprint & {
  heat: number;
  intensity: number;
  nodes: ChainNode[];
};

type MetroStation = {
  node: ChainNode;
  chain: ChainSummary;
  stageIndex: number;
  order: number;
  x: number;
  y: number;
  r: number;
  heat: number;
  intensity: number;
};

const STAGES = [
  "资源/能源",
  "基础材料",
  "核心零部件",
  "设备系统",
  "终端产品",
  "渠道服务",
  "回收再生产"
];

const CHAIN_BLUEPRINTS: ChainBlueprint[] = [
  {
    key: "ai_compute_chain",
    name: "AI 算力链",
    shortName: "AI算力",
    color: "#f97316",
    glow: "#fed7aa",
    nodeKeys: ["power_grid", "copper", "semiconductor_materials", "power_semiconductor", "hbm_memory", "gpu_advanced_package", "ai_servers", "software_cloud", "ai_compute"]
  },
  {
    key: "semiconductor_chain",
    name: "半导体底座链",
    shortName: "半导体",
    color: "#ef4444",
    glow: "#fecaca",
    nodeKeys: ["specialty_chemicals", "semiconductor_materials", "semiconductor_equipment", "integrated_circuits", "hbm_memory", "enterprise_ssd", "optical_modules", "ai_servers"]
  },
  {
    key: "new_energy_vehicle_chain",
    name: "新能源车链",
    shortName: "新能源车",
    color: "#22c55e",
    glow: "#bbf7d0",
    nodeKeys: ["lithium_ore", "nickel_ore", "battery_materials", "battery_cells", "power_semiconductor", "charging_swap", "new_energy_vehicle", "used_car_circulation", "battery_recycling"]
  },
  {
    key: "power_grid_chain",
    name: "电力电网链",
    shortName: "电力电网",
    color: "#0ea5e9",
    glow: "#bae6fd",
    nodeKeys: ["coal", "natural_gas", "solar_power", "wind_power", "power_grid", "energy_storage_system", "distributed_energy", "industrial_automation"]
  },
  {
    key: "robotics_chain",
    name: "机器人链",
    shortName: "机器人",
    color: "#8b5cf6",
    glow: "#ddd6fe",
    nodeKeys: ["rare_earth_ore", "steel", "industrial_bearings", "sensors", "machine_vision", "robotics_system", "industrial_robot", "software_cloud"]
  },
  {
    key: "consumer_electronics_chain",
    name: "消费电子链",
    shortName: "消费电子",
    color: "#14b8a6",
    glow: "#99f6e4",
    nodeKeys: ["petrochemicals", "display_glass", "pcb_fpc", "mlcc", "high_speed_connectors", "smart_devices", "ecommerce_retail", "electronics_recycling"]
  }
];

export default function IndustryChainCockpitPage() {
  const [overview, setOverview] = useState<ChainOverview | null>(null);
  const [selectedChainKey, setSelectedChainKey] = useState(CHAIN_BLUEPRINTS[0].key);
  const [selectedNodeKey, setSelectedNodeKey] = useState("power_grid");
  const [detail, setDetail] = useState<ChainNodeDetail | null>(null);
  const [geo, setGeo] = useState<ChainGeo | null>(null);
  const [timeline, setTimeline] = useState<ChainTimelinePoint[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api.chainOverview({ market: "ALL" })
      .then((payload) => {
        if (cancelled) return;
        setOverview(payload);
        if (!payload.nodes.some((node) => node.node_key === selectedNodeKey)) {
          setSelectedNodeKey(payload.default_focus_node_key ?? payload.nodes[0]?.node_key ?? "power_grid");
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(`产业链驾驶舱读取失败：${err.message}`);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedNodeKey) return;
    let cancelled = false;
    setDetailLoading(true);
    Promise.all([
      api.chainNode(selectedNodeKey, { market: "ALL" }),
      api.chainGeo({ nodeKey: selectedNodeKey, market: "ALL" }),
      api.chainTimeline({ nodeKey: selectedNodeKey, limit: 18 })
    ])
      .then(([nodeDetail, nodeGeo, nodeTimeline]) => {
        if (cancelled) return;
        setDetail(nodeDetail);
        setGeo(nodeGeo);
        setTimeline(nodeTimeline.timeline ?? []);
      })
      .catch(() => {
        if (!cancelled) {
          setDetail(null);
          setGeo(null);
          setTimeline([]);
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedNodeKey]);

  const nodeMap = useMemo(() => new Map((overview?.nodes ?? []).map((node) => [node.node_key, node])), [overview]);
  const chainSummaries = useMemo(() => buildChainSummaries(nodeMap), [nodeMap]);
  const selectedChain = chainSummaries.find((chain) => chain.key === selectedChainKey) ?? chainSummaries[0];
  const selectedNode = detail?.node ?? nodeMap.get(selectedNodeKey) ?? null;
  const visibleTopNodes = useMemo(() => {
    const lowered = query.trim().toLowerCase();
    return [...(overview?.nodes ?? [])]
      .filter((node) => !lowered || [node.name, node.node_key, node.layer, node.node_type, ...(node.industry_names ?? []), ...(node.tags ?? [])].join(" ").toLowerCase().includes(lowered))
      .sort((left, right) => nodeHeat(right) - nodeHeat(left))
      .slice(0, 12);
  }, [overview, query]);

  const selectStation = (nodeKey: string, chainKey?: string) => {
    if (chainKey) setSelectedChainKey(chainKey);
    setSelectedNodeKey(nodeKey);
  };

  const selectChain = (chainKey: string) => {
    setSelectedChainKey(chainKey);
    const chain = chainSummaries.find((item) => item.key === chainKey);
    const hottestNode = [...(chain?.nodes ?? [])].sort((left, right) => nodeHeat(right) - nodeHeat(left))[0];
    if (hottestNode) setSelectedNodeKey(hottestNode.node_key);
  };

  if (loading) return <div className="page-shell"><LoadingState label="正在加载产业链驾驶舱副本" /></div>;
  if (error) return <div className="page-shell"><ErrorState message={error} /></div>;
  if (!overview || !selectedChain) return <div className="page-shell"><ErrorState message="产业链驾驶舱数据为空" /></div>;

  return (
    <div className="page-shell space-y-5 bg-white">
      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="label">Industry Chain Cockpit Copy</div>
            <h1 className="mt-2 text-2xl font-semibold text-slate-950">产业链驾驶舱副本</h1>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/industry/chain" className="inline-flex h-10 items-center gap-2 rounded-md border border-[#f2dfd2] px-3 text-sm hover:border-orange-300">
              <Layers3 size={16} />
              原产业链地图
            </Link>
            <Link href="/research/hot-terms" className="inline-flex h-10 items-center gap-2 rounded-md border border-[#f2dfd2] px-3 text-sm hover:border-orange-300">
              <Flame size={16} />
              热词雷达
            </Link>
          </div>
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-[1fr_360px]">
          <HeatUniverse chains={chainSummaries} selectedChainKey={selectedChain.key} onSelectChain={selectChain} />
          <TopHeatBoard nodes={visibleTopNodes} selectedNodeKey={selectedNodeKey} query={query} onQueryChange={setQuery} onSelectNode={setSelectedNodeKey} />
        </div>
      </section>

      <section className="grid items-start gap-4 xl:grid-cols-[238px_minmax(0,1fr)_356px]">
        <ChainSelector chains={chainSummaries} selectedChainKey={selectedChain.key} onSelect={selectChain} />
        <MetroChainMap
          chainSummaries={chainSummaries}
          selectedChain={selectedChain}
          selectedNodeKey={selectedNodeKey}
          edges={overview.edges}
          onSelectStation={selectStation}
        />
        <NodeBattleCard
          node={selectedNode}
          detail={detail}
          detailLoading={detailLoading}
          selectedChain={selectedChain}
          onSelectNode={setSelectedNodeKey}
        />
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <TimeMigrationPanel chain={selectedChain} timeline={timeline} selectedNode={selectedNode} />
        <WorldDistributionPanel geo={geo} fallbackRegions={overview.regions ?? []} selectedNode={selectedNode} />
      </section>
    </div>
  );
}

function HeatUniverse({
  chains,
  selectedChainKey,
  onSelectChain
}: {
  chains: ChainSummary[];
  selectedChainKey: string;
  onSelectChain: (chainKey: string) => void;
}) {
  const width = 820;
  const height = 360;
  const centerX = width / 2;
  const centerY = height / 2 + 10;
  const positions = chains.map((chain, index) => {
    const angle = (-88 + index * (360 / chains.length)) * Math.PI / 180;
    const radius = 86 + chain.intensity * 78;
    return {
      chain,
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius,
      r: 34 + chain.intensity * 34
    };
  });

  return (
    <div className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-[#fffaf5]">
      <div className="flex items-center justify-between border-b border-[#f7e9de] px-5 py-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Network size={16} className="text-orange-600" />
          产业热力总览
        </div>
        <div className="mono text-xs text-slate-500">只保留产业簇</div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[360px] w-full" role="img" aria-label="产业宇宙总览图">
        <defs>
          <radialGradient id="universe-bg" cx="50%" cy="50%" r="70%">
            <stop offset="0" stopColor="#fff7ed" />
            <stop offset="0.62" stopColor="#ffffff" />
            <stop offset="1" stopColor="#fffaf5" />
          </radialGradient>
          <filter id="universe-glow" x="-70%" y="-70%" width="240%" height="240%">
            <feGaussianBlur stdDeviation="13" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect width={width} height={height} fill="url(#universe-bg)" />
        {[118, 178, 236].map((radius) => (
          <circle key={radius} cx={centerX} cy={centerY} r={radius} fill="none" stroke="#f6dfcf" strokeWidth="1" strokeDasharray="4 10" />
        ))}
        {positions.map((item, index) => {
          const active = item.chain.key === selectedChainKey;
          return (
            <g
              key={item.chain.key}
              role="button"
              tabIndex={0}
              onClick={() => onSelectChain(item.chain.key)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelectChain(item.chain.key);
              }}
              className="cursor-pointer outline-none"
            >
              <path
                d={`M ${centerX} ${centerY} Q ${(centerX + item.x) / 2} ${(centerY + item.y) / 2 - 34 + index * 3} ${item.x} ${item.y}`}
                fill="none"
                stroke={item.chain.color}
                strokeWidth={active ? 2.4 : 1.2}
                strokeOpacity={active ? 0.46 : 0.15}
              />
              <circle cx={item.x} cy={item.y} r={item.r + 16} fill={item.chain.color} opacity={active ? 0.2 : 0.1} filter="url(#universe-glow)" />
              <circle cx={item.x} cy={item.y} r={item.r} fill="#ffffff" stroke={item.chain.color} strokeWidth={active ? 2.8 : 1.4} />
              <circle cx={item.x} cy={item.y} r={Math.max(16, item.r * 0.48)} fill={heatColor(item.chain.intensity)} opacity="0.92" />
              <text x={item.x} y={item.y + item.r + 24} textAnchor="middle" fill="#111827" fontSize="13" fontWeight="850">
                {item.chain.shortName}
              </text>
              <text x={item.x} y={item.y + item.r + 42} textAnchor="middle" fill="#9a3412" fontSize="11.5" fontWeight="750">
                {item.chain.heat.toFixed(1)}
              </text>
            </g>
          );
        })}
        <g transform={`translate(${centerX - 58} ${centerY - 26})`}>
          <rect width="116" height="52" rx="18" fill="#ffffff" stroke="#fed7aa" />
          <text x="58" y="22" textAnchor="middle" fill="#111827" fontSize="13" fontWeight="850">
            全市场
          </text>
          <text x="58" y="40" textAnchor="middle" fill="#9a3412" fontSize="11.5" fontWeight="750">
            产业簇热度
          </text>
        </g>
      </svg>
    </div>
  );
}

function TopHeatBoard({
  nodes,
  selectedNodeKey,
  query,
  onQueryChange,
  onSelectNode
}: {
  nodes: ChainNode[];
  selectedNodeKey: string | null;
  query: string;
  onQueryChange: (value: string) => void;
  onSelectNode: (nodeKey: string) => void;
}) {
  return (
    <div className="rounded-lg border border-[#f2dfd2] bg-white p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Flame size={16} className="text-orange-600" />
        全市场热度榜
      </div>
      <div className="relative mt-4">
        <Search size={15} className="pointer-events-none absolute left-3 top-3 text-slate-400" />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="搜索节点"
          className="h-10 w-full rounded-md border border-[#f2dfd2] bg-white pl-9 pr-3 text-sm outline-none focus:border-orange-400"
        />
      </div>
      <div className="mt-3 space-y-2">
        {nodes.map((node, index) => {
          const active = node.node_key === selectedNodeKey;
          const intensity = normalizeHeat(nodeHeat(node));
          return (
            <button
              key={node.node_key}
              type="button"
              onClick={() => onSelectNode(node.node_key)}
              className={`w-full rounded-md border p-2.5 text-left transition ${active ? "border-orange-500 bg-orange-50" : "border-[#f2dfd2] bg-white hover:border-orange-300"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="mono w-5 text-xs text-slate-400">{index + 1}</span>
                  <span className="truncate text-sm font-semibold text-slate-900">{node.name}</span>
                </div>
                <span className="mono text-xs font-semibold" style={{ color: heatColor(intensity) }}>{nodeHeat(node).toFixed(1)}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#ffedd5]">
                <div className="h-full rounded-full" style={{ width: `${Math.max(intensity * 100, 8)}%`, backgroundColor: heatColor(intensity) }} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ChainSelector({
  chains,
  selectedChainKey,
  onSelect
}: {
  chains: ChainSummary[];
  selectedChainKey: string;
  onSelect: (chainKey: string) => void;
}) {
  return (
    <aside className="rounded-lg border border-[#f2dfd2] bg-white p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Layers3 size={16} className="text-orange-600" />
        产业链选择器
      </div>
      <div className="space-y-2">
        {chains.map((chain) => {
          const active = chain.key === selectedChainKey;
          return (
            <button
              key={chain.key}
              type="button"
              onClick={() => onSelect(chain.key)}
              className={`w-full rounded-md border p-3 text-left transition ${active ? "border-orange-500 bg-orange-50" : "border-[#f2dfd2] bg-white hover:border-orange-300"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full" style={{ backgroundColor: chain.color }} />
                  <span className="text-sm font-semibold text-slate-900">{chain.shortName}</span>
                </div>
                <span className="mono text-xs font-semibold text-orange-700">{chain.heat.toFixed(1)}</span>
              </div>
              <div className="mt-2 text-xs text-slate-500">{chain.nodes.length} 个节点</div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function MetroChainMap({
  chainSummaries,
  selectedChain,
  selectedNodeKey,
  edges,
  onSelectStation
}: {
  chainSummaries: ChainSummary[];
  selectedChain: ChainSummary;
  selectedNodeKey: string | null;
  edges: ChainEdge[];
  onSelectStation: (nodeKey: string, chainKey?: string) => void;
}) {
  const width = 1180;
  const height = 620;
  const stageX = (stageIndex: number) => 92 + stageIndex * 166;
  const laneY = (index: number) => 132 + index * 72;
  const stations = chainSummaries.flatMap((chain, chainIndex) => {
    return chain.nodes.map<MetroStation>((node, order) => {
      const stageIndexValue = stageIndex(node);
      const sameStageOffset = chain.nodes.slice(0, order).filter((item) => stageIndex(item) === stageIndexValue).length;
      const heat = nodeHeat(node);
      const intensity = normalizeHeat(heat);
      return {
        node,
        chain,
        stageIndex: stageIndexValue,
        order,
        x: stageX(stageIndexValue) + sameStageOffset * 18,
        y: laneY(chainIndex) + (sameStageOffset % 2) * 18,
        r: 8 + intensity * 9 + Math.min(node.stock_count ?? 0, 8) * 0.4,
        heat,
        intensity
      };
    });
  });
  const stationKey = (chainKey: string, nodeKey: string) => `${chainKey}:${nodeKey}`;
  const stationMap = new Map(stations.map((station) => [stationKey(station.chain.key, station.node.node_key), station]));
  const edgeSet = new Set(edges.map((edge) => `${edge.source}->${edge.target}`));

  return (
    <section className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#f7e9de] px-5 py-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Activity size={16} className="text-orange-600" />
          产业链主地图
        </div>
        <div className="mono text-xs text-slate-500">{selectedChain.name}</div>
      </div>
      <div className="overflow-x-auto bg-[#fffdfa]">
        <svg viewBox={`0 0 ${width} ${height}`} className="block min-w-[980px]" style={{ height: 620 }} role="img" aria-label="产业链地铁图">
          <defs>
            <filter id="metro-shadow" x="-30%" y="-30%" width="170%" height="180%">
              <feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#7c2d12" floodOpacity="0.09" />
            </filter>
          </defs>
          <rect width={width} height={height} fill="#fffdfa" />
          {STAGES.map((stage, index) => (
            <g key={stage}>
              <rect x={stageX(index) - 54} y="34" width="116" height={height - 72} rx="18" fill={index % 2 === 0 ? "#ffffff" : "#fff7ed"} stroke="#f5dfcf" />
              <text x={stageX(index) + 4} y="62" textAnchor="middle" fill="#111827" fontSize="13" fontWeight="850">{stage}</text>
            </g>
          ))}
          {chainSummaries.map((chain) => {
            const active = chain.key === selectedChain.key;
            const lineStations = chain.nodes
              .map((node) => stationMap.get(stationKey(chain.key, node.node_key)))
              .filter((station): station is MetroStation => Boolean(station));
            return (
              <g key={chain.key} opacity={active ? 1 : 0.24}>
                {lineStations.slice(0, -1).map((station, index) => {
                  const next = lineStations[index + 1];
                  const hasEdge = edgeSet.has(`${station.node.node_key}->${next.node.node_key}`);
                  return (
                    <path
                      key={`${chain.key}-${station.node.node_key}-${next.node.node_key}`}
                      d={metroPath(station, next)}
                      fill="none"
                      stroke={chain.color}
                      strokeWidth={active ? (hasEdge ? 7 : 4.6) : 3.2}
                      strokeOpacity={hasEdge ? 0.74 : 0.34}
                      strokeLinecap="round"
                    />
                  );
                })}
                <text x="34" y={lineStations[0]?.y ?? 0} fill={chain.color} fontSize="12" fontWeight="850">{chain.shortName}</text>
              </g>
            );
          })}
          {stations.map((station) => {
            const activeChain = station.chain.key === selectedChain.key;
            const activeNode = station.node.node_key === selectedNodeKey;
            const labelVisible = activeChain || activeNode || station.intensity > 0.62;
            return (
              <g
                key={`${station.chain.key}-${station.node.node_key}`}
                role="button"
                tabIndex={0}
                onClick={() => onSelectStation(station.node.node_key, station.chain.key)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") onSelectStation(station.node.node_key, station.chain.key);
                }}
                className="cursor-pointer outline-none"
                opacity={activeChain ? 1 : 0.42}
              >
                <circle cx={station.x} cy={station.y} r={station.r + 8} fill={station.chain.glow} opacity={activeNode ? 0.8 : 0.32} />
                <circle cx={station.x} cy={station.y} r={station.r} fill={heatColor(station.intensity)} stroke={activeNode ? "#111827" : "#ffffff"} strokeWidth={activeNode ? 3 : 2} filter="url(#metro-shadow)" />
                <circle cx={station.x - station.r * 0.25} cy={station.y - station.r * 0.25} r={Math.max(2.4, station.r * 0.18)} fill="#ffffff" opacity="0.72" />
                {labelVisible ? (
                  <g transform={`translate(${station.x - 52} ${station.y + station.r + 10})`}>
                    <rect width="104" height="25" rx="8" fill="#ffffff" fillOpacity="0.96" stroke="#f2dfd2" />
                    <text x="52" y="17" textAnchor="middle" fill="#111827" fontSize="11.5" fontWeight="750">{clipLabel(station.node.name, 8)}</text>
                  </g>
                ) : null}
                <title>{`${station.chain.name} / ${station.node.name} / 热度 ${station.heat.toFixed(1)}`}</title>
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}

function NodeBattleCard({
  node,
  detail,
  detailLoading,
  selectedChain,
  onSelectNode
}: {
  node: ChainNode | null;
  detail: ChainNodeDetail | null;
  detailLoading: boolean;
  selectedChain: ChainSummary;
  onSelectNode: (nodeKey: string) => void;
}) {
  const heat = node ? nodeHeat(node) : 0;
  const intensity = normalizeHeat(heat);
  return (
    <aside className="space-y-4">
      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="label">Node Battle Map</div>
            <div className="mt-2 text-xl font-semibold text-slate-950">{node?.name ?? "--"}</div>
            <div className="mt-1 text-xs text-slate-500">{node?.layer ?? "--"} / {selectedChain.shortName}</div>
          </div>
          <div className="rounded-full px-3 py-2 text-xs font-semibold text-white" style={{ backgroundColor: heatColor(intensity) }}>
            {heat.toFixed(1)}
          </div>
        </div>
        {node?.description ? <p className="mt-4 text-sm leading-6 text-slate-600">{node.description}</p> : null}
        <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
          <MiniMetric label="动量" value={node?.momentum?.toFixed(1) ?? "--"} />
          <MiniMetric label="股票" value={node?.stock_count ?? "--"} />
          <MiniMetric label="强度" value={`${Math.round(intensity * 100)}%`} />
        </div>
      </section>

      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <CircleGauge size={16} className="text-orange-600" />
          单节点作战地图
        </div>
        {detailLoading ? <LoadingState label="正在加载节点作战图" /> : null}
        {!detailLoading ? (
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <NodeStack title="上游输入" nodes={detail?.upstream ?? []} onSelectNode={onSelectNode} tone="#f59e0b" />
            <div className="flex flex-col items-center gap-2">
              <ArrowRight size={18} className="text-orange-500" />
              <div className="rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-center text-xs font-semibold text-orange-800">{node?.name ?? "--"}</div>
              <ArrowRight size={18} className="text-orange-500" />
            </div>
            <NodeStack title="下游扩散" nodes={detail?.downstream ?? []} onSelectNode={onSelectNode} tone="#ef4444" />
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Building2 size={16} className="text-orange-600" />
          龙头企业
        </div>
        <div className="space-y-2">
          {(detail?.leader_stocks ?? []).slice(0, 5).map((stock) => (
            <Link key={stock.code} href={`/stocks/${encodeURIComponent(stock.code)}?from=/industry/chain-cockpit`} className="block rounded-md border border-[#f2dfd2] bg-[#fffaf5] p-3 hover:border-orange-300">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-medium text-slate-900">{stock.name}</div>
                  <div className="mt-1 text-xs text-slate-500">{stock.code} / {stock.market || "--"}</div>
                </div>
                <div className="mono text-sm font-semibold text-orange-700">{formatNumber(stock.final_score)}</div>
              </div>
            </Link>
          ))}
          {!(detail?.leader_stocks ?? []).length ? <EmptyHint label="暂无龙头企业" /> : null}
        </div>
      </section>
    </aside>
  );
}

function NodeStack({ title, nodes, onSelectNode, tone }: { title: string; nodes: ChainNode[]; onSelectNode: (nodeKey: string) => void; tone: string }) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold text-slate-500">{title}</div>
      <div className="space-y-2">
        {nodes.slice(0, 6).map((node) => (
          <button key={node.node_key} type="button" onClick={() => onSelectNode(node.node_key)} className="w-full rounded-md border border-[#f2dfd2] bg-white px-3 py-2 text-left text-xs hover:border-orange-300">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-semibold text-slate-800">{node.name}</span>
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: tone }} />
            </div>
          </button>
        ))}
        {!nodes.length ? <div className="rounded-md border border-dashed border-[#f2dfd2] px-3 py-2 text-xs text-slate-500">暂无节点</div> : null}
      </div>
    </div>
  );
}

function TimeMigrationPanel({ chain, timeline, selectedNode }: { chain: ChainSummary; timeline: ChainTimelinePoint[]; selectedNode: ChainNode | null }) {
  const stageHeat = STAGES.map((stage, index) => {
    const nodes = chain.nodes.filter((node) => stageIndex(node) === index);
    const heat = nodes.length ? nodes.reduce((sum, node) => sum + nodeHeat(node), 0) / nodes.length : 0;
    return { stage, heat, intensity: normalizeHeat(heat), nodes };
  });
  const timelineValues = timeline.map(pointHeat);
  const maxTimeline = Math.max(...timelineValues, 1);

  return (
    <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
          <CalendarRange size={18} className="text-orange-600" />
          时间迁移图
        </div>
        <div className="text-xs text-slate-500">{selectedNode?.name ?? chain.shortName}</div>
      </div>
      <div className="grid gap-2 md:grid-cols-7">
        {stageHeat.map((item, index) => (
          <div key={item.stage} className="rounded-lg border border-[#f2dfd2] bg-[#fffaf5] p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold text-slate-700">{item.stage}</div>
              <div className="mono text-xs text-orange-700">{item.heat.toFixed(1)}</div>
            </div>
            <div className="mt-3 h-20 rounded-md bg-white p-2">
              <div className="flex h-full items-end justify-center">
                <div className="w-7 rounded-full" style={{ height: `${Math.max(item.intensity * 100, 10)}%`, backgroundColor: heatColor(item.intensity) }} />
              </div>
            </div>
            <div className="mt-2 truncate text-[11px] text-slate-500">{item.nodes.map((node) => node.name).join(" / ") || "暂无"}</div>
            {index < STAGES.length - 1 ? <div className="mt-2 h-1 rounded-full bg-gradient-to-r from-yellow-300 via-orange-400 to-red-500 opacity-60" /> : null}
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-2 md:grid-cols-6">
        {timeline.slice(0, 12).map((item, index) => {
          const heat = pointHeat(item);
          const intensity = Math.min(heat / maxTimeline, 1);
          return (
            <div key={`${pointDate(item)}-${index}`} className="rounded-md border border-[#f2dfd2] bg-white p-3">
              <div className="mono text-xs text-slate-500">{pointDate(item)}</div>
              <div className="mt-3 h-2 rounded-full bg-[#ffedd5]">
                <div className="h-full rounded-full" style={{ width: `${Math.max(intensity * 100, 8)}%`, backgroundColor: heatColor(intensity) }} />
              </div>
              <div className="mono mt-2 text-sm font-semibold text-slate-900">{heat.toFixed(1)}</div>
            </div>
          );
        })}
        {!timeline.length ? <EmptyHint label="暂无节点时间序列" /> : null}
      </div>
    </section>
  );
}

function WorldDistributionPanel({ geo, fallbackRegions, selectedNode }: { geo: ChainGeo | null; fallbackRegions: ChainRegion[]; selectedNode: ChainNode | null }) {
  const regions = (geo?.regions?.length ? geo.regions : fallbackRegions).slice(0, 12);
  const width = 720;
  const height = 420;
  return (
    <section className="rounded-lg border border-[#f2dfd2] bg-white p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-lg font-semibold text-slate-950">
          <Globe2 size={18} className="text-orange-600" />
          世界地图分布图
        </div>
        <div className="text-xs text-slate-500">{selectedNode?.name ?? "全局节点"} / {regions.length} 区域</div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-[420px] w-full rounded-lg bg-[#fffdfa]" role="img" aria-label="世界产业分布图">
        <defs>
          <filter id="world-marker-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect width={width} height={height} fill="#fffdfa" />
        <path d="M86 142 C132 96 218 98 266 135 C229 169 156 176 92 164 Z" fill="#f1f5f9" stroke="#e2e8f0" />
        <path d="M272 158 C322 98 404 94 462 142 C432 196 342 202 282 184 Z" fill="#f1f5f9" stroke="#e2e8f0" />
        <path d="M438 150 C494 92 616 102 668 160 C617 206 504 203 449 184 Z" fill="#f1f5f9" stroke="#e2e8f0" />
        <path d="M332 218 C386 205 436 246 418 314 C371 322 334 282 332 218 Z" fill="#f1f5f9" stroke="#e2e8f0" />
        <path d="M548 286 C584 260 648 277 666 330 C625 355 572 343 548 286 Z" fill="#f1f5f9" stroke="#e2e8f0" />
        {regions.map((region, index) => {
          const point = regionPoint(region, index, width, height);
          const intensity = normalizeHeat(region.heat ?? (region.intensity ?? 0) * 100);
          const color = heatColor(intensity);
          return (
            <g key={`${region.region_key}-${index}`}>
              <circle cx={point.x} cy={point.y} r={16 + intensity * 22} fill={color} opacity="0.18" filter="url(#world-marker-glow)" />
              <circle cx={point.x} cy={point.y} r={6 + intensity * 10} fill={color} stroke="#ffffff" strokeWidth="2" />
              <text x={point.x + 12} y={point.y + 4} fill="#334155" fontSize="11.5" fontWeight="750">{clipLabel(region.label || region.region_key, 10)}</text>
            </g>
          );
        })}
      </svg>
    </section>
  );
}

function MiniMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-[#f2dfd2] bg-[#fffaf5] p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mono mt-1 font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function EmptyHint({ label }: { label: string }) {
  return <div className="rounded-md border border-dashed border-[#f2dfd2] px-3 py-3 text-sm text-slate-500">{label}</div>;
}

function buildChainSummaries(nodeMap: Map<string, ChainNode>) {
  const raw = CHAIN_BLUEPRINTS.map<ChainSummary>((chain) => {
    const nodes = chain.nodeKeys.map((key) => nodeMap.get(key)).filter((node): node is ChainNode => Boolean(node));
    const heat = nodes.length ? nodes.reduce((sum, node) => sum + nodeHeat(node), 0) / nodes.length : 0;
    return { ...chain, nodes, heat, intensity: 0 };
  });
  const maxHeat = Math.max(...raw.map((chain) => chain.heat), 1);
  return raw.map((chain) => ({ ...chain, intensity: Math.min(chain.heat / maxHeat, 1) }));
}

function stageIndex(node: ChainNode) {
  if (node.layer === "自然资源" || node.layer === "公共品与能源") return 0;
  if (node.layer === "基础材料") return 1;
  if (node.layer === "通用零部件") return 2;
  if (node.layer === "设备与系统") return 3;
  if (node.layer === "终端产品") return 4;
  if (node.layer === "渠道与服务") return 5;
  return 6;
}

function metroPath(source: MetroStation, target: MetroStation) {
  const dx = Math.max(44, Math.abs(target.x - source.x) * 0.42);
  return `M ${source.x} ${source.y} C ${source.x + dx} ${source.y}, ${target.x - dx} ${target.y}, ${target.x} ${target.y}`;
}

function nodeHeat(node: ChainNode) {
  return Math.max(node.heat ?? 0, node.momentum ?? 0, (node.intensity ?? 0) * 100);
}

function normalizeHeat(heat: number) {
  return Math.min(Math.max(heat / 100, 0), 1);
}

function heatColor(intensity: number) {
  if (intensity >= 0.84) return "#b91c1c";
  if (intensity >= 0.62) return "#ea580c";
  if (intensity >= 0.36) return "#f59e0b";
  return "#facc15";
}

function pointDate(item: ChainTimelinePoint) {
  return item.trade_date ?? item.date ?? "--";
}

function pointHeat(item: ChainTimelinePoint) {
  return Math.max(item.heat ?? 0, item.momentum ?? 0, (item.intensity ?? 0) * 100);
}

function regionPoint(region: ChainRegion, index: number, width: number, height: number) {
  if (typeof region.x === "number" && typeof region.y === "number") {
    const rawX = region.x <= 1 ? region.x * width : region.x;
    const rawY = region.y <= 1 ? region.y * height : region.y;
    const needsBaseScale = rawX > 100 || rawY > 100;
    const scaledX = needsBaseScale ? rawX / 1000 * width : rawX;
    const scaledY = needsBaseScale ? rawY / 620 * height : rawY;
    return {
      x: clamp(scaledX, 28, width - 88),
      y: clamp(scaledY, 30, height - 36)
    };
  }
  const fallback = [
    [142, 152],
    [212, 238],
    [352, 154],
    [382, 274],
    [520, 162],
    [610, 204],
    [612, 314],
    [472, 220],
    [294, 112],
    [188, 308],
    [560, 118],
    [420, 118]
  ][index % 12];
  return { x: fallback[0], y: fallback[1] };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function formatNumber(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(1) : "--";
}

function clipLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}
