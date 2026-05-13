"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Shield,
  ShieldAlert,
  AlertTriangle,
  Loader2,
  Calculator,
  TrendingDown,
  BarChart3,
  Info,
  CheckCircle2,
  XCircle,
  Eye,
  ChevronDown,
  ChevronUp,
  Save
} from "lucide-react";
import { motion } from "framer-motion";
import {
  api,
  type PositionSizeRequest,
  type PositionSizeResponse,
  type PositionPlan,
  type ExposureData,
  type RiskPortfolio
} from "@/lib/api";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 }
};

function formatMoney(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  if (Math.abs(value) >= 10000) {
    return `¥${(value / 10000).toFixed(2)}万`;
  }
  return `¥${value.toFixed(2)}`;
}

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${(value * 100).toFixed(2)}%`;
}

function formatShares(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return value.toLocaleString("zh-CN");
}

function RiskPageContent() {
  const searchParams = useSearchParams();
  const symbolFromUrl = searchParams.get("symbol") || "";
  const nameFromUrl = searchParams.get("name") || "";

  // ===================================================================
  // Section 1: Position Size Calculator Form
  // ===================================================================
  const [accountEquity, setAccountEquity] = useState("");
  const [availableCash, setAvailableCash] = useState("");
  const [symbol, setSymbol] = useState(symbolFromUrl);
  const [entryPrice, setEntryPrice] = useState("");
  const [invalidationPrice, setInvalidationPrice] = useState("");
  const [riskPerTradePct, setRiskPerTradePct] = useState("1");
  const [maxSinglePosPct, setMaxSinglePosPct] = useState("");
  const [maxThemeExposurePct, setMaxThemeExposurePct] = useState("");
  const [currentDrawdownPct, setCurrentDrawdownPct] = useState("");
  const [market, setMarket] = useState("");
  const [lotSize, setLotSize] = useState("100");
  const [showExplain, setShowExplain] = useState(false);

  const [calculating, setCalculating] = useState(false);
  const [calcResult, setCalcResult] = useState<PositionSizeResponse | null>(null);
  const [calcError, setCalcError] = useState("");

  // ===================================================================
  // Section 2: Portfolio Exposure
  // ===================================================================
  const [portfolios, setPortfolios] = useState<RiskPortfolio[]>([]);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState<number | null>(null);
  const [exposureData, setExposureData] = useState<ExposureData | null>(null);
  const [exposureLoading, setExposureLoading] = useState(false);
  const [portfolioLoading, setPortfolioLoading] = useState(false);

  // ===================================================================
  // Section 3: Position Plans
  // ===================================================================
  const [plans, setPlans] = useState<PositionPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [plansError, setPlansError] = useState("");
  const [planStatusFilter, setPlanStatusFilter] = useState<string>("all");
  const [activatingId, setActivatingId] = useState<number | null>(null);
  const [archivingPlanId, setArchivingPlanId] = useState<number | null>(null);
  const [savingPlan, setSavingPlan] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // ===================================================================
  // Section 4: Drawdown Status (computed from input)
  // ===================================================================
  const drawdownPct = parseFloat(currentDrawdownPct) || 0;

  // ===================================================================
  // Effects
  // ===================================================================
  useEffect(() => {
    setPortfolioLoading(true);
    api.fetchPortfolios()
      .then((data) => {
        setPortfolios(data);
        if (data.length > 0) setSelectedPortfolioId(data[0].id);
      })
      .catch(() => {})
      .finally(() => setPortfolioLoading(false));

    loadPlans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedPortfolioId) {
      setExposureLoading(true);
      api.fetchExposure(selectedPortfolioId)
        .then((data) => {
          if (data) setExposureData(data);
          else setExposureData(null);
        })
        .catch(() => setExposureData(null))
        .finally(() => setExposureLoading(false));
    } else {
      setExposureData(null);
    }
  }, [selectedPortfolioId]);

  function loadPlans() {
    setPlansLoading(true);
    setPlansError("");
    api.fetchPositionPlans({ status: planStatusFilter === "all" ? undefined : planStatusFilter })
      .then(setPlans)
      .catch((err) => {
        setPlans([]);
        if (!err.message?.includes("404")) {
          setPlansError(err.message);
        }
      })
      .finally(() => setPlansLoading(false));
  }

  // ===================================================================
  // Handlers
  // ===================================================================
  async function handleCalculate() {
    const equity = parseFloat(accountEquity);
    if (!equity || equity <= 0) {
      setCalcError("请输入有效的账户权益");
      return;
    }
    if (!symbol.trim()) {
      setCalcError("请输入股票代码");
      return;
    }
    const price = parseFloat(entryPrice);
    if (!price || price <= 0) {
      setCalcError("请输入有效的入场参考价");
      return;
    }
    const rpt = (parseFloat(riskPerTradePct) || 1) / 100;

    setCalculating(true);
    setCalcError("");
    setCalcResult(null);

    const req: PositionSizeRequest = {
      account_equity: equity,
      available_cash: availableCash ? parseFloat(availableCash) : undefined,
      symbol: symbol.trim().toUpperCase(),
      entry_price: price,
      invalidation_price: invalidationPrice ? parseFloat(invalidationPrice) : undefined,
      risk_per_trade_pct: rpt,
      max_single_position_pct: maxSinglePosPct ? parseFloat(maxSinglePosPct) / 100 : undefined,
      max_theme_exposure_pct: maxThemeExposurePct ? parseFloat(maxThemeExposurePct) / 100 : undefined,
      current_drawdown_pct: currentDrawdownPct ? parseFloat(currentDrawdownPct) / 100 : undefined,
      market: market || undefined,
      lot_size: parseInt(lotSize) || 100,
    };

    try {
      const result = await api.calculatePositionSize(req);
      setCalcResult(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "测算失败";
      setCalcError(msg);
    } finally {
      setCalculating(false);
    }
  }

  async function handleSavePlan() {
    if (!calcResult || calcResult.error) return;
    setSavingPlan(true);
    setSaveSuccess(false);
    try {
      await api.createPositionPlan({
        symbol: calcResult.symbol,
        entry_price: calcResult.entry_price,
        invalidation_price: calcResult.invalidation_price,
        calculated_position_pct: calcResult.estimated_position_pct,
        estimated_position_value: calcResult.estimated_position_value,
        warnings: calcResult.warnings,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      loadPlans();
    } catch (err) {
      setCalcError(err instanceof Error ? err.message : "保存计划失败");
    } finally {
      setSavingPlan(false);
    }
  }

  async function handleActivatePlan(planId: number) {
    setActivatingId(planId);
    try {
      await api.activatePlan(planId);
      loadPlans();
    } catch (err) {
      console.error(err);
    } finally {
      setActivatingId(null);
    }
  }

  async function handleArchivePlan(planId: number) {
    setArchivingPlanId(planId);
    try {
      await api.archivePlan(planId);
      loadPlans();
    } catch (err) {
      console.error(err);
    } finally {
      setArchivingPlanId(null);
    }
  }

  // ===================================================================
  // Computed: Drawdown
  // ===================================================================
  const drawdownMultiplier = useMemo(() => {
    if (drawdownPct <= 0) return 1.0;
    if (drawdownPct <= 5) return 1.0;
    if (drawdownPct <= 10) return 0.75;
    if (drawdownPct <= 15) return 0.5;
    if (drawdownPct <= 20) return 0.25;
    return 0;
  }, [drawdownPct]);

  const drawdownStatusText = useMemo(() => {
    if (drawdownPct <= 0) return "正常状态";
    if (drawdownPct <= 5) return "正常波动";
    if (drawdownPct <= 10) return "注意回撤";
    if (drawdownPct <= 15) return "风险预警";
    if (drawdownPct <= 20) return "严重回撤";
    return "极端回撤";
  }, [drawdownPct]);

  const drawdownDescription = useMemo(() => {
    if (drawdownPct <= 0) return "当前无回撤，可正常开仓。";
    if (drawdownPct <= 5) return "小幅回撤，建议维持正常仓位。";
    if (drawdownPct <= 10) return "回撤加大，建议将仓位降至75%。";
    if (drawdownPct <= 15) return "较大回撤，建议将仓位降至50%。";
    if (drawdownPct <= 20) return "严重回撤，建议将仓位降至25%。";
    return "极端回撤，建议暂停开仓。";
  }, [drawdownPct]);

  const drawdownBadgeColor = useMemo(() => {
    if (drawdownPct <= 5) return "bg-emerald-100 text-emerald-700 border-emerald-200";
    if (drawdownPct <= 10) return "bg-amber-100 text-amber-700 border-amber-200";
    if (drawdownPct <= 15) return "bg-orange-100 text-orange-700 border-orange-200";
    if (drawdownPct <= 20) return "bg-rose-100 text-rose-700 border-rose-200";
    return "bg-red-100 text-red-700 border-red-200";
  }, [drawdownPct]);

  const filteredPlans = useMemo(() => {
    if (planStatusFilter === "all") return plans;
    return plans.filter((p) => p.status === planStatusFilter);
  }, [plans, planStatusFilter]);

  // ===================================================================
  // Render
  // ===================================================================
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="min-h-screen bg-slate-50 px-6 py-8"
    >
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Header */}
        <motion.section variants={itemVariants}>
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
            <Shield size={14} />
            Risk Budget
          </div>
          <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900">风险预算工作台</h1>
          <p className="mt-2 max-w-3xl text-sm font-medium leading-6 text-slate-500">
            基于风险预算模型的仓位测算工具。输入账户权益与交易参数，系统将自动计算风险预算上限、最大股数和仓位比例。
          </p>
        </motion.section>

        <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
          {/* =============================================================== */}
          {/* LEFT COLUMN */}
          {/* =============================================================== */}
          <main className="space-y-6">
            {/* ------------------------------------------------------- */}
            {/* Section 1: Calculator Form */}
            {/* ------------------------------------------------------- */}
            <motion.section
              variants={itemVariants}
              className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="mb-5 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
                <Calculator size={16} className="text-indigo-600" />
                仓位测算器
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {/* Account Equity */}
                <InputField
                  label="账户权益"
                  placeholder="e.g. 1000000"
                  value={accountEquity}
                  onChange={setAccountEquity}
                  suffix="元"
                  required
                />
                {/* Available Cash */}
                <InputField
                  label="可用现金"
                  placeholder="可选"
                  value={availableCash}
                  onChange={setAvailableCash}
                  suffix="元"
                />
                {/* Symbol */}
                <InputField
                  label="股票代码"
                  placeholder="e.g. 000858"
                  value={symbol}
                  onChange={setSymbol}
                  required
                />
                {/* Entry Price */}
                <InputField
                  label="入场参考价"
                  placeholder="e.g. 150.00"
                  value={entryPrice}
                  onChange={setEntryPrice}
                  suffix="元"
                  required
                />
                {/* Invalidation Price */}
                <InputField
                  label="无效点价格"
                  placeholder="止损价"
                  value={invalidationPrice}
                  onChange={setInvalidationPrice}
                  suffix="元"
                />
                {/* Risk Per Trade */}
                <InputField
                  label="单笔风险比例"
                  placeholder="0.5-2"
                  value={riskPerTradePct}
                  onChange={setRiskPerTradePct}
                  suffix="%"
                />
                {/* Max Single Position */}
                <InputField
                  label="单票上限"
                  placeholder="可选"
                  value={maxSinglePosPct}
                  onChange={setMaxSinglePosPct}
                  suffix="%"
                />
                {/* Max Theme Exposure */}
                <InputField
                  label="主题上限"
                  placeholder="可选"
                  value={maxThemeExposurePct}
                  onChange={setMaxThemeExposurePct}
                  suffix="%"
                />
                {/* Current Drawdown */}
                <InputField
                  label="当前回撤"
                  placeholder="可选"
                  value={currentDrawdownPct}
                  onChange={setCurrentDrawdownPct}
                  suffix="%"
                />
                {/* Market */}
                <InputField
                  label="市场"
                  placeholder="A股/港股/美股"
                  value={market}
                  onChange={setMarket}
                />
                {/* Lot Size */}
                <InputField
                  label="每手股数"
                  placeholder="100"
                  value={lotSize}
                  onChange={setLotSize}
                  suffix="股"
                />
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={handleCalculate}
                  disabled={calculating}
                  className="inline-flex h-11 items-center gap-2 rounded-lg bg-slate-900 px-6 text-sm font-black text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300 transition-colors"
                >
                  {calculating ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Calculator size={16} />
                  )}
                  测算风险预算上限
                </button>

                {calcResult && !calcResult.error && (
                  <button
                    type="button"
                    onClick={handleSavePlan}
                    disabled={savingPlan}
                    className="inline-flex h-11 items-center gap-2 rounded-lg border border-indigo-200 bg-white px-6 text-sm font-bold text-indigo-600 hover:bg-indigo-50 disabled:opacity-50 transition-colors"
                  >
                    {savingPlan ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : saveSuccess ? (
                      <CheckCircle2 size={16} />
                    ) : (
                      <Save size={16} />
                    )}
                    {saveSuccess ? "已保存" : "保存为计划"}
                  </button>
                )}
              </div>

              {calcError && (
                <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
                  {calcError}
                </div>
              )}
            </motion.section>

            {/* ------------------------------------------------------- */}
            {/* Section 2: Portfolio Exposure Panel */}
            {/* ------------------------------------------------------- */}
            <motion.section
              variants={itemVariants}
              className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="mb-5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
                  <BarChart3 size={16} className="text-indigo-600" />
                  组合暴露
                </div>
                {portfolios.length > 0 && (
                  <select
                    value={selectedPortfolioId ?? ""}
                    onChange={(e) => setSelectedPortfolioId(e.target.value ? parseInt(e.target.value) : null)}
                    className="h-8 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-bold text-slate-600 outline-none"
                  >
                    {portfolios.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} (¥{(p.total_equity / 10000).toFixed(0)}万)
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {portfolioLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={16} className="animate-spin text-slate-400" />
                  <span className="ml-2 text-xs font-bold text-slate-400">加载组合...</span>
                </div>
              ) : portfolios.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
                  <div className="text-xs font-bold text-slate-400">暂无组合数据</div>
                  <div className="mt-1 text-[10px] font-medium text-slate-400">API 暂未开放或尚未创建组合</div>
                </div>
              ) : exposureLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={16} className="animate-spin text-slate-400" />
                  <span className="ml-2 text-xs font-bold text-slate-400">加载暴露数据...</span>
                </div>
              ) : !exposureData ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
                  <div className="text-xs font-bold text-slate-400">暂无暴露数据</div>
                  <div className="mt-1 text-[10px] font-medium text-slate-400">该组合尚未计算暴露数据</div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Single Stock Exposure */}
                  <div>
                    <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">单票暴露</div>
                    {exposureData.single_stock_exposure.length === 0 ? (
                      <div className="rounded-lg bg-slate-50 p-3 text-center text-[11px] font-medium text-slate-400">暂无数据</div>
                    ) : (
                      <ExposureTable items={exposureData.single_stock_exposure} nameKey="symbol" />
                    )}
                  </div>

                  {/* Industry Exposure */}
                  <div>
                    <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">行业暴露</div>
                    {exposureData.industry_exposure.length === 0 ? (
                      <div className="rounded-lg bg-slate-50 p-3 text-center text-[11px] font-medium text-slate-400">暂无数据</div>
                    ) : (
                      <ExposureTable items={exposureData.industry_exposure} nameKey="industry" />
                    )}
                  </div>

                  {/* Theme Exposure */}
                  <div>
                    <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">主题暴露</div>
                    {exposureData.theme_exposure.length === 0 ? (
                      <div className="rounded-lg bg-slate-50 p-3 text-center text-[11px] font-medium text-slate-400">暂无数据</div>
                    ) : (
                      <ExposureTable items={exposureData.theme_exposure} nameKey="theme" />
                    )}
                  </div>

                  {/* Current Risk Rules */}
                  {exposureData.current_risk_rules.length > 0 && (
                    <div>
                      <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">当前风控规则</div>
                      <div className="space-y-1">
                        {exposureData.current_risk_rules.map((rule, i) => (
                          <div key={i} className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2 text-[11px] font-medium text-slate-600">
                            <ShieldAlert size={12} className="mt-0.5 shrink-0 text-slate-400" />
                            {rule}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </motion.section>

            {/* ------------------------------------------------------- */}
            {/* Section 3: Position Plans List */}
            {/* ------------------------------------------------------- */}
            <motion.section
              variants={itemVariants}
              className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="mb-5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
                  <Eye size={16} className="text-indigo-600" />
                  仓位计划
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex rounded-lg bg-slate-100 p-0.5">
                    {[
                      { key: "all", label: "全部" },
                      { key: "draft", label: "草稿" },
                      { key: "active", label: "生效" },
                      { key: "archived", label: "归档" }
                    ].map((tab) => (
                      <button
                        key={tab.key}
                        type="button"
                        onClick={() => setPlanStatusFilter(tab.key)}
                        className={`px-3 py-1.5 rounded-md text-[10px] font-bold transition-all ${
                          planStatusFilter === tab.key
                            ? "bg-white text-slate-900 shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {plansLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={16} className="animate-spin text-slate-400" />
                  <span className="ml-2 text-xs font-bold text-slate-400">加载计划列表...</span>
                </div>
              ) : plansError ? (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-bold text-rose-700">
                  {plansError}
                </div>
              ) : filteredPlans.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-8 text-center">
                  <div className="text-xs font-bold text-slate-400">暂无仓位计划</div>
                  <div className="mt-1 text-[10px] font-medium text-slate-400">
                    {planStatusFilter === "all"
                      ? "使用上方的测算器计算后保存为计划"
                      : `当前筛选条件下无${planStatusFilter === "draft" ? "草稿" : planStatusFilter === "active" ? "生效" : "归档"}计划`}
                  </div>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="pb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">标的</th>
                        <th className="pb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">入场价</th>
                        <th className="pb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">止损价</th>
                        <th className="pb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">仓位比例</th>
                        <th className="pb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">状态</th>
                        <th className="pb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">警告</th>
                        <th className="pb-3 text-[10px] font-black uppercase tracking-widest text-slate-400">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {filteredPlans.map((plan) => (
                        <tr key={plan.id} className="group hover:bg-slate-50/50 transition-colors">
                          <td className="py-4">
                            <div className="text-sm font-bold text-slate-800">{plan.symbol}</div>
                          </td>
                          <td className="py-4 text-sm font-mono font-bold text-slate-700">
                            ¥{plan.entry_price.toFixed(2)}
                          </td>
                          <td className="py-4 text-sm font-mono font-bold text-slate-500">
                            {plan.invalidation_price ? `¥${plan.invalidation_price.toFixed(2)}` : "--"}
                          </td>
                          <td className="py-4 text-sm font-mono font-bold text-slate-700">
                            {plan.calculated_position_pct != null
                              ? `${(plan.calculated_position_pct * 100).toFixed(2)}%`
                              : "--"}
                          </td>
                          <td className="py-4">
                            <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] font-bold ${
                              plan.status === "active"
                                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                : plan.status === "draft"
                                  ? "border-amber-200 bg-amber-50 text-amber-700"
                                  : "border-slate-200 bg-slate-50 text-slate-500"
                            }`}>
                              {plan.status === "active" && <CheckCircle2 size={10} />}
                              {plan.status === "draft" && <Info size={10} />}
                              {plan.status === "archived" && <XCircle size={10} />}
                              {plan.status === "active" ? "生效" : plan.status === "draft" ? "草稿" : "归档"}
                            </span>
                          </td>
                          <td className="py-4">
                            {plan.warnings && plan.warnings.length > 0 ? (
                              <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                                <AlertTriangle size={10} />
                                {plan.warnings.length}
                              </span>
                            ) : (
                              <span className="text-[10px] font-medium text-slate-400">--</span>
                            )}
                          </td>
                          <td className="py-4">
                            <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                              {plan.status === "draft" && (
                                <button
                                  type="button"
                                  onClick={() => handleActivatePlan(plan.id)}
                                  disabled={activatingId === plan.id}
                                  className="rounded-md border border-emerald-200 bg-white px-2.5 py-1 text-[9px] font-bold text-emerald-600 hover:bg-emerald-50 disabled:opacity-50 transition-colors"
                                >
                                  {activatingId === plan.id ? (
                                    <Loader2 size={10} className="animate-spin" />
                                  ) : (
                                    "生效"
                                  )}
                                </button>
                              )}
                              {plan.status !== "archived" && (
                                <button
                                  type="button"
                                  onClick={() => handleArchivePlan(plan.id)}
                                  disabled={archivingPlanId === plan.id}
                                  className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[9px] font-bold text-slate-500 hover:border-rose-200 hover:text-rose-600 disabled:opacity-50 transition-colors"
                                >
                                  {archivingPlanId === plan.id ? (
                                    <Loader2 size={10} className="animate-spin" />
                                  ) : (
                                    "归档"
                                  )}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </motion.section>
          </main>

          {/* =============================================================== */}
          {/* RIGHT COLUMN */}
          {/* =============================================================== */}
          <aside className="space-y-6">
            {/* ------------------------------------------------------- */}
            {/* Result Card */}
            {/* ------------------------------------------------------- */}
            {calcResult && !calcResult.error ? (
              <motion.section
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
              >
                <div className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
                  <Calculator size={16} className="text-emerald-600" />
                  风险预算结果
                </div>

                <div className="space-y-4">
                  {/* Symbol + Entry */}
                  <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3">
                    <span className="text-xs font-bold text-slate-500">标的</span>
                    <span className="text-sm font-black text-slate-900">{calcResult.symbol}</span>
                  </div>

                  {/* Max Loss Amount */}
                  <MetricRow
                    label="风险金额"
                    value={formatMoney(calcResult.max_loss_amount)}
                    tooltip="本次交易的最大亏损金额"
                  />
                  {/* Risk Per Share */}
                  <MetricRow
                    label="每股风险"
                    value={calcResult.risk_per_share != null ? `¥${calcResult.risk_per_share.toFixed(2)}` : "--"}
                    tooltip="入场价与无效点价格之间的差值"
                  />
                  {/* Max Quantity */}
                  <MetricRow
                    label="最大股数"
                    value={formatShares(calcResult.rounded_quantity)}
                    tooltip="取整后的最大买入股数"
                  />
                  {/* Position % */}
                  <MetricRow
                    label="名义仓位比例"
                    value={formatPct(calcResult.estimated_position_pct)}
                    tooltip="仓位占总权益的比例"
                  />
                  {/* Effective Risk % */}
                  <MetricRow
                    label="实际风险比例"
                    value={formatPct(calcResult.effective_risk_pct)}
                    tooltip="实际使用的风险预算比例"
                  />
                  {/* Cash Required */}
                  <MetricRow
                    label="现金占用"
                    value={formatMoney(calcResult.cash_required)}
                    tooltip="建仓所需资金"
                  />
                  {/* Cash After */}
                  {calcResult.cash_after != null && (
                    <MetricRow
                      label="剩余现金"
                      value={formatMoney(calcResult.cash_after)}
                      tooltip="建仓后剩余可用现金"
                    />
                  )}

                  {/* Constraints Applied */}
                  {calcResult.constraints_applied.length > 0 && (
                    <div>
                      <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
                        约束条件
                      </div>
                      <div className="space-y-1">
                        {calcResult.constraints_applied.map((c, i) => (
                          <div key={i} className="flex items-start gap-2 rounded-lg bg-indigo-50/50 px-3 py-2 text-[11px] font-medium text-indigo-700">
                            <CheckCircle2 size={12} className="mt-0.5 shrink-0" />
                            {c}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Warnings */}
                  {calcResult.warnings.length > 0 && (
                    <div>
                      <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-amber-600">
                        风险提示
                      </div>
                      <div className="space-y-1">
                        {calcResult.warnings.map((w, i) => (
                          <div key={i} className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-[11px] font-medium text-amber-800">
                            <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                            {w}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Calculation Explain */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowExplain(!showExplain)}
                      className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-400 hover:text-slate-600 transition-colors"
                    >
                      {showExplain ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      查看计算说明
                    </button>
                    {showExplain && (
                      <div className="mt-2 rounded-lg bg-slate-50 px-3 py-3 text-[11px] font-medium leading-6 text-slate-600">
                        {calcResult.calculation_explain}
                      </div>
                    )}
                  </div>

                  {/* Disclaimer */}
                  <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-[10px] font-medium leading-5 text-slate-400">
                    {calcResult.disclaimer}
                  </div>
                </div>
              </motion.section>
            ) : calcResult?.error ? (
              <motion.section
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-lg border border-rose-200 bg-rose-50 p-6"
              >
                <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-rose-600 mb-3">
                  <AlertTriangle size={16} />
                  测算失败
                </div>
                <p className="text-sm font-bold text-rose-800">{calcResult.error}</p>
              </motion.section>
            ) : null}

            {/* ------------------------------------------------------- */}
            {/* Section 4: Drawdown Status */}
            {/* ------------------------------------------------------- */}
            <motion.section
              variants={itemVariants}
              className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
                <TrendingDown size={16} className="text-indigo-600" />
                回撤状态
              </div>

              {!currentDrawdownPct ? (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-6 text-center">
                  <div className="text-xs font-bold text-slate-400">请输入当前回撤</div>
                  <div className="mt-1 text-[10px] font-medium text-slate-400">
                    在测算器中填入回撤值后，此处将显示状态
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Current Drawdown Value */}
                  <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3">
                    <span className="text-xs font-bold text-slate-500">当前回撤</span>
                    <span className={`text-lg font-black font-mono ${
                      drawdownPct > 10 ? "text-rose-600" : drawdownPct > 5 ? "text-amber-600" : "text-slate-900"
                    }`}>
                      {drawdownPct.toFixed(2)}%
                    </span>
                  </div>

                  {/* Risk Multiplier */}
                  <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3">
                    <span className="text-xs font-bold text-slate-500">风险乘数</span>
                    <span className={`rounded-md border px-3 py-1 text-sm font-black ${drawdownBadgeColor}`}>
                      {drawdownMultiplier.toFixed(2)}x
                    </span>
                  </div>

                  {/* Status */}
                  <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3">
                    <span className="text-xs font-bold text-slate-500">状态</span>
                    <span className={`rounded-md border px-3 py-1 text-xs font-bold ${drawdownBadgeColor}`}>
                      {drawdownStatusText}
                    </span>
                  </div>

                  {/* Description */}
                  <div className="rounded-lg bg-slate-50 px-4 py-3 text-[11px] font-medium leading-5 text-slate-600">
                    {drawdownDescription}
                  </div>

                  {/* Multiplier scale */}
                  <div className="pt-2">
                    <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">回撤-乘数对照</div>
                    <div className="space-y-1.5">
                      <ScaleRow label="0%-5%" multiplier="1.00x" color="bg-emerald-500" active={drawdownPct <= 5} />
                      <ScaleRow label="5%-10%" multiplier="0.75x" color="bg-amber-500" active={drawdownPct > 5 && drawdownPct <= 10} />
                      <ScaleRow label="10%-15%" multiplier="0.50x" color="bg-orange-500" active={drawdownPct > 10 && drawdownPct <= 15} />
                      <ScaleRow label="15%-20%" multiplier="0.25x" color="bg-rose-500" active={drawdownPct > 15 && drawdownPct <= 20} />
                      <ScaleRow label=">20%" multiplier="0.00x" color="bg-red-600" active={drawdownPct > 20} />
                    </div>
                  </div>
                </div>
              )}
            </motion.section>
          </aside>
        </div>
      </div>
    </motion.div>
  );
}

// =====================================================================
// Sub-components
// =====================================================================

function InputField({
  label,
  placeholder,
  value,
  onChange,
  suffix,
  required
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="mb-1.5 flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-slate-400">
        {label}
        {required && <span className="text-rose-400">*</span>}
      </label>
      <div className="relative">
        <input
          type="text"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-indigo-400 focus:bg-white transition-colors"
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold text-slate-400 pointer-events-none">
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}

function MetricRow({
  label,
  value,
  tooltip
}: {
  label: string;
  value: string;
  tooltip?: string;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg bg-slate-50 px-4 py-3">
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-bold text-slate-500">{label}</span>
        {tooltip && (
          <span className="group relative">
            <Info size={11} className="text-slate-300 hover:text-slate-400 cursor-help" />
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-10">
              <div className="bg-slate-800 text-white text-[10px] px-2 py-1 rounded shadow-lg whitespace-nowrap max-w-[200px] text-center">
                {tooltip}
              </div>
            </div>
          </span>
        )}
      </div>
      <span className="text-sm font-black text-slate-900 font-mono">{value}</span>
    </div>
  );
}

function ExposureTable({
  items,
  nameKey
}: {
  items: Array<{
    symbol?: string;
    name?: string;
    industry?: string;
    theme?: string;
    exposure_pct: number;
    limit_pct: number;
    over_limit: boolean;
  }>;
  nameKey: "symbol" | "industry" | "theme";
}) {
  return (
    <div className="space-y-1.5">
      {items.map((item, i) => {
        const name = item[nameKey] || item.name || "--";
        const exposureStr = `${(item.exposure_pct * 100).toFixed(2)}%`;
        const limitStr = `${(item.limit_pct * 100).toFixed(2)}%`;
        return (
          <div
            key={i}
            className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 text-[11px] font-bold ${
              item.over_limit
                ? "bg-rose-50 border border-rose-200"
                : "bg-slate-50"
            }`}
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="truncate text-slate-800">{name}</span>
              {item.over_limit && (
                <span className="shrink-0 inline-flex items-center gap-0.5 rounded bg-rose-100 px-1.5 py-0.5 text-[9px] font-black text-rose-700">
                  <AlertTriangle size={9} />
                  超限
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={item.over_limit ? "text-rose-700" : "text-slate-600"}>
                {exposureStr}
              </span>
              <span className="text-slate-300">/</span>
              <span className="text-slate-400">{limitStr}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ScaleRow({
  label,
  multiplier,
  color,
  active
}: {
  label: string;
  multiplier: string;
  color: string;
  active: boolean;
}) {
  return (
    <div className={`flex items-center justify-between rounded-lg px-3 py-2 transition-colors ${
      active ? "bg-indigo-50 border border-indigo-200" : "bg-slate-50"
    }`}>
      <div className="flex items-center gap-2">
        <div className={`h-2 w-2 rounded-full ${color}`} />
        <span className={`text-[11px] font-bold ${active ? "text-indigo-700" : "text-slate-500"}`}>
          {label}
        </span>
      </div>
      <span className={`text-[11px] font-mono font-black ${active ? "text-indigo-700" : "text-slate-400"}`}>
        {multiplier}
      </span>
    </div>
  );
}

export default function RiskPage() {
  return (
    <Suspense fallback={<div className="min-h-[60vh] flex items-center justify-center"><Loader2 size={32} className="animate-spin text-slate-400" /></div>}>
      <RiskPageContent />
    </Suspense>
  );
}
