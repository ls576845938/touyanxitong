"use client";

import { motion } from "framer-motion";
import { AlertCircle } from "lucide-react";

export function ErrorState({ message }: { message: string }) {
  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-4 rounded-xl border border-rose-100 bg-rose-50/50 p-6 shadow-sm"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600">
        <AlertCircle size={20} />
      </div>
      <div>
        <h3 className="text-sm font-bold text-rose-900">数据加载失败</h3>
        <p className="mt-1 text-sm leading-relaxed text-rose-600/80">
          {message}
        </p>
      </div>
    </motion.div>
  );
}
