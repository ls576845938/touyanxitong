"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { api, type InstrumentRow } from "@/lib/api";
import { boardLabel, marketLabel } from "@/lib/markets";

export function StockSearch({ compact = false, placeholder = "搜索股票代码或名称" }: { compact?: boolean; placeholder?: string }) {
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
    <div ref={ref} className={`relative ${compact ? "w-full md:w-72" : "w-full"}`}>
      <div className="flex h-10 items-center gap-2 rounded-md border border-line bg-white px-3 focus-within:border-mint">
        <Search size={16} className="shrink-0 text-slate-400" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => {
            if (rows.length || trimmed) setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && rows[0]) goToStock(rows[0].code);
          }}
          className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none"
          placeholder={placeholder}
        />
      </div>
      {open ? (
        <div className="absolute left-0 right-0 top-12 z-30 max-h-96 overflow-y-auto rounded-md border border-line bg-white shadow-lg">
          {loading ? <div className="px-3 py-3 text-sm text-slate-600">搜索中...</div> : null}
          {!loading && rows.length === 0 ? <div className="px-3 py-3 text-sm text-slate-600">没有匹配股票。</div> : null}
          {rows.map((row) => (
            <button
              key={`${row.market}-${row.code}`}
              type="button"
              onClick={() => goToStock(row.code)}
              className="block w-full border-b border-line px-3 py-3 text-left text-sm last:border-0 hover:bg-slate-50"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium">{row.name}<span className="label ml-2">{row.code}</span></div>
                <div className="label">{row.bars_count} 根K线</div>
              </div>
              <div className="label mt-1">{marketLabel(row.market)} / {boardLabel(row.board)} / {row.industry_level1 || "未分类"}</div>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
