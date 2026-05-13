"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { IndustryRadarRow } from "@/lib/api";
import { registerChartCapture } from "./CandleChart";

export function IndustryHeatChart({ rows, chartId }: { rows: IndustryRadarRow[]; chartId?: string }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);

    // Register for chart export
    const unregister = chartId
      ? registerChartCapture(chartId, () => chart.getDataURL({ type: "png", backgroundColor: "#fff" }))
      : null;

    const data = rows.map((row) => ({
      value: row.heat_score,
      itemStyle: {
        color: row.heat_score >= 80 ? "#ef4444" : row.heat_score >= 50 ? "#f97316" : "#eab308",
        borderRadius: [6, 6, 0, 0]
      }
    }));

    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 40, right: 20, top: 30, bottom: 60, containLabel: true },
      tooltip: { 
        trigger: "axis",
        backgroundColor: "rgba(255, 255, 255, 0.9)",
        borderColor: "#f1f5f9",
        borderWidth: 1,
        textStyle: { color: "#0f172a", fontWeight: "bold" },
        extraCssText: "box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); border-radius: 12px;"
      },
      xAxis: {
        type: "category",
        data: rows.map((row) => row.name),
        axisLabel: { 
          interval: 0, 
          rotate: 35,
          color: "#64748b",
          fontWeight: 600,
          fontSize: 10
        },
        axisLine: { lineStyle: { color: "#f1f5f9" } },
        axisTick: { show: false }
      },
      yAxis: { 
        type: "value", 
        name: "热度分",
        nameTextStyle: { color: "#94a3b8", fontWeight: "bold", fontSize: 10 },
        splitLine: { lineStyle: { color: "#f1f5f9" } },
        axisLabel: { color: "#94a3b8", fontWeight: "bold" }
      },
      series: [
        {
          type: "bar",
          data: data,
          barWidth: "40%",
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowOffsetX: 0,
              shadowColor: "rgba(0, 0, 0, 0.1)"
            }
          }
        }
      ]
    });
    
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      if (unregister) unregister();
      chart.dispose();
    };
  }, [rows, chartId]);

  return <div ref={ref} className="h-[360px] w-full" />;
}
