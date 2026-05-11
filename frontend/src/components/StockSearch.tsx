"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2, ArrowRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { api, type InstrumentRow } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

export function StockSearch({ compact = false, placeholder = "搜索 A股 / 港股 / 美股" }: { compact?: boolean; placeholder?: string }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<InstrumentRow[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  const trimmed = useMemo(() => query.trim(), [query]);

  useEffect(() => {
    if (trimmed.length < 1) {
      setRows([]);
      setOpen(false);
      return;
    }
    const handle = window.setTimeout(() => {
      setLoading(true);
      api.instruments({ q: trimmed, limit: 10 })
        .then((payload) => {
          setRows(payload.rows);
          setOpen(true);
        })
        .catch(() => {
          setRows([]);
          setOpen(true);
        })
        .finally(() => setLoading(false));
    }, 180);
    return () => window.clearTimeout(handle);
  }, [trimmed]);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const goToStock = (code: string) => {
    setQuery("");
    setRows([]);
    setOpen(false);
    router.push(`/stocks/${encodeURIComponent(code)}?from=search`);
  };

  return (
    <div ref={ref} className={`relative ${compact ? "w-full" : "w-full"}`}>
      <div className="group relative flex h-11 items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 transition-all duration-200 focus-within:border-indigo-500 focus-within:ring-4 focus-within:ring-indigo-500/10 shadow-sm">
        <Search size={18} className="shrink-0 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => {
            if (rows.length || trimmed) setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && rows[0]) goToStock(rows[0].code);
          }}
          className="h-full min-w-0 flex-1 bg-transparent text-[14px] font-medium text-slate-900 placeholder:text-slate-400 outline-none"
          placeholder={placeholder}
        />
        {loading && <Loader2 size={16} className="animate-spin text-slate-400" />}
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 4, scale: 0.98 }}
            className="absolute left-0 right-0 top-[52px] z-[100] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-200/60"
          >
            <div className="p-2">
              {!loading && rows.length === 0 ? (
                <div className="px-4 py-8 text-center">
                  <p className="text-sm font-medium text-slate-500">未找到匹配的股票</p>
                  <p className="mt-1 text-xs text-slate-400">尝试输入代码或公司名称</p>
                </div>
              ) : null}
              
              {rows.map((row) => (
                <button
                  key={`${row.market}-${row.code}`}
                  type="button"
                  onClick={() => goToStock(row.code)}
                  className="group flex w-full items-center justify-between rounded-xl px-4 py-3 text-left transition-colors hover:bg-slate-50"
                >
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-slate-900">{row.name}</span>
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                        {row.code}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[11px] font-medium text-slate-500">
                      <span>{marketLabel(row.market)}</span>
                      <span className="h-1 w-1 rounded-full bg-slate-300" />
                      <span>{boardLabel(row.board)}</span>
                      <span className="h-1 w-1 rounded-full bg-slate-300" />
                      <span>{row.industry_level1 || "未分类"}</span>
                    </div>
                  </div>
                  <ArrowRight size={16} className="text-slate-300 transition-transform group-hover:translate-x-1 group-hover:text-indigo-500" />
                </button>
              ))}
            </div>
            {rows.length > 0 && (
              <div className="bg-slate-50 px-4 py-2 border-t border-slate-100">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">
                  找到 {rows.length} 个结果
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
