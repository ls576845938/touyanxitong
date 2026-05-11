"use client";

import { useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Maximize2, Minus, Plus, RotateCcw, Target, Info } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
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
    <div className="relative group overflow-hidden rounded-3xl border border-slate-200 bg-white text-slate-900 shadow-2xl transition-all duration-500 hover:border-slate-300">
      <div className="absolute inset-0 pointer-events-none opacity-30">
        <div className="absolute top-[20%] right-[-10%] w-[50%] h-[50%] bg-blue-50 blur-[120px] rounded-full" />
        <div className="absolute bottom-[20%] left-[-10%] w-[50%] h-[50%] bg-indigo-50 blur-[120px] rounded-full" />
      </div>

      <div className="relative z-10 flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 bg-white/60 backdrop-blur-xl px-6 py-4">
        <div className="flex items-center gap-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 border border-indigo-100 shadow-sm">
            <Target className="text-indigo-600" size={20} />
          </div>
          <div>
            <h3 className="text-sm font-black uppercase tracking-[0.1em] text-slate-900 flex items-center gap-2">
              全产业链关系总图
              <span className="px-2 py-0.5 rounded-full bg-indigo-50 border border-indigo-100 text-[9px] font-bold text-indigo-600 uppercase tracking-widest">Dynamic Mesh</span>
            </h3>
            <div className="mt-1 flex items-center gap-2 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
              {model.selectedName ? (
                <span className="text-orange-600 font-black">{model.selectedName} 链路系</span>
              ) : (
                "全域概览模式"
              )}
              <span className="opacity-30">•</span>
              <span>{model.visibleNodeCount} 节点</span>
              <span className="opacity-30">•</span>
              <span>{model.visibleEdgeCount} 关系</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <ControlButton active={showLabels} onClick={() => setShowLabels(!showLabels)} icon={Maximize2} label="标签" />
          <div className="h-6 w-[1px] bg-slate-200 mx-1" />
          <ControlButton onClick={() => setZoom(v => clamp(v - 0.15, 0.5, 2.5))} icon={Minus} label="缩小" />
          <ControlButton onClick={() => setZoom(v => clamp(v + 0.15, 0.5, 2.5))} icon={Plus} label="放大" />
          <ControlButton onClick={resetViewport} icon={RotateCcw} label="重置" />
        </div>
      </div>

      <div className="relative h-[760px] bg-slate-50/30">
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
              setZoom(clamp(gesture.startZoom * zoomRatio, 0.5, 2.5));
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
            <radialGradient id="graph-sphere-bg" cx="45%" cy="35%" r="65%">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="100%" stopColor="#f1f5f9" />
            </radialGradient>
            <filter id="soft-glow-node-light" x="-200%" y="-200%" width="500%" height="500%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <marker id="graph-arrow-light" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#f97316" />
            </marker>
            <clipPath id="industry-sphere-clip-light">
              <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS * zoom + 5} />
            </clipPath>
          </defs>

          <circle cx={CENTER_X} cy={CENTER_Y} r={SPHERE_RADIUS * zoom} fill="url(#graph-sphere-bg)" stroke="#e2e8f0" strokeWidth="1" />
          
          <g clipPath="url(#industry-sphere-clip-light)">
            <g opacity="0.15">
              {projection.latitudeLines.map((path, index) => (
                <path key={`lat-${index}`} d={path} fill="none" stroke="#94a3b8" strokeWidth="0.5" strokeDasharray="2 4" />
              ))}
              {projection.longitudeLines.map((path, index) => (
                <path key={`lon-${index}`} d={path} fill="none" stroke="#94a3b8" strokeWidth="0.5" strokeDasharray="2 4" />
              ))}
            </g>

            <g>
              {projection.edges.map((item) => (
                <motion.path
                  key={`${item.edge.source}-${item.edge.target}-${item.edge.relation_type ?? ""}`}
                  initial={false}
                  animate={{
                    d: item.path,
                    stroke: item.active ? "#f97316" : "#cbd5e1",
                    strokeOpacity: item.opacity,
                    strokeWidth: item.width
                  }}
                  fill="none"
                  markerEnd={item.active && item.z > -0.1 ? "url(#graph-arrow-light)" : undefined}
                />
              ))}
            </g>
          </g>

          <g>
            {projection.nodes.map((item) => {
              const active = item.node.node_key === selectedNodeKey;
              const hColor = heatColor(item.intensity);
              const layerColor = layerColorAt(item.layerIndex);
              const labelVisible = showLabels && (item.z > -0.08 || active || item.connected);
              const r = item.r * item.scale;
              
              return (
                <motion.g
                  key={item.node.node_key}
                  initial={false}
                  animate={{
                    opacity: item.opacity,
                    transform: `translate(${item.x}px, ${item.y}px) scale(${active ? 1.25 : 1})`
                  }}
                  className="cursor-pointer"
                  onClick={() => !suppressClickRef.current && onSelect(item.node.node_key)}
                >
                  <circle r={r * 2.2} fill={layerColor} opacity={active ? 0.2 : 0.08} filter="url(#soft-glow-node-light)" />
                  <circle r={r} fill="white" stroke={active ? "#0f172a" : hColor} strokeWidth={active ? 3 : 1.5} shadow-sm />
                  <circle cx={-r * 0.3} cy={-r * 0.3} r={r * 0.25} fill={hColor} opacity={0.6} />
                  
                  <AnimatePresence>
                    {labelVisible && (
                      <motion.g
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: 5 }}
                        transform={`translate(${r + 6} -10)`}
                      >
                        <rect
                          width={labelWidth(item.node.name)}
                          height={22}
                          rx={11}
                          fill="white"
                          stroke={active ? "#f97316" : "#e2e8f0"}
                          className="shadow-md"
                        />
                        <text x="10" y="15" fill={active ? "#0f172a" : "#475569"} fontSize="11" fontWeight="800" className="pointer-events-none">
                          {clipLabel(item.node.name, 12)}
                        </text>
                      </motion.g>
                    )}
                  </AnimatePresence>
                </motion.g>
              );
            })}
          </g>

          <g>
            {projection.layerLabels.map((label) => (
              <motion.g
                key={label.key}
                initial={false}
                animate={{
                  transform: `translate(${label.x}px, ${label.y}px)`,
                  opacity: label.opacity
                }}
              >
                <circle r="4" fill={label.color} stroke="white" strokeWidth="1" className="shadow-sm" />
                <text
                  x={label.textAnchor === "start" ? 10 : -10}
                  y="4"
                  textAnchor={label.textAnchor}
                  fill="#64748b"
                  fontSize="10"
                  fontWeight="900"
                  className="uppercase tracking-widest"
                >
                  {label.name}
                </text>
              </motion.g>
            ))}
          </g>
        </svg>

        <div className="absolute bottom-8 left-8 p-5 rounded-2xl border border-slate-200 bg-white/90 backdrop-blur-xl shadow-xl flex flex-col gap-3">
          <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
            <Info size={12} />
            热力强度区间
          </div>
          <div className="flex gap-4">
            <LegendItem color="#eab308" label="温和" />
            <LegendItem color="#f97316" label="活跃" />
            <LegendItem color="#ef4444" label="爆红" />
          </div>
        </div>

        <div className="absolute top-24 right-8 p-5 rounded-2xl border border-slate-200 bg-white/90 backdrop-blur-xl shadow-xl w-48 hidden lg:block">
          <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-4">产业空间分区</div>
          <div className="space-y-2.5">
            {model.layers.map((layer, index) => (
              <div key={layer} className="flex items-center gap-3 group/layer cursor-default">
                <div className="h-2.5 w-2.5 rounded-full transition-transform group-hover/layer:scale-125" style={{ backgroundColor: layerColorAt(index) }} />
                <span className="text-[11px] font-bold text-slate-600 group-hover/layer:text-slate-900 transition-colors">{layer}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ControlButton({ icon: Icon, label, onClick, active }: { icon: any; label: string; onClick: () => void; active?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex h-9 items-center gap-2 rounded-xl border px-4 text-[11px] font-bold transition-all active:scale-95",
        active 
          ? "bg-slate-900 border-slate-900 text-white shadow-lg shadow-slate-200" 
          : "bg-white border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-900 hover:shadow-sm"
      )}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color, boxShadow: `0 0 10px ${color}66` }} />
      <span className="text-[11px] font-bold text-slate-600 tracking-tight">{label}</span>
    </div>
  );
}

function heatColor(intensity: number) {
  if (intensity >= 0.8) return "#ef4444"; // Red
  if (intensity >= 0.45) return "#f97316"; // Orange
  return "#eab308"; // Yellow
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
    patches: [], 
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

function layerColorAt(index: number) {
  return LAYER_PALETTE[index % LAYER_PALETTE.length];
}

function clipLabel(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function labelWidth(value: string) {
  return Math.min(120, Math.max(60, clipLabel(value, 12).length * 9 + 20));
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
