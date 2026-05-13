"use client";

import { useEffect, useRef } from "react";
import { createChart, type IChartApi, ColorType } from "lightweight-charts";
import type { BarRow } from "@/lib/api";

// ---------------------------------------------------------------------------
// Chart export registry (shared across chart components)
// ---------------------------------------------------------------------------
export type ChartCaptureFn = () => string | undefined;

const _chartRegistry = new Map<string, ChartCaptureFn>();

export function registerChartCapture(id: string, fn: ChartCaptureFn): () => void {
  _chartRegistry.set(id, fn);
  return () => { _chartRegistry.delete(id); };
}

export function captureAllChartDataUrls(): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [id, fn] of _chartRegistry) {
    try {
      const url = fn();
      if (url) result[id] = url;
    } catch {
      // skip failed captures
    }
  }
  return result;
}

export function CandleChart({ rows, chartId }: { rows: BarRow[]; chartId?: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current || rows.length === 0) return;

    const chart = createChart(ref.current, {
      height: 400,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#0f172a", // slate-900
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#f1f5f9" }, // slate-100
        horzLines: { color: "#f1f5f9" }  // slate-100
      },
      rightPriceScale: { 
        borderColor: "#e2e8f0", // slate-200
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
      },
      timeScale: { 
        borderColor: "#e2e8f0", // slate-200
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
    });

    chartRef.current = chart;

    // Register for chart export
    const unregister = chartId
      ? registerChartCapture(chartId, () => {
          const canvas = chart.takeScreenshot();
          return canvas ? canvas.toDataURL("image/png") : undefined;
        })
      : null;

    const series = chart.addCandlestickSeries({
      upColor: "#ef4444",    // red-500 (Up in China context)
      downColor: "#10b981",  // emerald-500 (Down in China context)
      borderVisible: false,
      wickUpColor: "#ef4444",
      wickDownColor: "#10b981"
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
      if (unregister) unregister();
      chart.remove();
      chartRef.current = null;
    };
  }, [rows, chartId]);

  if (rows.length === 0) {
    return (
      <div className="flex h-[400px] w-full items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-sm text-slate-400">
        暂无可展示 K 线数据
      </div>
    );
  }

  return <div ref={ref} className="h-[400px] w-full" />;
}
