import type { IndustryRadarRow, IndustryTimelineRow } from "@/lib/api";

export type IndustryHeatLike = Pick<
  IndustryRadarRow | IndustryTimelineRow,
  "industry_id" | "name" | "heat_score" | "heat_change_7d" | "heat_change_30d"
> & {
  trend_breadth?: number | null;
  breakout_breadth?: number | null;
  trade_date?: string | null;
};

export function industryMomentum(row: IndustryHeatLike | undefined): number {
  if (!row) return 0;
  const sevenDayDelta = finite(row.heat_change_7d) ? Math.max(row.heat_change_7d, 0) : 0;
  const thirtyDayDelta = finite(row.heat_change_30d) ? Math.max(row.heat_change_30d, 0) : 0;
  const trendBreadth = finite(row.trend_breadth) ? row.trend_breadth : 0;
  const breakoutBreadth = finite(row.breakout_breadth) ? row.breakout_breadth : 0;
  return Math.max(0, row.heat_score + sevenDayDelta * 1.8 + thirtyDayDelta * 0.45 + trendBreadth * 24 + breakoutBreadth * 18);
}

export function heatColor(intensity: number): string {
  if (intensity >= 0.82) return "#b91c1c";
  if (intensity >= 0.62) return "#ef4444";
  if (intensity >= 0.38) return "#f97316";
  if (intensity >= 0.16) return "#facc15";
  return "#fde68a";
}

export function heatLabel(intensity: number): string {
  if (intensity >= 0.82) return "极热";
  if (intensity >= 0.62) return "高热";
  if (intensity >= 0.38) return "升温";
  if (intensity >= 0.16) return "温和";
  return "冷却";
}

export function heatByName(rows: IndustryHeatLike[]): Map<string, IndustryHeatLike> {
  return new Map(rows.map((row) => [row.name, row]));
}

export function heatById(rows: IndustryHeatLike[]): Map<number, IndustryHeatLike> {
  return new Map(rows.map((row) => [row.industry_id, row]));
}

export function normalizedMomentum(rows: IndustryHeatLike[]): Map<number, number> {
  const metrics = rows.map((row) => [row.industry_id, industryMomentum(row)] as const);
  const maxMetric = Math.max(...metrics.map(([, metric]) => metric), 1);
  return new Map(metrics.map(([industryId, metric]) => [industryId, metric / maxMetric]));
}

function finite(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
