"use client";

import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import type { ChainEdge, ChainNode } from "@/lib/api";

type IndustryGraphMapProps = {
  nodes: ChainNode[];
  edges: ChainEdge[];
  selectedNodeKey: string | null;
  activeLayer: string;
  query: string;
  onSelect: (nodeKey: string) => void;
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

type GraphNode = {
  node: ChainNode;
  base: Vec3;
  r: number;
  heat: number;
  intensity: number;
  layerIndex: number;
  visible: boolean;
  matched: boolean;
  connected: boolean;
  contextual: boolean;
  downstreamDepth: number | null;
};

type ProjectedNode = GraphNode & {
  x: number;
  y: number;
  z: number;
  scale: number;
  opacity: number;
};

type GraphEdge = {
  edge: ChainEdge;
  source: GraphNode;
  target: GraphNode;
  heat: number;
  intensity: number;
  active: boolean;
};

type ProjectedEdge = GraphEdge & {
  path: string;
  opacity: number;
  width: number;
  z: number;
};

type PointerPoint = {
  x: number;
  y: number;
};

type GestureState =
  | {
      mode: "rotate";
      pointerId: number;
      startX: number;
      startY: number;
      origin: Rotation;
    }
  | {
      mode: "pinch";
      startDistance: number;
      startZoom: number;
      startCenter: PointerPoint;
      origin: Rotation;
    };

const WIDTH = 1180;
const HEIGHT = 760;
const CENTER_X = WIDTH / 2;
const CENTER_Y = HEIGHT / 2;
const SPHERE_RADIUS = 288;
const TWO_PI = Math.PI * 2;

const LAYER_PALETTE = [
  "#38bdf8",
  "#22c55e",
  "#f59e0b",
  "#a78bfa",
  "#06b6d4",
  "#ef4444",
  "#14b8a6",
  "#eab308"
];

export function IndustryGraphMap({
  nodes,
  edges,
  selectedNodeKey,
  activeLayer,
  query,
  onSelect
}: IndustryGraphMapProps) {
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState<Rotation>({ x: -0.12, y: -0.42 });
  const [showLabels, setShowLabels] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const pointersRef = useRef(new Map<number, PointerPoint>());
  const gestureRef = useRef<GestureState | null>(null);
  const suppressClickRef = useRef(false);

  const model = useMemo(
    () => buildGraph(nodes, edges, selectedNodeKey, activeLayer, query),
    [activeLayer, edges, nodes, query, selectedNodeKey]
  );
  const projection = useMemo(() => projectGraph(model, rotation, zoom), [model, rotation, zoom]);

  const resetViewport = () => {
    setZoom(1);
    setRotation({ x: -0.12, y: -0.42 });
  };

  return (
    <div className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#f7e9de] px-4 py-3">
        <div>
          <div className="text-sm font-semibold text-slate-950">全产业链关系总图</div>
          <div className="mt-1 text-xs text-slate-500">
            {model.selectedName ? `${model.selectedName} 下游链 ${model.downstreamCount} 个节点${model.contextCount ? ` / 相关输入 ${model.contextCount}` : ""} / ` : ""}
            {model.visibleNodeCount} 个节点 / {model.visibleEdgeCount} 条关系
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowLabels((value) => !value)}
            className={`inline-flex h-9 items-center gap-2 rounded-md border px-3 text-xs ${
              showLabels ? "border-orange-500 bg-orange-50 text-orange-700" : "border-[#f2dfd2] text-slate-600"
            }`}
          >
            <Maximize2 size={14} />
            标签
          </button>
          <IconButton label="缩小" onClick={() => setZoom((value) => clamp(value - 0.12, 0.62, 1.9))}>
            <Minus size={15} />
          </IconButton>
          <IconButton label="放大" onClick={() => setZoom((value) => clamp(value + 0.12, 0.62, 1.9))}>
            <Plus size={15} />
          </IconButton>
          <IconButton label="重置" onClick={resetViewport}>
            <RotateCcw size={15} />
          </IconButton>
        </div>
      </div>

      <div className="relative h-[760px] bg-[#fffdf9]">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label="全产业链球面关系节点图"
          className="h-full w-full select-none"
          onPointerDown={(event) => {
            if (event.pointerType === "mouse" && event.button !== 0) return;
            pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
            suppressClickRef.current = false;
            setIsDragging(true);
            startGesture(pointersRef.current, event.pointerId, rotation, zoom, gestureRef);
          }}
          onPointerMove={(event) => {
            if (!pointersRef.current.has(event.pointerId)) return;
            pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
            const gesture = gestureRef.current;
            if (!gesture) return;

            if (gesture.mode === "pinch") {
              const points = Array.from(pointersRef.current.values());
              if (points.length < 2) return;
              const distance = pointerDistance(points[0], points[1]);
              const center = pointerCenter(points[0], points[1]);
              const zoomRatio = distance / Math.max(gesture.startDistance, 1);
              const centerDx = center.x - gesture.startCenter.x;
              const centerDy = center.y - gesture.startCenter.y;
              suppressClickRef.current = true;
              setZoom(clamp(gesture.startZoom * zoomRatio, 0.62, 1.9));
              setRotation({
                x: clamp(gesture.origin.x + centerDy * 0.0042, -1.18, 1.18),
                y: gesture.origin.y + centerDx * 0.0048
              });
              return;
            }

            const point = pointersRef.current.get(gesture.pointerId);
            if (!point) return;
            const dx = point.x - gesture.startX;
            const dy = point.y - gesture.startY;
            if (Math.abs(dx) + Math.abs(dy) > 4) suppressClickRef.current = true;
            setRotation({
              x: clamp(gesture.origin.x + dy * 0.0062, -1.18, 1.18),
              y: gesture.origin.y + dx * 0.0074
            });
          }}
          onPointerUp={(event) => {
            pointersRef.current.delete(event.pointerId);
            if (pointersRef.current.size === 0) {
              gestureRef.current = null;
              setIsDragging(false);
              return;
            }
            startGesture(pointersRef.current, Array.from(pointersRef.current.keys())[0], rotation, zoom, gestureRef);
          }}
          onPointerCancel={(event) => {
            pointersRef.current.delete(event.pointerId);
            if (pointersRef.current.size === 0) {
              gestureRef.current = null;
              setIsDragging(false);
            }
          }}
          style={{ cursor: isDragging ? "grabbing" : "grab", touchAction: "none" }}
        >
          <defs>
            <clipPath id="industry-sphere-clip">
              <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS * zoom + 5} />
            </clipPath>
            <filter id="graph-node-shadow" x="-80%" y="-80%" width="260%" height="260%">
              <feDropShadow dx="0" dy="10" stdDeviation="8" floodColor="#7c2d12" floodOpacity="0.13" />
            </filter>
            <filter id="sphere-shadow" x="-20%" y="-20%" width="140%" height="160%">
              <feDropShadow dx="0" dy="20" stdDeviation="18" floodColor="#7c2d12" floodOpacity="0.10" />
            </filter>
            <radialGradient id="sphere-surface" cx="42%" cy="32%" r="68%">
              <stop offset="0" stopColor="#ffffff" stopOpacity="0.98" />
              <stop offset="0.46" stopColor="#fff7ed" stopOpacity="0.95" />
              <stop offset="1" stopColor="#fed7aa" stopOpacity="0.36" />
            </radialGradient>
            <radialGradient id="sphere-gloss" cx="35%" cy="28%" r="44%">
              <stop offset="0" stopColor="#ffffff" stopOpacity="0.68" />
              <stop offset="0.72" stopColor="#ffffff" stopOpacity="0.12" />
              <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
            </radialGradient>
            <marker id="graph-arrow-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#ea580c" opacity="0.68" />
            </marker>
          </defs>

          <rect width={WIDTH} height={HEIGHT} fill="#fffdf9" />
          <ellipse cx={CENTER_X} cy="668" rx={SPHERE_RADIUS * zoom * 1.02} ry={46 * zoom} fill="#fed7aa" opacity="0.2" />
          <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS * zoom} fill="url(#sphere-surface)" filter="url(#sphere-shadow)" />

          <g clipPath="url(#industry-sphere-clip)">
            {projection.patches.map((patch) => (
              <path key={patch.key} d={patch.path} fill={patch.color} opacity={patch.opacity} />
            ))}
            {projection.latitudeLines.map((path, index) => (
              <path key={`lat-${index}`} d={path} fill="none" stroke="#f1c9ad" strokeWidth="1" strokeOpacity="0.28" />
            ))}
            {projection.longitudeLines.map((path, index) => (
              <path key={`lon-${index}`} d={path} fill="none" stroke="#f2d8c6" strokeWidth="1" strokeOpacity="0.22" />
            ))}
            <g fill="none">
              {projection.edges.map((item) => (
                <path
                  key={`${item.edge.source}-${item.edge.target}-${item.edge.relation_type ?? ""}`}
                  d={item.path}
                  stroke={item.active ? warmColor(item.intensity) : "#bfaea0"}
                  strokeWidth={item.width}
                  strokeOpacity={item.opacity}
                  strokeLinecap="round"
                  markerEnd={item.active && item.z > -0.1 ? "url(#graph-arrow-hot)" : undefined}
                />
              ))}
            </g>
          </g>

          <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS * zoom} fill="url(#sphere-gloss)" pointerEvents="none" />
          <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS * zoom} fill="none" stroke="#f4c7a8" strokeWidth="1.4" strokeOpacity="0.72" />

          <g>
            {projection.nodes.map((item) => {
              const active = item.node.node_key === selectedNodeKey;
              const color = warmColor(item.intensity);
              const layerColor = layerColorAt(item.layerIndex);
              const downstream = item.downstreamDepth !== null;
              const labelVisible = showLabels && (item.z > -0.08 || active || item.connected);
              const r = item.r * item.scale;
              return (
                <g
                  key={item.node.node_key}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    if (suppressClickRef.current) {
                      suppressClickRef.current = false;
                      return;
                    }
                    onSelect(item.node.node_key);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(item.node.node_key);
                    }
                  }}
                  className="cursor-pointer outline-none"
                  opacity={item.opacity}
                >
                  <circle cx={item.x} cy={item.y} r={r * 2.15} fill={layerColor} opacity={active ? 0.22 : downstream ? 0.16 : item.contextual ? 0.12 : 0.08} />
                  <circle
                    cx={item.x}
                    cy={item.y}
                    r={r}
                    fill={color}
                    stroke={active ? "#111827" : downstream ? "#ea580c" : item.contextual ? "#f59e0b" : item.matched ? "#f97316" : "#ffffff"}
                    strokeWidth={active ? 2.8 : downstream || item.contextual ? 2 : 1.2}
                    filter="url(#graph-node-shadow)"
                  />
                  <circle cx={item.x - r * 0.28} cy={item.y - r * 0.34} r={Math.max(2, r * 0.18)} fill="#ffffff" opacity="0.72" />
                  {labelVisible ? (
                    <g transform={`translate(${item.x + r + 6} ${item.y - 11})`}>
                      <rect width={labelWidth(item.node.name)} height="24" rx="7" fill="#ffffff" fillOpacity="0.94" stroke={active ? "#ea580c" : "#f3dfd3"} />
                      <text x="8" y="16" fill="#111827" fontSize="11.5" fontWeight={active ? "800" : "650"}>
                        {clipLabel(item.node.name, 10)}
                      </text>
                    </g>
                  ) : null}
                  <title>{`${item.node.name}｜${item.node.layer}｜热度 ${item.heat.toFixed(1)}`}</title>
                </g>
              );
            })}
          </g>

          <g>
            {projection.layerLabels.map((label) => (
              <g key={label.key} transform={`translate(${label.x} ${label.y})`} opacity={label.opacity}>
                <circle r="5" fill={label.color} opacity="0.72" />
                <text x={label.textAnchor === "start" ? 11 : -11} y="4" textAnchor={label.textAnchor} fill="#475569" fontSize="11.5" fontWeight="700">
                  {label.name}
                </text>
              </g>
            ))}
          </g>

          <g transform="translate(28 710)">
            <rect width="330" height="34" rx="10" fill="#ffffff" stroke="#f2dfd2" />
            <LegendDot x={20} color="#facc15" label="温和" />
            <LegendDot x={94} color="#f59e0b" label="升温" />
            <LegendDot x={170} color="#ea580c" label="活跃" />
            <LegendDot x={246} color="#b91c1c" label="高热" />
          </g>
          <LayerLegend layers={model.layers} />
        </svg>
      </div>
    </div>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[#f2dfd2] bg-white text-slate-600 hover:border-orange-300 hover:text-orange-700"
    >
      {children}
    </button>
  );
}

