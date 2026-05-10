export const MARKET_LABELS: Record<string, string> = {
  ALL: "全市场",
  A: "A股",
  US: "美股",
  HK: "港股"
};

export const BOARD_LABELS: Record<string, string> = {
  all: "全部",
  main: "主板",
  chinext: "创业板",
  star: "科创板",
  bse: "北交所",
  nasdaq: "NASDAQ",
  nyse: "NYSE",
  amex: "AMEX",
  us: "美股",
  hk_main: "港股主板",
  hk_gem: "港股 GEM",
  etf: "ETF",
  adr: "ADR"
};

export const MARKET_OPTIONS = ["ALL", "A", "US", "HK"];
export const A_BOARD_OPTIONS = ["all", "main", "chinext", "star", "bse"];

export function marketLabel(value: string) {
  return MARKET_LABELS[value] ?? value;
}

export function boardLabel(value: string) {
  return BOARD_LABELS[value] ?? value;
}
