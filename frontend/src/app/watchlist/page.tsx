"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, CalendarDays, Eye, Filter, Loader2, Plus, Repeat2, TrendingUp, X } from "lucide-react";
import { motion } from "framer-motion";
import { ErrorState } from "@/components/ErrorState";
import { LoadingState } from "@/components/LoadingState";
import { api, type ResearchThesis, type WatchlistItemEnhanced } from "@/lib/api";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0 }
};

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItemEnhanced[]>([]);
  const [theses, setTheses] = useState<ResearchThesis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [subjectFilter, setSubjectFilter] = useState<string>("all");
  const [archivingId, setArchivingId] = useState<number | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [thesisSearch, setThesisSearch] = useState("");
  const [addingThesisId, setAddingThesisId] = useState<number | null>(null);

  const loadData = () => {
    setLoading(true);
    setError("");
    Promise.all([
      api.fetchWatchlistItems({ status: statusFilter, limit: 50 }),
      api.fetchTheses({ status: "active", limit: 100 })
    ])
      .then(([watchlistData, thesesData]) => {
        setItems(watchlistData);
        setTheses(thesesData);
      })
      .catch((err: Error) => setError(`数据读取失败：${err.message}`))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (priorityFilter !== "all" && item.priority !== priorityFilter) return false;
      if (subjectFilter !== "all" && item.subject_type !== subjectFilter) return false;
      return true;
    });
  }, [items, priorityFilter, subjectFilter]);

  const upcomingReviews = useMemo(() => {
    return items
      .filter((item) => item.review_date && item.status === "active")
      .sort((a, b) => {
        if (!a.review_date) return 1;
        if (!b.review_date) return -1;
        return new Date(a.review_date).getTime() - new Date(b.review_date).getTime();
      })
      .slice(0, 5);
  }, [items]);

  const handleArchive = async (itemId: number) => {
    setArchivingId(itemId);
    try {
      await api.archiveWatchlistItem(itemId);
      setItems((prev) => prev.map((item) =>
        item.id === itemId ? { ...item, status: "archived" } : item
      ));
    } catch (err) {
      setError(err instanceof Error ? err.message : "归档失败");
    } finally {
      setArchivingId(null);
    }
  };

  const handleAddFromThesis = async (thesis: ResearchThesis) => {
    setAddingThesisId(thesis.id);
    try {
      await api.addToWatchlist({
        thesis_id: thesis.id,
        subject_type: thesis.subject_type,
        subject_id: thesis.subject_id,
        subject_name: thesis.subject_name,
        thesis_title: thesis.thesis_title,
        direction: thesis.direction,
        reason: thesis.thesis_body?.slice(0, 500),
        priority: "B"
      });
      setShowModal(false);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入观察池失败");
    } finally {
      setAddingThesisId(null);
    }
  };

  const filteredTheses = useMemo(() => {
    if (!thesisSearch.trim()) return theses.slice(0, 20);
    const q = thesisSearch.toLowerCase();
    return theses.filter(
      (t) =>
        t.thesis_title?.toLowerCase().includes(q) ||
        t.thesis_body?.toLowerCase().includes(q) ||
        t.subject_name?.toLowerCase().includes(q) ||
        t.subject_id?.toLowerCase().includes(q)
    ).slice(0, 20);
  }, [theses, thesisSearch]);

  const subjectTypeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    items.forEach((item) => {
      counts[item.subject_type] = (counts[item.subject_type] || 0) + 1;
    });
    return counts;
  }, [items]);

  if (loading) return <div className="min-h-screen bg-slate-50 p-8"><LoadingState label="正在加载观察池数据" /></div>;
  if (error) return <div className="min-h-screen bg-slate-50 p-8"><ErrorState message={error} /></div>;

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={containerVariants}
      className="min-h-screen bg-slate-50 px-6 py-8 space-y-6"
    >
      {/* Header */}
      <motion.section variants={itemVariants} className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-2">
              <Eye size={14} />
              观察池
            </div>
            <h1 className="text-3xl font-black text-slate-900 tracking-tight">观察池工作台</h1>
            <p className="mt-2 text-sm font-medium text-slate-500 max-w-2xl">
              以观点为中心的观察池管理。跟踪研究观点、证伪条件与复盘结果。
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowModal(true)}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-indigo-600 px-5 text-sm font-bold text-white shadow-lg shadow-indigo-100 hover:bg-indigo-700 transition-colors"
          >
            <Plus size={16} />
            从观点添加
          </button>
        </div>

        {/* Filters */}
        <div className="mt-6 flex flex-wrap items-center gap-3 pt-6 border-t border-slate-100">
          <span className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-slate-400">
            <Filter size={12} />
            筛选
          </span>
          <div className="flex bg-slate-100 rounded-xl p-1">
            {["active", "archived"].map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`px-4 py-1.5 rounded-lg text-[10px] font-black uppercase transition-all ${
                  statusFilter === status ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {status === "active" ? "观察中" : "已归档"}
              </button>
            ))}
          </div>
          <div className="flex bg-slate-100 rounded-xl p-1">
            {[{ key: "all", label: "全部" }, { key: "S", label: "S" }, { key: "A", label: "A" }, { key: "B", label: "B" }].map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => setPriorityFilter(p.key)}
                className={`px-3 py-1.5 rounded-lg text-[10px] font-black transition-all ${
                  priorityFilter === p.key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex bg-slate-100 rounded-xl p-1">
            {[
              { key: "all", label: "全部类型" },
              ...Object.entries(subjectTypeCounts).map(([key]) => ({
                key,
                label: key === "stock" ? "股票" : key === "industry" ? "产业" : key === "theme" ? "主题" : key
              }))
            ].map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => setSubjectFilter(s.key)}
                className={`px-3 py-1.5 rounded-lg text-[10px] font-black transition-all ${
                  subjectFilter === s.key ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      </motion.section>

      {/* Upcoming Reviews */}
      {upcomingReviews.length > 0 && (
        <motion.section variants={itemVariants} className="bg-amber-50 border border-amber-200 rounded-3xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <CalendarDays size={18} className="text-amber-600" />
            <h2 className="text-base font-bold text-amber-900">即将复盘</h2>
            <span className="text-xs font-bold text-amber-600">{upcomingReviews.length} 条</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {upcomingReviews.map((item) => (
              <div key={item.id} className="bg-white rounded-xl border border-amber-100 p-4">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="font-bold text-slate-900 text-sm truncate">
                    {item.subject_name || item.thesis_title?.slice(0, 30)}
                  </span>
                  <span className={`shrink-0 px-2 py-0.5 rounded text-[9px] font-black uppercase ${
                    item.priority === "S" ? "bg-rose-100 text-rose-700" :
                    item.priority === "A" ? "bg-amber-100 text-amber-700" :
                    "bg-slate-100 text-slate-600"
                  }`}>
                    {item.priority}
                  </span>
                </div>
                <div className="text-[10px] font-bold text-amber-600">
                  复盘日: {item.review_date}
                </div>
                {item.reason && (
                  <div className="mt-1 text-[10px] font-medium text-slate-400 line-clamp-1">{item.reason}</div>
                )}
              </div>
            ))}
          </div>
        </motion.section>
      )}

      {/* Main Content */}
      {filteredItems.length === 0 ? (
        <motion.section variants={itemVariants} className="bg-white rounded-3xl p-12 text-center shadow-sm border border-slate-200">
          <div className="text-slate-300 font-black uppercase tracking-[0.2em] mb-2">暂无数据</div>
          <p className="text-sm text-slate-500 font-medium">当前筛选条件下无观察池条目。点击上方按钮从观点添加。</p>
        </motion.section>
      ) : (
        <div className="space-y-4">
          {filteredItems.map((item) => (
            <WatchlistItemCard
              key={item.id}
              item={item}
              onArchive={handleArchive}
              archivingId={archivingId}
            />
          ))}
        </div>
      )}

      {/* Add from Thesis Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden border border-slate-200"
          >
            <div className="flex items-center justify-between p-6 border-b border-slate-200">
              <h2 className="text-lg font-black text-slate-900">从观点添加到观察池</h2>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="p-2 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-6">
              <input
                type="text"
                value={thesisSearch}
                onChange={(e) => setThesisSearch(e.target.value)}
                placeholder="搜索观点标题、内容、股票名称..."
                className="w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-800 outline-none focus:border-indigo-400 focus:bg-white mb-4"
                autoFocus
              />
              <div className="max-h-[400px] space-y-2 overflow-y-auto">
                {filteredTheses.map((thesis) => (
                  <div
                    key={thesis.id}
                    className="rounded-xl border border-slate-100 bg-slate-50/30 p-4 hover:border-indigo-200 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider border ${
                            thesis.direction === "positive" ? "bg-rose-100 text-rose-700 border-rose-200" :
                            thesis.direction === "negative" ? "bg-emerald-100 text-emerald-700 border-emerald-200" :
                            thesis.direction === "mixed" ? "bg-amber-100 text-amber-700 border-amber-200" :
                            "bg-slate-100 text-slate-600 border-slate-200"
                          }`}>
                            {thesis.direction === "positive" ? "看多" :
                             thesis.direction === "negative" ? "看空" :
                             thesis.direction === "mixed" ? "多空交织" : "中性"}
                          </span>
                          <span className="text-[9px] font-bold text-slate-400">
                            {thesis.subject_name} ({thesis.subject_id})
                          </span>
                        </div>
                        <div className="text-sm font-bold text-slate-900 truncate">
                          {thesis.thesis_title || thesis.thesis_body?.slice(0, 100)}
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-[10px] font-medium text-slate-400">
                          <span>周期 {thesis.horizon_days}天</span>
                          <span>置信度 {Math.round(thesis.confidence * 100)}%</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleAddFromThesis(thesis)}
                        disabled={addingThesisId === thesis.id}
                        className="shrink-0 inline-flex h-9 items-center gap-1.5 rounded-lg bg-indigo-600 px-4 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                      >
                        {addingThesisId === thesis.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Plus size={14} />
                        )}
                        添加
                      </button>
                    </div>
                  </div>
                ))}
                {filteredTheses.length === 0 && (
                  <div className="text-center py-8 text-sm font-medium text-slate-400">
                    {thesisSearch ? "未找到匹配观点" : "暂无可用观点"}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </motion.div>
  );
}

