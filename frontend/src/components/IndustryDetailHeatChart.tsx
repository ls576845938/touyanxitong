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
      backgroundColor: "transparent",
      grid: { left: 40, right: 30, top: 40, bottom: 40, containLabel: true },
      tooltip: { 
        trigger: "axis",
        backgroundColor: "rgba(255, 255, 255, 0.9)",
        borderColor: "#f1f5f9",
        borderWidth: 1,
        textStyle: { color: "#0f172a", fontWeight: "bold" },
        extraCssText: "box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); border-radius: 12px;"
      },
      legend: { 
        top: 0, 
        right: 20,
        textStyle: { color: "#64748b", fontWeight: "bold", fontSize: 11 },
        icon: "roundRect"
      },
      xAxis: {
        type: "category",
        data: ordered.map((row) => row.trade_date),
        axisLabel: { 
          color: "#94a3b8", 
          fontWeight: "bold",
          fontSize: 10
        },
        axisLine: { lineStyle: { color: "#f1f5f9" } },
        axisTick: { show: false }
      },
      yAxis: { 
        type: "value", 
        name: "热度评分",
        nameTextStyle: { color: "#94a3b8", fontWeight: "bold", fontSize: 10 },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { color: "#94a3b8", fontWeight: "bold" }
      },
      series: [
        {
          name: "热度分",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.heat_score),
          lineStyle: { width: 4, color: "#ef4444" },
          itemStyle: { color: "#ef4444" },
          symbol: "circle",
          symbolSize: 6,
          emphasis: { scale: 1.5 }
        },
        {
          name: "7日热度",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.heat_7d),
          lineStyle: { width: 2.5, color: "#f97316", type: "dashed" },
          itemStyle: { color: "#f97316" },
          symbol: "none"
        },
        {
          name: "30日热度",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.heat_30d),
          lineStyle: { width: 2, color: "#eab308", opacity: 0.6 },
          itemStyle: { color: "#eab308" },
          symbol: "none"
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
