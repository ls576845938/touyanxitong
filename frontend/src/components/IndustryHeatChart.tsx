"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { IndustryRadarRow } from "@/lib/api";

export function IndustryHeatChart({ rows }: { rows: IndustryRadarRow[] }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      grid: { left: 40, right: 20, top: 28, bottom: 50 },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.name),
        axisLabel: { interval: 0, rotate: 28 }
      },
      yAxis: { type: "value", name: "热度分" },
      series: [
        {
          type: "bar",
          data: rows.map((row) => row.heat_score),
          itemStyle: { color: "#2e7d6f", borderRadius: [4, 4, 0, 0] }
        }
      ]
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [rows]);

  return <div ref={ref} className="h-[360px] w-full" />;
}