function LegendDot({ x, color, label }: { x: number; color: string; label: string }) {
  return (
    <g transform={`translate(${x} 17)`}>
      <circle cx="0" cy="0" r="6" fill={color} />
      <text x="12" y="4" fill="#64748b" fontSize="12">
        {label}
      </text>
    </g>
  );
}

function LayerLegend({ layers }: { layers: string[] }) {
  const rowHeight = 22;
  const width = 224;
  const height = 38 + layers.length * rowHeight;
  return (
    <g transform="translate(928 84)">
      <rect width={width} height={height} rx="12" fill="#ffffff" fillOpacity="0.92" stroke="#f2dfd2" />
      <text x="14" y="22" fill="#111827" fontSize="12" fontWeight="800">
        球面色块分类
      </text>
      {layers.map((layer, index) => (
        <g key={layer} transform={`translate(14 ${40 + index * rowHeight})`}>
          <rect width="12" height="12" rx="3" fill={layerColorAt(index)} fillOpacity="0.7" />
          <text x="20" y="10" fill="#475569" fontSize="11.5" fontWeight="650">
            {layer}
          </text>
        </g>
      ))}
    </g>
  );
}

function startGesture(
  pointers: Map<number, PointerPoint>,
  pointerId: number,
  rotation: Rotation,
  zoom: number,
  gestureRef: React.MutableRefObject<GestureState | null>
) {
  const points = Array.from(pointers.values());
  if (points.length >= 2) {
    gestureRef.current = {
      mode: "pinch",
      startDistance: pointerDistance(points[0], points[1]),
      startZoom: zoom,
      startCenter: pointerCenter(points[0], points[1]),
      origin: rotation
    };
    return;
  }
  const point = pointers.get(pointerId);
  if (!point) return;
  gestureRef.current = {
    mode: "rotate",
    pointerId,
    startX: point.x,
    startY: point.y,
    origin: rotation
  };
}

