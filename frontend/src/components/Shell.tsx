"use client";

import { usePathname } from "next/navigation";
import { BarChart3, ClipboardCheck, Database, FileText, Flame, Gauge, Layers3, Map as MapIcon, Repeat2, Search, TrendingUp } from "lucide-react";
import { StockSearch } from "@/components/StockSearch";

const navItems = [
  { href: "/", label: "Dashboard", icon: Gauge },
  { href: "/universe", label: "证券主数据", icon: Database },
  { href: "/industry", label: "产业雷达", icon: Layers3 },
  { href: "/industry/chain", label: "产业链地图", icon: MapIcon },
  { href: "/industry/review", label: "赛道复盘", icon: Flame },
  { href: "/trend", label: "趋势池", icon: BarChart3 },
  { href: "/watchlist", label: "观察池复盘", icon: Repeat2 },
  { href: "/research", label: "研究任务", icon: ClipboardCheck },
  { href: "/research/hot-terms", label: "热词雷达", icon: TrendingUp },
  { href: "/stocks/300308", label: "单股证据链", icon: Search },
  { href: "/report", label: "每日简报", icon: FileText }
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const activeHref = navItems
    .filter((item) => item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  return (
    <div className="app-shell">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex w-[min(1440px,calc(100vw-32px))] flex-wrap items-center justify-between gap-3 py-4">
          <div>
            <div className="text-xl font-semibold tracking-normal">AlphaRadar</div>
            <div className="label mt-1">AI 产业趋势雷达与早期特征观察系统</div>
          </div>
          <div className="w-full md:w-80 lg:w-96">
            <StockSearch compact placeholder="搜索 A股 / 港股 / 美股" />
          </div>
          <nav className="relative z-50 flex flex-wrap items-center gap-2">
            {navItems.map((item) => {
              const active = item.href === activeHref;
              const Icon = item.icon;
              return (
                <a
                  key={item.href}
                  href={item.href}
                  className={`flex h-10 items-center gap-2 rounded-md border px-3 text-sm ${
                    active
                      ? "border-mint bg-mint text-white"
                      : "border-line bg-white text-ink hover:border-mint"
                  }`}
                >
                  <Icon size={16} aria-hidden="true" />
                  <span>{item.label}</span>
                </a>
              );
            })}
          </nav>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
