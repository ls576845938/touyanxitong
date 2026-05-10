"use client";

import { useEffect, useRef } from "react";
import { createChart, type IChartApi } from "lightweight-charts";
import type { BarRow } from "@/lib/api";

export function CandleChart({ rows }: { rows: BarRow[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current || rows.length === 0) return;
    const chart = createChart(ref.current, {
      height: 380,
      layout: {
        background: { color: "#ffffff" },
        textColor: "#172026"
      },
      grid: {
        vertLines: { color: "#edf2f1" },
        horzLines: { color: "#edf2f1" }
      },
      rightPriceScale: { borderColor: "#d9e2e0" },
      timeScale: { borderColor: "#d9e2e0" }
    });
    chartRef.current = chart;
    const series = chart.addCandlestickSeries({
      upColor: "#2e7d6f",
      downColor: "#a7434b",
      borderVisible: false,
      wickUpColor: "#2e7d6f",
      wickDownColor: "#a7434b"
    });
    const uniqueRows = Array.from(new Map(rows.map((row) => [row.time, row])).values()).sort((left, right) =>
      left.time.localeCompare(right.time)
    );
    series.setData(
      uniqueRows.map((row) => ({
        time: row.time,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close
      }))
    );
    chart.timeScale().fitContent();

    const resize = () => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth });
    };
    resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.remove();
      chartRef.current = null;
    };
  }, [rows]);

  if (rows.length === 0) {
    return (
      <div className="flex h-[380px] w-full items-center justify-center rounded-md border border-line bg-slate-50 text-sm text-slate-600">
        暂无可展示 K 线。请先对该标的运行行情批次下载。
      </div>
    );
  }

  return <div ref={ref} className="h-[380px] w-full" />;
}