function buildGraph(nodes: ChainNode[], edges: ChainEdge[], selectedNodeKey: string | null, activeLayer: string, query: string) {
  const layers = Array.from(new Set(nodes.map((node) => node.layer))).filter(Boolean);
  const lowered = query.trim().toLowerCase();
  const maxHeat = Math.max(...nodes.map(nodeHeat), 1);
  const downstream = buildDownstream(edges, selectedNodeKey);

  const nodesByLayer = new Map<string, ChainNode[]>();
  for (const node of nodes) {
    const rows = nodesByLayer.get(node.layer) ?? [];
    rows.push(node);
    nodesByLayer.set(node.layer, rows);
  }
  for (const rows of nodesByLayer.values()) {
    rows.sort((left, right) => nodeHeat(right) - nodeHeat(left));
  }

  const graphNodes: GraphNode[] = [];
  for (const node of nodes) {
    const layerIndex = Math.max(layers.indexOf(node.layer), 0);
    const group = nodesByLayer.get(node.layer) ?? [];
    const groupIndex = Math.max(group.findIndex((item) => item.node_key === node.node_key), 0);
    const base = spherePosition(layerIndex, layers.length, groupIndex, group.length, nodeHeat(node), maxHeat);
    const matched = matchesNode(node, lowered);
    const layerVisible = activeLayer === "all" || normalizeLayerKey(node.layer) === activeLayer;
    const queryVisible = !lowered || matched;
    const contextual = downstream.contextKeys.has(node.node_key);
    const connected = node.node_key === selectedNodeKey || downstream.keys.has(node.node_key) || contextual;
    const visible = (layerVisible && queryVisible) || connected;
    const intensity = Math.min(nodeHeat(node) / maxHeat, 1);
    const downstreamDepth = downstream.depthByKey.get(node.node_key) ?? null;
    graphNodes.push({
      node,
      base,
      r: 6.8 + intensity * 13.5 + (node.node_key === selectedNodeKey ? 5 : downstreamDepth !== null ? 2 : 0),
      heat: nodeHeat(node),
      intensity,
      layerIndex,
      visible,
      matched,
      connected,
      contextual,
      downstreamDepth
    });
  }

  const byKey = new Map(graphNodes.map((node) => [node.node.node_key, node]));
  const graphEdges = edges.flatMap<GraphEdge>((edge) => {
    const source = byKey.get(edge.source);
    const target = byKey.get(edge.target);
    if (!source || !target) return [];
    const active = downstream.edgeKeys.has(edgeIdentity(edge));
    const heat = Math.max(source.heat, target.heat, edge.heat ?? 0);
    const intensity = Math.max(source.intensity, target.intensity, normalize(edge.intensity), normalize(edge.weight));
    if (!source.visible && !target.visible && !active) return [];
    return [{ edge, source, target, heat, intensity: Math.min(intensity, 1), active }];
  });

  return {
    nodes: graphNodes,
    edges: graphEdges,
    layers,
    selectedName: nodes.find((node) => node.node_key === selectedNodeKey)?.name ?? "",
    downstreamCount: downstream.keys.size,
    contextCount: downstream.contextKeys.size,
    visibleNodeCount: graphNodes.filter((node) => node.visible).length,
    visibleEdgeCount: graphEdges.length
  };
}

