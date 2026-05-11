"use client";

import { motion } from "framer-motion";

export function LoadingState({ label = "正在加载数据" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12">
      <div className="relative flex h-10 w-10">
        <motion.span
          animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0.2, 0.5] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          className="absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"
        />
        <div className="relative inline-flex h-10 w-10 rounded-full bg-indigo-600 shadow-lg shadow-indigo-200" />
      </div>
      <motion.p 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mt-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400"
      >
        {label}
      </motion.p>
    </div>
  );
}
