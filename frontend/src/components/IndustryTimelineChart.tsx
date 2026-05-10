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
      grid: { left: 44, right: 36, top: 36, bottom: 38 },
      tooltip: { trigger: "axis" },
      legend: { top: 4, right: 8 },
      xAxis: {
        type: "category",
        data: ordered.map((row) => row.trade_date),
        axisLabel: { interval: 0 }
      },
      yAxis: [
        { type: "value", name: "总热度" },
        { type: "value", name: "赛道数" }
      ],
      series: [
        {
          name: "总热度",
          type: "line",
          smooth: true,
          data: ordered.map((row) => row.summary.total_heat_score),
          lineStyle: { width: 3, color: "#2e7d6f" },
          itemStyle: { color: "#2e7d6f" },
          areaStyle: { color: "rgba(46,125,111,0.10)" }
        },
        {
          name: "升温赛道",
          type: "bar",
          yAxisIndex: 1,
          data: ordered.map((row) => row.summary.rising_count),
          itemStyle: { color: "#d79b2b", borderRadius: [4, 4, 0, 0] }
        },
        {
          name: "降温赛道",
          type: "bar",
          yAxisIndex: 1,
          data: ordered.map((row) => row.summary.cooling_count),
          itemStyle: { color: "#c94d5d", borderRadius: [4, 4, 0, 0] }
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
