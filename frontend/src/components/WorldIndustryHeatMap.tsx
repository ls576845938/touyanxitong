"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Globe2, MapPin, Navigation, Zap, Info } from "lucide-react";
import type { ChainGeo, ChainNode, ChainRegion, ChainRoute } from "@/lib/api";

type WorldIndustryHeatMapProps = {
  geo: ChainGeo | null;
  selectedNode: ChainNode | null;
};

type AtlasRegion = {
  region_key: string;
  label: string;
  x: number;
  y: number;
  path: string;
};

type RenderRegion = AtlasRegion & ChainRegion & {
  intensityValue: number;
  heatValue: number;
};

// 更加精细化的世界区域矢量路径（点阵/数字网格风格示意）
const REGION_ATLAS: AtlasRegion[] = [
  { region_key: "north_america", label: "北美区域", x: 220, y: 200, path: "M80 120 L240 80 L360 140 L340 280 L200 340 L100 240 Z" },
  { region_key: "latin_america", label: "拉美市场", x: 300, y: 460, path: "M280 320 L360 380 L320 540 L240 580 L220 420 Z" },
  { region_key: "europe", label: "欧洲核心", x: 500, y: 170, path: "M440 120 L540 100 L600 160 L540 220 L460 200 Z" },
  { region_key: "middle_east", label: "中东能源", x: 580, y: 260, path: "M540 210 L620 200 L640 280 L560 300 Z" },
  { region_key: "africa", label: "非洲大陆", x: 540, y: 380, path: "M460 240 L580 230 L640 340 L580 500 L420 440 Z" },
  { region_key: "china", label: "中国制造", x: 780, y: 220, path: "M660 120 L840 100 L940 180 L880 300 L720 320 Z" },
  { region_key: "india", label: "印度增长", x: 680, y: 310, path: "M640 260 L720 250 L740 340 L660 360 Z" },
  { region_key: "developed_asia", label: "日韩台", x: 880, y: 180, path: "M840 130 L920 120 L940 210 L860 220 Z" },
  { region_key: "asean", label: "东盟制造", x: 780, y: 340, path: "M720 280 L820 280 L840 380 L740 400 Z" },
  { region_key: "australia", label: "澳洲矿产", x: 880, y: 480, path: "M800 420 L940 400 L960 500 L840 540 Z" }
];