function projectGraph(model: ReturnType<typeof buildGraph>, rotation: Rotation, zoom: number) {
  const radius = SPHERE_RADIUS * zoom;
  const nodeMap = new Map<GraphNode, ProjectedNode>();

  for (const node of model.nodes) {
    const rotated = rotatePoint(node.base, rotation);
    const point = projectPoint(rotated, radius);
    const depth = (rotated.z + 1) / 2;
    const scale = 0.78 + depth * 0.44;
    const backDim = rotated.z < -0.2 ? 0.22 : 0.42 + depth * 0.58;
    nodeMap.set(node, {
      ...node,
      x: point.x,
      y: point.y,
      z: rotated.z,
      scale,
      opacity: node.visible ? backDim : Math.min(backDim, 0.16)
    });
  }

  const projectedEdges = model.edges.flatMap<ProjectedEdge>((edge) => {
    const source = nodeMap.get(edge.source);
    const target = nodeMap.get(edge.target);
    if (!source || !target) return [];
    const sourceSurface = rotatePoint(edge.source.base, rotation);
    const targetSurface = rotatePoint(edge.target.base, rotation);
    const z = (source.z + target.z) / 2;
    const depthOpacity = clamp((z + 1) / 2, 0.08, 1);
    const opacity = edge.active ? 0.18 + depthOpacity * 0.42 + edge.intensity * 0.16 : 0.03 + depthOpacity * 0.1;
    const width = edge.active ? 1.15 + edge.intensity * 4 : 0.6 + edge.intensity * 0.78;
    return [
      {
        ...edge,
        path: buildSurfacePath(sourceSurface, targetSurface, radius * 1.006),
        opacity,
        width,
        z
      }
    ];
  });

  return {
    nodes: Array.from(nodeMap.values()).sort((left, right) => left.z - right.z),
    edges: projectedEdges.sort((left, right) => left.z - right.z),
    patches: buildLayerPatches(model.layers, rotation, radius),
    latitudeLines: [-55, -30, 0, 30, 55].map((degree) => buildLatitudePath((degree / 180) * Math.PI, rotation, radius)),
    longitudeLines: Array.from({ length: 12 }, (_, index) => buildLongitudePath((-Math.PI + (index * TWO_PI) / 12), rotation, radius)),
    layerLabels: model.layers.map((name, index) => {
      const lon = -Math.PI + ((index + 0.5) * TWO_PI) / Math.max(model.layers.length, 1);
      const rotated = rotatePoint(sphericalToCartesian(0, lon), rotation);
      const point = projectPoint(rotated, radius * 1.1);
      return {
        key: name,
        name,
        color: layerColorAt(index),
        x: point.x,
        y: point.y,
        opacity: clamp((rotated.z + 1) / 2, 0.26, 0.92),
        textAnchor: point.x >= CENTER_X ? "start" as const : "end" as const
      };
    })
  };
}

