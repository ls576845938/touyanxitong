"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  BarChart3,
  ClipboardCheck,
  Database,
  FileText,
  Crosshair,
  Gauge,
  Network,
  LayoutGrid,
  Activity,
  Share2,
  Bot,
  Eye,
  ChevronDown,
  Search
} from "lucide-react";
import { motion } from "framer-motion";
import { StockSearch } from "@/components/StockSearch";
import { useState } from "react";

const PRIMARY_NAV_ITEMS = [
  { href: "/dashboard", label: "总览", icon: Gauge },
  { href: "/agent", label: "投研Agent", icon: Bot },
  { href: "/trend", label: "个股", icon: Search },
  { href: "/watchlist", label: "观察池", icon: Eye },
];

const SECONDARY_NAV_ITEMS = [
  { href: "/research/ai-big-graph", label: "AI大图谱", icon: Share2 },
  { href: "/research/thesis", label: "逻辑狙击", icon: Crosshair },
  { href: "/research", label: "研究任务", icon: ClipboardCheck },
  { href: "/research/ai-infra-map", label: "深度图谱", icon: Network },
  { href: "/universe", label: "证券库", icon: Database },
  { href: "/portfolio/dashboard", label: "组合", icon: BarChart3 },
  { href: "/report", label: "简报", icon: FileText }
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [showMore, setShowMore] = useState(false);

  const allNavItems = [...PRIMARY_NAV_ITEMS, ...SECONDARY_NAV_ITEMS];
  const activeHref = allNavItems
    .filter((item) => item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  useEffect(() => {
    const id = window.setTimeout(() => {
      for (const item of allNavItems) {
        if (item.href !== pathname) router.prefetch(item.href);
      }
    }, 800);
    return () => window.clearTimeout(id);
  }, [pathname, router]);

  function NavIcon({ item }: { item: typeof PRIMARY_NAV_ITEMS[0] }) {
    const active = item.href === activeHref;
    const Icon = item.icon;
    return (
      <Link
        key={item.href}
        href={item.href}
        prefetch
        onMouseEnter={() => router.prefetch(item.href)}
        title={item.label}
        className={`group relative flex h-12 w-12 items-center justify-center rounded-xl transition-all duration-200 ${
          active
            ? "bg-slate-100 text-slate-900 shadow-inner"
            : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
        }`}
      >
        <Icon size={20} strokeWidth={active ? 2.5 : 2} />
        {active && (
          <motion.div
            layoutId="sidebar-active"
            className="absolute left-0 h-6 w-1 rounded-r-full bg-slate-900"
          />
        )}
        <div className="absolute left-16 hidden group-hover:block z-50">
           <div className="bg-slate-900 text-white text-[10px] font-bold px-2 py-1 rounded shadow-lg whitespace-nowrap">
              {item.label}
           </div>
        </div>
      </Link>
    );
  }

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      {/* Sidebar Navigation */}
      <aside className="fixed inset-y-0 left-0 z-50 w-20 flex-col border-r border-slate-200 bg-white hidden md:flex">
        <div className="flex h-16 items-center justify-center border-b border-slate-100">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white shadow-sm">
            <LayoutGrid size={20} />
          </div>
        </div>
        <nav className="flex flex-1 flex-col items-center gap-3 py-6">
          {PRIMARY_NAV_ITEMS.map((item) => (
            <NavIcon key={item.href} item={item} />
          ))}

          {/* Separator */}
          <div className="my-1 h-px w-8 bg-slate-200" />

          {/* Secondary Nav with toggle */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowMore(!showMore)}
              title={showMore ? "收起更多" : "更多功能"}
              className={`group relative flex h-12 w-12 items-center justify-center rounded-xl transition-all duration-200 ${
                !activeHref || PRIMARY_NAV_ITEMS.some((p) => p.href === activeHref)
                  ? "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
                  : "bg-slate-100 text-slate-900 shadow-inner"
              }`}
            >
              <ChevronDown size={18} strokeWidth={2} className={`transition-transform ${showMore ? 'rotate-180' : ''}`} />
              <div className="absolute left-16 hidden group-hover:block z-50">
                 <div className="bg-slate-900 text-white text-[10px] font-bold px-2 py-1 rounded shadow-lg whitespace-nowrap">
                    {showMore ? "收起更多" : "更多"}
                 </div>
              </div>
            </button>

            {/* Dropdown for More items */}
            {showMore && (
              <div className="absolute left-16 top-0 z-50 w-48 rounded-xl border border-slate-200 bg-white py-2 shadow-xl">
                <div className="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400 border-b border-slate-100">
                  更多功能
                </div>
                {SECONDARY_NAV_ITEMS.map((item) => {
                  const active = item.href === activeHref;
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setShowMore(false)}
                      className={`flex items-center gap-3 px-4 py-2.5 text-xs font-bold transition-colors ${
                        active
                          ? "bg-slate-100 text-slate-900"
                          : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                      }`}
                    >
                      <Icon size={16} strokeWidth={active ? 2.5 : 2} />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </nav>
        <div className="border-t border-slate-100 p-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
             <Activity size={18} />
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col md:pl-20">
        <header className="sticky top-0 z-[60] border-b border-slate-200 bg-white/80 backdrop-blur-md">
          <div className="flex h-16 w-full items-center justify-between gap-8 px-8">
            <div className="flex items-center gap-6">
              <div>
                <div className="text-sm font-black tracking-tight text-slate-900">ALPHA RADAR</div>
                <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">Terminal v2.0</div>
              </div>
              
              <div className="h-6 w-px bg-slate-200 mx-2" />

              <div className="flex items-center gap-3 rounded-full bg-slate-50 px-3 py-1.5 border border-slate-100">
                <div className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </div>
                <span className="text-[10px] font-black uppercase tracking-wider text-slate-600">Research Loop</span>
                <span className="text-[11px] font-bold text-slate-900 mono">Thesis / Gate / Backtest</span>
              </div>
            </div>

            <div className="max-w-md flex-1">
              <StockSearch compact />
            </div>

            <div className="flex items-center gap-4">
               <div className="text-right">
                  <div className="text-[10px] font-black uppercase text-slate-400 leading-none">Status</div>
                  <div className="text-[11px] font-bold text-slate-900">Gate Active</div>
               </div>
               <div className="h-8 w-8 rounded-full bg-slate-100 border border-slate-200" />
            </div>
          </div>
        </header>

        <main className="flex-1 p-8">
          {children}
        </main>
        
        <footer className="border-t border-slate-200 bg-white py-8 px-8">
          <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
            <div>
              <div className="text-xs font-bold text-slate-900">AlphaRadar Executive</div>
              <p className="mt-1 text-[10px] text-slate-500 uppercase tracking-wider">AI-Powered Industrial Intelligence System</p>
            </div>
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
              © 2024 ALPHA RADAR LABS. 
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
