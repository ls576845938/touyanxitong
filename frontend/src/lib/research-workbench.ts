export type WorkbenchTone = "neutral" | "pass" | "warn" | "fail";

export type QualityFlag = "MOCK" | "FALLBACK" | "FAIL";

export type ObservationLevel = "重点观察" | "持续跟踪" | "仅作记录";

export type WorkbenchRecord = {
  date: string | null;
  title: string;
  detail: string;
  tone: WorkbenchTone;
  tags?: string[];
};

export function formatPct(value?: number | null, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSigned(value?: number | null, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  const normalized = value > 0 ? `+${value.toFixed(digits)}` : value.toFixed(digits);
  return normalized;
}

export function formatDate(value?: string | null): string {
  if (!value) return "--";
  return value;
}

export function formatCompactNumber(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits: value >= 100 ? 0 : 1
  }).format(value);
}

export function observationLevel(score?: number | null, confidence?: string | null): ObservationLevel {
  if ((score ?? 0) >= 75 && confidence === "high") return "重点观察";
  if ((score ?? 0) >= 55 || confidence === "medium") return "持续跟踪";
  return "仅作记录";
}

export function toneFromStatus(status?: string | null): WorkbenchTone {
  const normalized = (status ?? "").toUpperCase();
  if (normalized.includes("FAIL") || normalized.includes("BLOCK")) return "fail";
  if (normalized.includes("WARN") || normalized.includes("REVIEW")) return "warn";
  if (normalized.includes("PASS") || normalized.includes("READY") || normalized.includes("ACTIVE")) return "pass";
  return "neutral";
}

export function collectQualityFlags(...values: Array<string | boolean | null | undefined>): QualityFlag[] {
  const flags = new Set<QualityFlag>();
  for (const value of values) {
    if (value === null || value === undefined) continue;
    const normalized = String(value).toUpperCase();
    if (normalized.includes("MOCK")) flags.add("MOCK");
    if (normalized.includes("FALLBACK")) flags.add("FALLBACK");
    if (normalized.includes("FAIL")) flags.add("FAIL");
  }
  return Array.from(flags);
}

export function toneFromFlags(flags: QualityFlag[]): WorkbenchTone {
  if (flags.includes("FAIL") || flags.includes("MOCK") || flags.includes("FALLBACK")) return "fail";
  return "neutral";
}

export function riskPrompt(flags: QualityFlag[]): string {
  if (flags.includes("MOCK")) return "存在 mock 数据，仅可作为研究辅助草稿。";
  if (flags.includes("FALLBACK")) return "存在 fallback 数据，请回到原始信源复核。";
  if (flags.includes("FAIL")) return "存在数据质量 FAIL，禁止把摘要当成结论。";
  return "暂无显式数据质量阻断，仍需交叉验证。";
}

export function uniqueTexts(items: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of items) {
    const text = item?.trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
  }
  return result;
}