function buildSurfacePath(source: Vec3, target: Vec3, radius: number) {
  const dot = clamp(source.x * target.x + source.y * target.y + source.z * target.z, -0.999, 0.999);
  const omega = Math.acos(dot);
  const sinOmega = Math.sin(omega) || 1;
  const steps = Math.max(8, Math.ceil((omega / Math.PI) * 28));
  const commands: string[] = [];

  for (let index = 0; index <= steps; index += 1) {
    const t = index / steps;
    const left = Math.sin((1 - t) * omega) / sinOmega;
    const right = Math.sin(t * omega) / sinOmega;
    const point = normalizeVec({
      x: source.x * left + target.x * right,
      y: source.y * left + target.y * right,
      z: source.z * left + target.z * right
    });
    const projected = projectPoint(point, radius);
    commands.push(`${index === 0 ? "M" : "L"} ${projected.x} ${projected.y}`);
  }

  return commands.join(" ");
}

function buildLayerPatches(layers: string[], rotation: Rotation, radius: number) {
  const sector = TWO_PI / Math.max(layers.length, 1);
  return layers.map((layer, index) => {
    const lonStart = -Math.PI + index * sector + 0.018;
    const lonEnd = lonStart + sector - 0.036;
    const points: string[] = [];
    for (let step = 0; step <= 18; step += 1) {
      const lat = -1.08 + (step / 18) * 2.16;
      const point = projectPoint(rotatePoint(sphericalToCartesian(lat, lonStart), rotation), radius);
      points.push(`${point.x} ${point.y}`);
    }
    for (let step = 18; step >= 0; step -= 1) {
      const lat = -1.08 + (step / 18) * 2.16;
      const point = projectPoint(rotatePoint(sphericalToCartesian(lat, lonEnd), rotation), radius);
      points.push(`${point.x} ${point.y}`);
    }
    return {
      key: layer,
      color: layerColorAt(index),
      opacity: 0.105,
      path: `M ${points.join(" L ")} Z`
    };
  });
}

