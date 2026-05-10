"use client";

import { useEffect, useMemo, useState } from "react";
import { Globe2, MapPin, MoveRight } from "lucide-react";
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

const REGION_ATLAS: AtlasRegion[] = [
  { region_key: "north_america", label: "北美", x: 198, y: 186, path: "M74 124 C100 72 172 48 246 60 C304 70 348 100 372 150 C390 188 382 234 344 264 C312 288 282 278 256 300 C230 320 228 360 194 364 C162 368 138 344 122 314 C102 276 72 260 58 224 C44 188 52 152 74 124 Z" },
  { region_key: "latin_america", label: "拉美", x: 282, y: 390, path: "M276 308 C310 324 332 350 336 388 C340 430 324 482 300 530 C286 560 266 578 248 594 C238 552 220 514 208 468 C196 420 202 372 224 338 C236 320 250 306 276 308 Z" },
  { region_key: "europe", label: "欧洲", x: 490, y: 168, path: "M430 116 C454 94 494 88 528 94 C562 100 590 118 600 144 C608 168 592 188 564 194 C532 202 514 196 490 210 C464 224 432 214 420 188 C410 166 410 136 430 116 Z" },
  { region_key: "middle_east", label: "中东", x: 566, y: 238, path: "M536 198 C558 190 586 194 606 208 C624 222 628 250 616 272 C602 294 574 302 552 292 C530 282 516 258 516 238 C516 220 522 204 536 198 Z" },
  { region_key: "africa", label: "非洲", x: 520, y: 336, path: "M450 222 C486 204 542 210 586 236 C620 256 636 296 632 348 C628 408 590 466 528 490 C474 510 430 486 412 432 C398 388 400 338 410 292 C418 258 426 236 450 222 Z" },
  { region_key: "india", label: "印度", x: 646, y: 292, path: "M622 252 C640 240 664 240 684 248 C702 256 712 278 710 298 C708 320 694 340 674 350 C656 358 638 354 628 338 C614 316 610 286 622 252 Z" },
  { region_key: "china", label: "中国", x: 760, y: 210, path: "M654 106 C716 70 796 70 868 98 C922 118 954 154 958 202 C960 242 936 278 892 286 C844 294 816 318 774 324 C730 330 686 312 662 270 C638 226 628 162 654 106 Z" },
  { region_key: "developed_asia", label: "日韩台", x: 850, y: 170, path: "M820 116 C846 104 882 110 904 132 C924 152 924 182 904 202 C882 224 844 222 822 202 C800 180 796 130 820 116 Z" },
  { region_key: "asean", label: "东盟", x: 746, y: 316, path: "M700 266 C722 258 748 258 772 268 C794 278 808 296 810 318 C812 346 798 368 774 378 C748 390 722 386 706 366 C690 344 686 284 700 266 Z" },
  { region_key: "australia", label: "澳洲", x: 862, y: 458, path: "M792 398 C830 376 878 374 920 390 C950 402 970 424 972 454 C974 488 946 514 906 524 C864 536 816 528 790 506 C764 484 764 432 792 398 Z" }
];