export function WorldIndustryHeatMap({ geo, selectedNode }: WorldIndustryHeatMapProps) {
  const regions = useMemo(() => buildRegions(geo?.regions ?? []), [geo?.regions]);
  const routes = useMemo(() => buildRoutes(geo?.routes ?? [], regions), [geo?.routes, regions]);
  const [hoveredReg, setHoveredReg] = useState<string | null>(null);

  return (
    <div className="grid items-start gap-8 xl:grid-cols-[1fr_400px]">
      <div className="relative bg-white rounded-[40px] border border-slate-200 overflow-hidden shadow-2xl h-[680px]">
        {/* 数字地图背景：精细点阵 */}
        <div className="absolute inset-0 opacity-[0.05] pointer-events-none" 
             style={{ backgroundImage: 'radial-gradient(#000 1.5px, transparent 0)', backgroundSize: '24px 24px' }} />
        
        <svg viewBox="0 0 1000 620" className="block w-full h-full select-none">
          <defs>
            <filter id="hub-shadow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="12" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <linearGradient id="route-grad" x1="0%" y1="0%" x2="100%" y2="0%">
               <stop offset="0%" stopColor="#eab308" />
               <stop offset="100%" stopColor="#ef4444" />
            </linearGradient>
          </defs>

          {/* 抽象陆地轮廓 */}
          <g fill="#f1f5f9" stroke="#e2e8f0" strokeWidth="1">
            {REGION_ATLAS.map((reg) => (
              <path key={`bg-${reg.region_key}`} d={reg.path} className="transition-colors duration-500 hover:fill-slate-100" />
            ))}
          </g>

          {/* 供应链流动路径 */}
          <g>
            {routes.map((route, idx) => (
              <motion.path
                key={`r-${idx}`}
                d={routePath(route.from, route.to)}
                fill="none"
                stroke="url(#route-grad)"
                strokeWidth={1.5 + route.intensity * 2}
                strokeDasharray="6 8"
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 0.35 }}
                transition={{ duration: 2, delay: idx * 0.1 }}
              />
            ))}
          </g>

          {/* 核心地理热力锚点 - 实用性强化：标签常亮 */}
          {regions.map((reg) => {
            const hColor = heatColor(reg.intensityValue);
            const active = hoveredReg === reg.region_key;
            
            return (
              <motion.g
                key={reg.region_key}
                onMouseEnter={() => setHoveredReg(reg.region_key)}
                onMouseLeave={() => setHoveredReg(null)}
                className="cursor-pointer"
                animate={{ scale: active ? 1.1 : 1 }}
              >
                {/* 扩散呼吸环 */}
                <motion.circle
                  cx={reg.x} cy={reg.y}
                  r={(18 + reg.intensityValue * 35) * 1.5}
                  fill={hColor}
                  animate={{ opacity: [0.03, 0.15, 0.03], scale: [0.9, 1.1, 0.9] }}
                  transition={{ duration: 3, repeat: Infinity }}
                />
                
                {/* 中心实心站点 */}
                <circle cx={reg.x} cy={reg.y} r={14 + reg.intensityValue * 16} fill="white" stroke={hColor} strokeWidth="3" className="shadow-lg" />
                <circle cx={reg.x} cy={reg.y} r={6 + reg.intensityValue * 8} fill={hColor} />
                
                {/* 地理位置标签 - 实用性：增加常亮背景板 */}
                <g transform={`translate(${reg.x} ${reg.y - (30 + reg.intensityValue * 15)})`}>
                   <rect
                     x={-55} y={-16} width={110} height={32} rx={16}
                     fill="white"
                     stroke={active ? hColor : "#f1f5f9"}
                     strokeWidth={active ? 2.5 : 1}
                     className="shadow-2xl transition-all"
                   />
                   <text textAnchor="middle" y={1} fill="#0f172a" fontSize="11" fontWeight="900" className="uppercase tracking-tighter">{reg.label}</text>
                   <text textAnchor="middle" y={12} fill={hColor} fontSize="10" fontWeight="900" className="tabular-nums">{reg.heatValue.toFixed(1)}</text>
                </g>
              </motion.g>
            );
          })}
        </svg>

        {/* 顶部状态条 */}
        <div className="absolute top-10 left-10 flex items-center gap-6 bg-white/90 backdrop-blur-xl border border-slate-200 px-8 py-5 rounded-[24px] shadow-2xl">
           <div className="flex items-center gap-4">
             <div className="h-3 w-3 rounded-full bg-red-500 animate-pulse" />
             <div>
               <div className="text-[10px] font-black text-slate-400 uppercase tracking-widest leading-none mb-1">Live Intelligence</div>
               <div className="text-sm font-black text-slate-900">GLOBAL PRODUCTION MESH ACTIVE</div>
             </div>
           </div>
           <div className="h-8 w-[1px] bg-slate-200" />
           <div className="flex flex-col">
              <span className="text-[10px] font-black text-slate-400 uppercase">Strategic Regions</span>
              <span className="text-sm font-black italic">{regions.length} Nodes</span>
           </div>
        </div>
      </div>

      {/* 侧边深度分析面板 */}
      <aside className="space-y-6 h-[680px] overflow-y-auto no-scrollbar">
        <div className="bg-white border border-slate-200 p-8 rounded-[40px] shadow-xl">
          <div className="flex items-center justify-between mb-8">
            <h4 className="text-md font-black uppercase tracking-widest text-slate-900 flex items-center gap-3">
              <Zap size={20} className="text-orange-500" />
              热度区域排行
            </h4>
            <div className="p-2.5 rounded-xl bg-slate-900 text-white shadow-lg"><Navigation size={18} /></div>
          </div>
          
          <div className="space-y-4">
            {regions.map((reg, idx) => {
              const hColor = heatColor(reg.intensityValue);
              const active = hoveredReg === reg.region_key;
              
              return (
                <div 
                  key={reg.region_key}
                  onMouseEnter={() => setHoveredReg(reg.region_key)}
                  onMouseLeave={() => setHoveredReg(null)}
                  className={cn(
                    "group p-6 rounded-[28px] border transition-all cursor-pointer relative overflow-hidden",
                    active ? "bg-slate-900 border-slate-900 shadow-2xl scale-[1.03]" : "bg-slate-50 border-slate-100 hover:bg-white hover:border-orange-200"
                  )}
                >
                  <div className="flex items-start justify-between mb-4 relative z-10">
                    <div className="flex items-center gap-4">
                      <div className="text-[10px] font-black text-slate-400 w-5">0{idx + 1}</div>
                      <span className={cn("text-md font-black tracking-tight", active ? "text-white" : "text-slate-900")}>{reg.label}</span>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-black tabular-nums" style={{ color: active ? 'white' : hColor }}>{reg.heatValue.toFixed(1)}</div>
                      <div className={cn("text-[8px] font-black uppercase tracking-widest", active ? "text-slate-500" : "text-slate-400")}>Intensity</div>
                    </div>
                  </div>
                  
                  {/* 热力深度可视化 */}
                  <div className="relative h-2 w-full bg-slate-200 rounded-full overflow-hidden mb-5 z-10">
                    <motion.div 
                      className="absolute left-0 top-0 h-full rounded-full shadow-[0_0_10px_rgba(0,0,0,0.2)]" 
                      style={{ backgroundColor: hColor }}
                      initial={{ width: 0 }}
                      animate={{ width: `${reg.intensityValue * 100}%` }}
                    />
                  </div>

                  <div className={cn("text-[11px] font-bold leading-relaxed mb-4 relative z-10", active ? "text-slate-400" : "text-slate-500")}>
                    {reg.summary || "正在实时分析该区域的产业链分布密度与资本流入效率..."}
                  </div>
                  
                  {reg.hubs && (
                    <div className="flex flex-wrap gap-2 relative z-10">
                       {reg.hubs.slice(0, 3).map(hub => (
                         <span key={hub} className={cn("px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border", active ? "bg-white/10 border-white/20 text-white" : "bg-white border-slate-200 text-slate-600")}>
                           {hub}
                         </span>
                       ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          
          <div className="mt-10 p-6 rounded-3xl bg-orange-50 border border-orange-100 flex items-center gap-4">
             <Info className="text-orange-600 shrink-0" size={24} />
             <p className="text-[11px] font-bold text-orange-800 leading-relaxed">
               数据基于全球 48 个主要市场 24,000+ 家核心制造企业的地理定位与财务变动深度挖掘而成。
             </p>
          </div>
        </div>
      </aside>
    </div>
  );
}

// Logic implementations

function buildRegions(source: ChainRegion[]) {
  const sourceMap = new Map(source.map(r => [r.region_key, r]));
  const regions = REGION_ATLAS.map(atlas => {
    const r = sourceMap.get(atlas.region_key);
    const heatValue = Math.max(r?.heat ?? 0, (r?.intensity ?? 0) * 100, r?.share ?? 0);
    return { ...atlas, ...r, heatValue, intensityValue: 0 } as RenderRegion;
  }).filter(r => r.heatValue > 0 || r.summary);

  const maxHeat = Math.max(...regions.map(r => r.heatValue), 1);
  return regions.map(r => ({ ...r, intensityValue: Math.min(normalize(r.intensity, r.heatValue / maxHeat), 1) }))
                .sort((a,b) => b.heatValue - a.heatValue);
}

function buildRoutes(routes: ChainRoute[], regions: RenderRegion[]) {
  const regionMap = new Map(regions.map(r => [r.region_key, r]));
  return routes.flatMap(r => {
    const from = regionMap.get(r.from_key);
    const to = regionMap.get(r.to_key);
    if (!from || !to) return [];
    const intensity = Math.min(Math.max(normalize(r.intensity), normalize(r.heat), from.intensityValue, to.intensityValue), 1);
    return [{ from, to, intensity }];
  });
}

function routePath(from: RenderRegion, to: RenderRegion) {
  const midX = (from.x + to.x) / 2;
  const lift = Math.abs(to.x - from.x) * 0.15 + 45;
  return `M${from.x},${from.y}Q${midX},${Math.min(from.y, to.y) - lift} ${to.x},${to.y}`;
}

function heatColor(i: number) {
  if (i >= 0.8) return "#ef4444";
  if (i >= 0.45) return "#f97316";
  return "#eab308";
}

function normalize(v?: number | null, fallback = 0) {
  if (typeof v === 'number' && !isNaN(v)) return v > 1 ? v/100 : v;
  return fallback;
}