function buildLatitudePath(lat: number, rotation: Rotation, radius: number) {
  const points: string[] = [];
  for (let step = 0; step <= 72; step += 1) {
    const lon = -Math.PI + (step / 72) * TWO_PI;
    const point = projectPoint(rotatePoint(sphericalToCartesian(lat, lon), rotation), radius);
    points.push(`${step === 0 ? "M" : "L"} ${point.x} ${point.y}`);
  }
  return points.join(" ");
}

function buildLongitudePath(lon: number, rotation: Rotation, radius: number) {
  const points: string[] = [];
  for (let step = 0; step <= 54; step += 1) {
    const lat = -1.25 + (step / 54) * 2.5;
    const point = projectPoint(rotatePoint(sphericalToCartesian(lat, lon), rotation), radius);
    points.push(`${step === 0 ? "M" : "L"} ${point.x} ${point.y}`);
  }
  return points.join(" ");
}

function spherePosition(layerIndex: number, layerCount: number, index: number, count: number, heat: number, maxHeat: number) {
  const sector = TWO_PI / Math.max(layerCount, 1);
  const lonBase = -Math.PI + sector * (layerIndex + 0.5);
  const rank = count <= 1 ? 0.5 : index / Math.max(count - 1, 1);
  const latBase = (0.5 - rank) * Math.PI * 0.72;
  const lonJitter = Math.sin((index + 1) * 2.399) * sector * 0.33;
  const heatLift = (Math.min(heat / Math.max(maxHeat, 1), 1) - 0.5) * 0.16;
  return sphericalToCartesian(clamp(latBase + heatLift, -1.18, 1.18), lonBase + lonJitter);
}

function sphericalToCartesian(lat: number, lon: number): Vec3 {
  const cosLat = Math.cos(lat);
  return {
    x: cosLat * Math.sin(lon),
    y: Math.sin(lat),
    z: cosLat * Math.cos(lon)
  };
}