function WatchlistItemCard({
  item,
  onArchive,
  archivingId
}: {
  item: WatchlistItemEnhanced;
  onArchive: (id: number) => void;
  archivingId: number | null;
}) {
  const [expandedInvalidation, setExpandedInvalidation] = useState(false);

  let invalidationConditions: string[] = [];
  try {
    const parsed = JSON.parse(item.invalidation_conditions_json || "[]");
    invalidationConditions = Array.isArray(parsed) ? parsed : [];
  } catch {}

  let watchMetrics: Record<string, unknown> = {};
  try {
    watchMetrics = JSON.parse(item.watch_metrics_json || "{}");
  } catch {}

  const isArchiving = archivingId === item.id;

  return (
    <motion.div
      variants={itemVariants}
      className="bg-white rounded-3xl p-8 shadow-sm border border-slate-200 hover:shadow-md transition-shadow"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        {/* Main Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-3">
            <span className={`px-2.5 py-1 rounded-lg text-xs font-black uppercase tracking-wider ${
              item.priority === "S" ? "bg-rose-100 text-rose-700" :
              item.priority === "A" ? "bg-amber-100 text-amber-700" :
              "bg-slate-100 text-slate-600"
            }`}>
              优先级 {item.priority}
            </span>
            <span className="text-xs font-bold text-indigo-600">
              {item.subject_name}
            </span>
            <span className="text-[10px] font-mono font-bold text-slate-400">
              {item.subject_id}
            </span>
            <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${
              item.subject_type === "stock" ? "bg-blue-50 text-blue-600 border-blue-100" :
              item.subject_type === "industry" ? "bg-purple-50 text-purple-600 border-purple-100" :
              "bg-slate-50 text-slate-500 border-slate-100"
            }`}>
              {item.subject_type === "stock" ? "股票" : item.subject_type === "industry" ? "产业" : item.subject_type}
            </span>
          </div>

          <h3 className="text-lg font-bold text-slate-900">
            {item.thesis_title || item.subject_name}
          </h3>

          {item.reason && (
            <p className="mt-2 text-sm font-medium text-slate-600 leading-relaxed max-w-3xl">
              {item.reason}
            </p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {item.subject_type === "stock" && item.subject_id && (
            <>
              <Link
                href={`/stocks/${encodeURIComponent(item.subject_id)}?from=/watchlist`}
                className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 text-xs font-bold text-slate-600 hover:border-indigo-200 hover:text-indigo-600 transition-colors"
              >
                查看证据链
              </Link>
              <Link
                href={`/risk?symbol=${encodeURIComponent(item.subject_id)}&name=${encodeURIComponent(item.subject_name || "")}`}
                className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 text-xs font-bold text-slate-600 hover:border-amber-200 hover:text-amber-600 transition-colors"
              >
                创建风险预算计划
              </Link>
            </>
          )}
          {item.status === "active" && (
            <button
              type="button"
              onClick={() => onArchive(item.id)}
              disabled={isArchiving}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 text-xs font-bold text-slate-500 hover:border-rose-200 hover:text-rose-600 disabled:opacity-50 transition-colors"
            >
              {isArchiving ? <Loader2 size={14} className="animate-spin" /> : null}
              归档
            </button>
          )}
        </div>
      </div>

      {/* Details Grid */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Direction */}
        <div className="rounded-xl bg-slate-50 p-3 border border-slate-100">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">方向</div>
          <span className={`text-xs font-black ${
            item.direction === "positive" ? "text-rose-600" :
            item.direction === "negative" ? "text-emerald-600" :
            item.direction === "mixed" ? "text-amber-600" :
            "text-slate-600"
          }`}>
            {item.direction === "positive" ? "看多" :
             item.direction === "negative" ? "看空" :
             item.direction === "mixed" ? "多空交织" : "中性"}
          </span>
        </div>

        {/* Status */}
        <div className="rounded-xl bg-slate-50 p-3 border border-slate-100">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">状态</div>
          <span className={`text-xs font-black ${
            item.status === "active" ? "text-emerald-600" : "text-slate-400"
          }`}>
            {item.status === "active" ? "观察中" : "已归档"}
          </span>
        </div>

        {/* Review Date */}
        <div className="rounded-xl bg-slate-50 p-3 border border-slate-100">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">复盘日期</div>
          <span className="text-xs font-bold text-slate-700">
            {item.review_date || "待安排"}
          </span>
        </div>

        {/* Review Result */}
        <div className="rounded-xl bg-slate-50 p-3 border border-slate-100">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">复盘结果</div>
          <span className="text-xs font-bold text-slate-700">
            {item.review_result || "待复盘"}
          </span>
        </div>
      </div>

      {/* Watch Metrics */}
      {Object.keys(watchMetrics).length > 0 && (
        <div className="mt-4">
          <div className="flex flex-wrap gap-2">
            {Object.entries(watchMetrics).map(([key, value]) => (
              <div key={key} className="rounded-lg bg-indigo-50/50 border border-indigo-100 px-3 py-1.5">
                <span className="text-[9px] font-black uppercase tracking-widest text-indigo-500">{key}</span>
                <span className="ml-2 text-xs font-bold text-indigo-700">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Invalidation Conditions */}
      {invalidationConditions.length > 0 && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => setExpandedInvalidation(!expandedInvalidation)}
            className="inline-flex items-center gap-1 text-[10px] font-bold text-slate-400 hover:text-slate-600 transition-colors"
          >
            {expandedInvalidation ? "收起" : "展开"}证伪条件 ({invalidationConditions.length})
          </button>
          {expandedInvalidation && (
            <div className="mt-2 space-y-1.5">
              {invalidationConditions.map((cond, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px] font-medium text-slate-500">
                  <span className="w-1 h-1 mt-1.5 shrink-0 rounded-full bg-slate-300" />
                  {cond}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
}
