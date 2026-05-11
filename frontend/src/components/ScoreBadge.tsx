"use client";

import { motion } from "framer-motion";

export function ScoreBadge({ score, rating }: { score: number | null; rating: string | null }) {
  const value = score ?? 0;
  
  // High-contrast scale: #eab308 (amber) -> #f97316 (orange) -> #ef4444 (red)
  let colors = "bg-slate-50 text-slate-500 border-slate-200";
  let dotColor = "bg-slate-400";
  
  if (value >= 85) {
    colors = "bg-red-50 text-[#ef4444] border-red-100";
    dotColor = "bg-[#ef4444]";
  } else if (value >= 75) {
    colors = "bg-orange-50 text-[#f97316] border-orange-100";
    dotColor = "bg-[#f97316]";
  } else if (value >= 60) {
    colors = "bg-amber-50 text-[#eab308] border-amber-100";
    dotColor = "bg-[#eab308]";
  }

  return (
    <motion.span 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`inline-flex min-w-[85px] items-center justify-between rounded-md border px-2.5 py-1 text-[11px] font-black tracking-tighter shadow-sm uppercase ${colors}`}
    >
      <span>{rating ?? "N/A"}</span>
      <div className="flex items-center gap-1.5 ml-2">
        <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
        <span className="mono">{score === null ? "--" : value.toFixed(1)}</span>
      </div>
    </motion.span>
  );
}