export function WorldIndustryHeatMap({ geo, selectedNode }: WorldIndustryHeatMapProps) {
  const regions = useMemo(() => buildRegions(geo?.regions ?? []), [geo?.regions]);
  const routes = useMemo(() => buildRoutes(geo?.routes ?? [], regions), [geo?.routes, regions]);
  const [activeRegionKey, setActiveRegionKey] = useState<string | null>(regions[0]?.region_key ?? null);

  useEffect(() => {
    setActiveRegionKey(regions[0]?.region_key ?? null);
  }, [regions]);

  const activeRegion = regions.find((region) => region.region_key === activeRegionKey) ?? regions[0] ?? null;

  return (
    <div className="grid items-start gap-4 xl:grid-cols-[1.45fr_0.55fr]">
      <div className="overflow-hidden rounded-lg border border-[#f2dfd2] bg-white">
        <svg viewBox="0 0 1000 620" role="img" aria-label="世界产业分布热力图" className="block h-[620px] w-full">
          <defs>
            <linearGradient id="world-surface" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stopColor="#ffffff" />
              <stop offset="1" stopColor="#fffaf5" />
            </linearGradient>
            <linearGradient id="world-route" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0" stopColor="#facc15" />
              <stop offset="0.52" stopColor="#f97316" />
              <stop offset="1" stopColor="#dc2626" />
            </linearGradient>
            <filter id="world-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="14" stdDeviation="16" floodColor="#7c2d12" floodOpacity="0.08" />
            </filter>
          </defs>

          <rect width="1000" height="620" fill="url(#world-surface)" />
          <g opacity="0.88">
            {[102, 176, 250, 324, 398, 472, 546].map((y) => (
              <line key={`lat-${y}`} x1="40" x2="960" y1={y} y2={y} stroke="#f4ece5" strokeWidth="1" />
            ))}
            {[110, 220, 330, 440, 550, 660, 770, 880].map((x) => (
              <line key={`lon-${x}`} x1={x} x2={x} y1="54" y2="566" stroke="#f6ede6" strokeWidth="1" />
            ))}
          </g>

          <g fill="#fff6ed" stroke="#efdbc9" strokeWidth="1.2" filter="url(#world-shadow)">
            {REGION_ATLAS.map((region) => (
              <path key={region.region_key} d={region.path} />
            ))}
          </g>

          <g fill="none" stroke="#f0d8c7" strokeWidth="1" opacity="0.9">
            <path d="M86 162 C160 140 240 148 318 196" />
            <path d="M438 154 C478 170 534 172 592 152" />
            <path d="M670 140 C754 122 850 148 942 212" />
            <path d="M454 252 C508 286 550 350 560 420" />
            <path d="M706 286 C754 310 820 334 892 340" />
            <path d="M792 418 C838 428 884 436 944 444" />
          </g>

          <g fill="none">
            {routes.map((route) => (
              <path
                key={`${route.from.region_key}-${route.to.region_key}`}
                d={routePath(route.from, route.to)}
                stroke="url(#world-route)"
                strokeWidth={1.6 + route.intensity * 4.8}
                strokeOpacity={0.18 + route.intensity * 0.42}
                strokeDasharray="5 8"
                strokeLinecap="round"
              />
            ))}
          </g>

          <g>
            {regions.map((region) => {
              const color = warmColor(region.intensityValue);
              const active = activeRegion?.region_key === region.region_key;
              const rings = [2.3, 1.45, 0.66];
              return (
                <g
                  key={region.region_key}
                  role="button"
                  tabIndex={0}
                  onClick={() => setActiveRegionKey(region.region_key)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") setActiveRegionKey(region.region_key);
                  }}
                  className="cursor-pointer outline-none"
                >
                  {rings.map((ratio, index) => (
                    <circle
                      key={`${region.region_key}-ring-${ratio}`}
                      cx={region.x}
                      cy={region.y}
                      r={(16 + region.intensityValue * 30) * ratio}
                      fill={color}
                      opacity={index === 0 ? 0.08 : index === 1 ? 0.14 : 0.9}
                    />
                  ))}
                  <circle cx={region.x} cy={region.y} r="8" fill="#ffffff" opacity="0.9" />
                  <g transform={`translate(${region.x + (region.x > 770 ? -124 : 18)} ${region.y - (region.y < 120 ? -12 : 30)})`}>
                    <rect width="112" height="46" rx="10" fill="#ffffff" stroke={active ? color : "#f3dfd3"} strokeWidth={active ? 1.8 : 1} />
                    <text x="10" y="18" fill="#111827" fontSize="12.5" fontWeight="800">
                      {region.label}
                    </text>
                    <text x="10" y="34" fill={color} fontSize="11.5" fontWeight="700">
                      {region.heatValue.toFixed(1)}
                    </text>
                  </g>
                </g>
              );
            })}
          </g>

          <g transform="translate(46 576)">
            <rect width="310" height="28" rx="10" fill="#ffffff" stroke="#f2dfd2" />
            <LegendDot x={18} color="#facc15" label="温和" />
            <LegendDot x={88} color="#f59e0b" label="升温" />
            <LegendDot x={162} color="#ea580c" label="活跃" />
            <LegendDot x={234} color="#b91c1c" label="高热" />
          </g>
        </svg>
      </div>

      <div className="space-y-3">
        <div className="rounded-lg border border-[#f2dfd2] bg-white p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <Globe2 size={16} className="text-orange-600" />
            {selectedNode?.name ?? "区域热力"}
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {regions.length} 个区域
          </div>
        </div>

        {regions.map((region) => {
          const active = activeRegion?.region_key === region.region_key;
          const color = warmColor(region.intensityValue);
          return (
            <button
              key={region.region_key}
              type="button"
              onClick={() => setActiveRegionKey(region.region_key)}
              className={`w-full rounded-lg border p-3 text-left transition ${
                active ? "border-orange-500 bg-orange-50/70" : "border-[#f2dfd2] bg-white hover:border-orange-300"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 font-semibold text-slate-900">
                    <MapPin size={15} style={{ color }} />
                    {region.label}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{region.summary || `${region.country_count ?? 0} 个市场触点`}</div>
                </div>
                <span className="mono rounded-md px-2 py-1 text-xs font-semibold text-white" style={{ backgroundColor: color }}>
                  {region.heatValue.toFixed(1)}
                </span>
              </div>
              <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                <span>{region.hubs?.slice(0, 3).join(" / ") || "区域集群"}</span>
                <span>{formatPercent(region.share)}</span>
              </div>
            </button>
          );
        })}

        {activeRegion && routes.length ? (
          <div className="rounded-lg border border-[#f2dfd2] bg-white p-4">
            <div className="text-sm font-semibold text-slate-900">迁移路径</div>
            <div className="mt-3 space-y-2">
              {routes
                .filter((route) => route.from.region_key === activeRegion.region_key || route.to.region_key === activeRegion.region_key)
                .slice(0, 4)
                .map((route) => (
                  <div key={`${route.from.region_key}-${route.to.region_key}`} className="flex items-center justify-between text-xs text-slate-600">
                    <span className="inline-flex items-center gap-1">
                      {route.from.label}
                      <MoveRight size={12} className="text-orange-500" />
                      {route.to.label}
                    </span>
                    <span className="mono font-semibold text-orange-700">{route.intensity.toFixed(2)}</span>
                  </div>
                ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function LegendDot({ x, color, label }: { x: number; color: string; label: string }) {
  return (
    <g transform={`translate(${x} 14)`}>
      <circle cx="0" cy="0" r="5" fill={color} />
      <text x="11" y="4" fill="#6b7280" fontSize="11.5">
        {label}
      </text>
    </g>
  );
}

function buildRegions(source: ChainRegion[]) {
  const sourceMap = new Map(source.map((region) => [region.region_key, region]));
  const seeded = REGION_ATLAS.map<RenderRegion>((atlas) => {
    const region = sourceMap.get(atlas.region_key);
    const heatValue = Math.max(region?.heat ?? 0, (region?.intensity ?? 0) * 100, region?.share ?? 0);
    return {
      ...atlas,
      region_key: atlas.region_key,
      label: region?.label ?? atlas.label,
      heat: region?.heat,
      intensity: region?.intensity,
      share: region?.share,
      summary: region?.summary,
      country_count: region?.country_count,
      hubs: region?.hubs,
      industries: region?.industries,
      x: region?.x ?? atlas.x,
      y: region?.y ?? atlas.y,
      heatValue,
      intensityValue: 0
    };
  }).filter((region) => region.heatValue > 0 || region.summary || region.hubs?.length);

  const maxHeat = Math.max(...seeded.map((region) => region.heatValue), 1);
  return seeded
    .map((region) => ({
      ...region,
      intensityValue: Math.min(normalize(region.intensity, region.heatValue / maxHeat), 1)
    }))
    .sort((left, right) => right.heatValue - left.heatValue);
}

function buildRoutes(routes: ChainRoute[], regions: RenderRegion[]) {
  const regionMap = new Map(regions.map((region) => [region.region_key, region]));
  return routes.flatMap((route) => {
    const from = regionMap.get(route.from_key);
    const to = regionMap.get(route.to_key);
    if (!from || !to) return [];
    const intensity = Math.min(
      Math.max(normalize(route.intensity), normalize(route.heat), normalize(route.weight), from.intensityValue, to.intensityValue),
      1
    );
    return [{ from, to, intensity }];
  });
}

function routePath(from: RenderRegion, to: RenderRegion) {
  const midX = (from.x + to.x) / 2;
  const lift = Math.min(130, Math.abs(to.x - from.x) * 0.24 + 48);
  const controlY = Math.min(from.y, to.y) - lift;
  return `M ${from.x} ${from.y} Q ${midX} ${controlY} ${to.x} ${to.y}`;
}

function warmColor(intensity: number) {
  if (intensity >= 0.86) return "#b91c1c";
  if (intensity >= 0.64) return "#ea580c";
  if (intensity >= 0.38) return "#f59e0b";
  return "#facc15";
}

function normalize(primary?: number | null, fallback = 0) {
  if (typeof primary === "number" && !Number.isNaN(primary)) {
    return primary > 1 ? primary / 100 : primary;
  }
  return fallback;
}

function formatPercent(value?: number | null) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return `${value.toFixed(value > 1 ? 0 : 2)}${value > 1 ? "%" : ""}`;
}