function rotatePoint(point: Vec3, rotation: Rotation): Vec3 {
  const yawCos = Math.cos(rotation.y);
  const yawSin = Math.sin(rotation.y);
  const x1 = point.x * yawCos + point.z * yawSin;
  const z1 = -point.x * yawSin + point.z * yawCos;
  const pitchCos = Math.cos(rotation.x);
  const pitchSin = Math.sin(rotation.x);
  return {
    x: x1,
    y: point.y * pitchCos - z1 * pitchSin,
    z: point.y * pitchSin + z1 * pitchCos
  };
}

function projectPoint(point: Vec3, radius: number) {
  const perspective = 1 / (1 - point.z * 0.16);
  return {
    x: CENTER_X + point.x * radius * perspective,
    y: CENTER_Y - point.y * radius * perspective
  };
}

function buildDownstream(edges: ChainEdge[], selectedNodeKey: string | null) {
  const keys = new Set<string>();
  const contextKeys = new Set<string>();
  const edgeKeys = new Set<string>();
  const depthByKey = new Map<string, number>();
  if (!selectedNodeKey) return { keys, contextKeys, edgeKeys, depthByKey };

  const adjacency = new Map<string, ChainEdge[]>();
  for (const edge of edges) {
    const rows = adjacency.get(edge.source) ?? [];
    rows.push(edge);
    adjacency.set(edge.source, rows);
  }

  const visited = new Set<string>([selectedNodeKey]);
  const queue: { nodeKey: string; depth: number }[] = [{ nodeKey: selectedNodeKey, depth: 0 }];
  while (queue.length) {
    const current = queue.shift();
    if (!current) break;
    for (const edge of adjacency.get(current.nodeKey) ?? []) {
      if (edge.target === selectedNodeKey) continue;
      edgeKeys.add(edgeIdentity(edge));
      if (visited.has(edge.target)) continue;
      visited.add(edge.target);
      keys.add(edge.target);
      depthByKey.set(edge.target, current.depth + 1);
      queue.push({ nodeKey: edge.target, depth: current.depth + 1 });
    }
  }

  for (const edge of edges) {
    if (!keys.has(edge.target)) continue;
    if (edge.source === selectedNodeKey || keys.has(edge.source)) continue;
    contextKeys.add(edge.source);
    edgeKeys.add(edgeIdentity(edge));
  }

  return { keys, contextKeys, edgeKeys, depthByKey };
}

function edgeIdentity(edge: ChainEdge) {
  return `${edge.source}->${edge.target}:${edge.relation_type ?? ""}:${edge.flow ?? ""}`;
}

function matchesNode(node: ChainNode, query: string) {
  if (!query) return true;
  return [node.name, node.node_key, node.layer, node.node_type, ...(node.industry_names ?? []), ...(node.tags ?? [])]
    .join(" ")
    .toLowerCase()
    .includes(query);
}

function nodeHeat(node: ChainNode) {
  return Math.max(node.heat ?? 0, node.momentum ?? 0, (node.intensity ?? 0) * 100);
}

function normalize(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return 0;
  return value > 1 ? value / 100 : value;
}

function normalizeLayerKey(value: string) {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function warmColor(intensity: number) {
  if (intensity >= 0.86) return "#b91c1c";
  if (intensity >= 0.64) return "#ea580c";
  if (intensity >= 0.38) return "#f59e0b";
  return "#facc15";
}

function layerColorAt(index: number) {
  return LAYER_PALETTE[index % LAYER_PALETTE.length];
}

function clipLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function labelWidth(value: string) {
  return Math.min(98, Math.max(46, clipLabel(value, 10).length * 12 + 16));
}

function pointerDistance(left: PointerPoint, right: PointerPoint) {
  return Math.hypot(left.x - right.x, left.y - right.y);
}

function pointerCenter(left: PointerPoint, right: PointerPoint) {
  return {
    x: (left.x + right.x) / 2,
    y: (left.y + right.y) / 2
  };
}

function normalizeVec(value: Vec3): Vec3 {
  const length = Math.hypot(value.x, value.y, value.z) || 1;
  return {
    x: value.x / length,
    y: value.y / length,
    z: value.z / length
  };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}
