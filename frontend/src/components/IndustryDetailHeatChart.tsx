"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { IndustryTimelineRow } from "@/lib/api";

export function IndustryDetailHeatChart({ rows }: { rows: IndustryTimelineRow[] }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const ordered = [...rows].reverse();
    chart.setOption({
      grid: { left: 44, right: 24, top: 34, bottom: 38 },
      tooltip: { trigger: "axis" },
      legend: { top: 4, right: 8 },
      xAxis: { type: "category", data: ordered.map((row) => row.trade_date) },
      yAxis: { type: "value", name: "热度" },
      series: [
        {
          name: "热度分",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.heat_score),
          lineStyle: { width: 3, color: "#2e7d6f" },
          itemStyle: { color: "#2e7d6f" }
        },
        {
          name: "7日热度",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.heat_7d),
          lineStyle: { width: 2, color: "#d79b2b" },
          itemStyle: { color: "#d79b2b" }
        },
        {
          name: "30日热度",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.heat_30d),
          lineStyle: { width: 2, color: "#c94d5d" },
          itemStyle: { color: "#c94d5d" }
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

  return <div ref={ref} className="h-[320px] w-full" />;
}
