"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { IndustryTimelineItem } from "@/lib/api";

export function IndustryTimelineChart({ rows }: { rows: IndustryTimelineItem[] }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const ordered = [...rows].reverse();
    
    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 50, right: 50, top: 40, bottom: 40, containLabel: true },
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
        icon: "circle"
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
      yAxis: [
        { 
          type: "value", 
          name: "总热度",
          nameTextStyle: { color: "#94a3b8", fontWeight: "bold", fontSize: 10 },
          splitLine: { lineStyle: { color: "#f1f5f9" } },
          axisLabel: { color: "#94a3b8", fontWeight: "bold" }
        },
        { 
          type: "value", 
          name: "赛道数",
          nameTextStyle: { color: "#94a3b8", fontWeight: "bold", fontSize: 10 },
          splitLine: { show: false },
          axisLabel: { color: "#94a3b8", fontWeight: "bold" }
        }
      ],
      series: [
        {
          name: "总热度",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.summary.total_heat_score),
          lineStyle: { width: 4, color: "#4f46e5" },
          itemStyle: { color: "#4f46e5" },
          areaStyle: { 
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(79, 70, 229, 0.1)" },
              { offset: 1, color: "rgba(79, 70, 229, 0)" }
            ]) 
          },
          symbolSize: 8,
          emphasis: { scale: 1.5 }
        },
        {
          name: "升温赛道",
          type: "bar",
          yAxisIndex: 1,
          stack: "trend",
          data: ordered.map((row) => row.summary.rising_count),
          itemStyle: { color: "#ef4444", borderRadius: [4, 4, 0, 0] },
          barWidth: "20%"
        },
        {
          name: "降温赛道",
          type: "bar",
          yAxisIndex: 1,
          stack: "trend",
          data: ordered.map((row) => row.summary.cooling_count),
          itemStyle: { color: "#eab308", borderRadius: [0, 0, 4, 4] },
          barWidth: "20%"
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

  return <div ref={ref} className="h-[340px] w-full" />;
}
