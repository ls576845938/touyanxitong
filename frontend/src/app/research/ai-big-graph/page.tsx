"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { 
  Activity, 
  ArrowLeft, 
  Boxes, 
  Cpu, 
  Database, 
  Expand, 
  GitBranch, 
  Layers, 
  LayoutDashboard, 
  Network, 
  Search, 
  Share2, 
  Target, 
  Zap,
  Info,
  TrendingUp,
  ShieldAlert,
  ArrowUpRight,
  Maximize2,
  Download,
  Flame,
  MousePointer2,
  RefreshCcw,
  Plus,
  Minus,
  FileText,
  Workflow,
  Radio,
  Power
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import * as echarts from "echarts";
import { cn } from "@/lib/utils";
import { 
  AI_INFRA_TREE, 
  flattenAiInfraTree, 
  findAiInfraNode,
  type AiInfraNode,
  type AiInfraFlatNode
} from "@/lib/ai-infra-knowledge-tree";
import { api, type ChainOverview, type ResearchHotTerms } from "@/lib/api";

type ViewMode = "tree" | "graph" | "sunburst" | "heatmap";

/**
 * LOGIC-DRIVEN COLOR PALETTE
 * Based on the industry chain role:
 * - Blue/Indigo: Foundations & Capital
 * - Violet/Purple: High-Value Intelligence (Chips)
 * - Emerald/Green: Data Storage & Persistence
 * - Cyan/Teal: Transmission & Connectivity
 * - Slate/Zinc: Structural Systems (Servers)
 * - Amber/Orange: Utility & Power
 * - Gold/Crimson: Strategic Upstream (Tax Collectors)
 */
const LOGIC_COLORS: Record<string, { base: string; light: string; bg: string }> = {
  demand: { base: "#4f46e5", light: "#818cf8", bg: "#eef2ff" },        // Indigo (Foundations)
  'compute-chip': { base: "#8b5cf6", light: "#a78bfa", bg: "#f5f3ff" }, // Violet (The Brain)
  'memory-storage': { base: "#10b981", light: "#34d399", bg: "#ecfdf5" }, // Emerald (Memory)
  'server-odm': { base: "#64748b", light: "#94a3b8", bg: "#f8fafc" },    // Slate (Systems)
  'pcb': { base: "#0ea5e9", light: "#38bdf8", bg: "#f0f9ff" },          // Sky (Connectivity)
  'scale-up': { base: "#06b6d4", light: "#22d3ee", bg: "#ecfeff" },     // Cyan (Interconnect)
  'scale-out': { base: "#0d9488", light: "#2dd4bf", bg: "#f0fdfa" },     // Teal (Networking)
  'optical': { base: "#14b8a6", light: "#5eead4", bg: "#f0fdfa" },       // Teal-Bright (Optical)
  'cooling': { base: "#f59e0b", light: "#fbbf24", bg: "#fffbeb" },       // Amber (Facility)
  'power': { base: "#ea580c", light: "#fb923c", bg: "#fff7ed" },         // Orange (Energy)
  'tax-collectors': { base: "#b45309", light: "#f59e0b", bg: "#fef3c7" }, // Gold/Brown (Strategic)
  'ai-data-center': { base: "#334155", light: "#475569", bg: "#f1f5f9" }  // Zinc (Infrastructure Total)
};

const HEAT_GRADIENT = [
  "#FEF3C7", // Cool Yellow
  "#FDE68A", 
  "#FCD34D", 
  "#FBBF24", // Warm Amber
  "#F59E0B", 
  "#EA580C", // Hot Orange
  "#DC2626", // Danger Red
  "#991B1B"  // Peak Heat
];

export default function AiBigGraphPage() {
  const [viewMode, setViewMode] = useState<ViewMode>("tree");
  const [selectedId, setSelectedId] = useState<string>("compute-chip");
  const [query, setQuery] = useState("");
  const [showInfo, setShowInfo] = useState(false); // Toggle for hidden explanation
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // Dynamic Data
  const [hotTerms, setHotTerms] = useState<ResearchHotTerms | null>(null);
  const [chain, setChain] = useState<ChainOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const flatNodes = useMemo(() => flattenAiInfraTree(AI_INFRA_TREE), []);
  
  // Heat Score Calculation
  const nodeHeatMap = useMemo(() => {
    const heatmap: Record<string, number> = {};
    flatNodes.forEach(node => {
      let score = 0;
      if (hotTerms) {
        const matches = hotTerms.hot_terms.filter(t => t.term.includes(node.title) || node.title.includes(t.term));
        score += matches.reduce((sum, t) => sum + t.score, 0) * 2;
      }
      if (chain) {
        const matches = chain.nodes.filter(cn => cn.name.includes(node.title) || node.title.includes(cn.name));
        score += matches.reduce((sum, cn) => sum + (cn.heat ?? 0), 0) * 10;
      }
      heatmap[node.id] = Math.max(15, score);
    });
    return heatmap;
  }, [flatNodes, hotTerms, chain]);

  const selectedNode = useMemo(() => findAiInfraNode(selectedId, flatNodes), [selectedId, flatNodes]);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.hotTerms().catch(() => null), api.chainOverview().catch(() => null)]).then(([hot, ch]) => {
      setHotTerms(hot);
      setChain(ch);
      setLoading(false);
    });
  }, []);

  // Hierarchical Data (Mind Map Format)
  const hierarchicalData = useMemo(() => {
    const transform = (node: AiInfraNode): any => ({
      name: node.title,
      id: node.id,
      value: nodeHeatMap[node.id] || 10,
      children: node.children?.map(transform) || [],
      itemStyle: { color: getLogicalColor(node.id, node.role || node.parentId || node.id).base }
    });

    return {
      name: "AI算力基础设施全景",
      id: "root",
      children: AI_INFRA_TREE.map(transform)
    };
  }, [nodeHeatMap]);

  // Topology Data (Graph)
  const graphData = useMemo(() => {
    const nodes: any[] = [];
    const links: any[] = [];
    flatNodes.forEach(node => {
      const heat = nodeHeatMap[node.id] || 10;
      const colorSet = getLogicalColor(node.id, node.rootId);
      nodes.push({
        id: node.id,
        name: node.title,
        value: heat,
        symbolSize: (node.depth === 0 ? 40 : node.depth === 1 ? 28 : 16) * (1 + Math.min(1.2, heat / 150)),
        category: node.rootId,
        itemStyle: {
          color: heat > 120 ? getRefinedHeatColor(heat) : colorSet.base,
          shadowBlur: heat > 100 ? 15 : 0,
          shadowColor: colorSet.base
        }
      });
      if (node.parentId) links.push({ source: node.parentId, target: node.id });
    });
    return { nodes, links, categories: AI_INFRA_TREE.map(n => ({ name: n.id })) };
  }, [flatNodes, nodeHeatMap]);

  // Chart Rendering
  useEffect(() => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
      chartInstance.current.on('click', (params: any) => {
        const id = params.data?.id || params.name;
        if (id && id !== "root") setSelectedId(id);
      });
    }

    const option = 
      viewMode === "tree" ? getTreeOption(hierarchicalData, selectedId) :
      viewMode === "graph" ? getGraphOption(graphData, selectedId) :
      viewMode === "sunburst" ? getSunburstOption(hierarchicalData, selectedId) :
      getTreeMapOption(hierarchicalData, selectedId);

    chartInstance.current.setOption(option, true);

    const resize = () => chartInstance.current?.resize();
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, [viewMode, hierarchicalData, graphData, selectedId]);

  const exportImg = () => {
    if (!chartInstance.current) return;
    const url = chartInstance.current.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' });
    const link = document.createElement('a');
    link.href = url;
    link.download = `AI-Infra-Chain-${viewMode}-${new Date().getTime()}.png`;
    link.click();
  };

  const currentChartZoom = () => {
    const option = chartInstance.current?.getOption() as { series?: Array<{ zoom?: number }> } | undefined;
    return option?.series?.[0]?.zoom ?? 1;
  };

  return (
    <div className="flex h-screen bg-[#fafafa] text-slate-900 overflow-hidden font-sans select-none">
      {/* Sidebar */}
      <aside className="w-[360px] border-r border-slate-200/60 flex flex-col bg-white/80 backdrop-blur-2xl z-20 shadow-xl">
        <div className="p-8 border-b border-slate-100">
          <div className="flex items-center gap-4 mb-8">
            <div className="h-14 w-14 rounded-[22px] bg-indigo-600 flex items-center justify-center text-white shadow-2xl shadow-indigo-200 ring-4 ring-indigo-50">
              <Workflow size={28} />
            </div>
            <div>
              <h1 className="text-2xl font-[900] tracking-tighter text-slate-900 leading-none">AI大图谱</h1>
              <p className="text-[10px] font-black text-indigo-500/60 uppercase tracking-[0.2em] mt-2">Chain Logic v1.5</p>
            </div>
          </div>

          <div className="relative mb-6">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-300" size={20} />
            <input 
              type="text"
              placeholder="搜索标的、环节、概念..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-4 bg-slate-50 border-2 border-transparent rounded-[20px] text-sm font-bold focus:bg-white focus:border-indigo-100 transition-all outline-none shadow-inner"
            />
          </div>

          <div className="flex p-1.5 bg-slate-100 rounded-2xl shadow-inner">
            {(["tree", "graph", "sunburst", "heatmap"] as ViewMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setViewMode(m)}
                className={cn(
                  "flex-1 py-3 text-[10px] font-black rounded-xl transition-all flex flex-col items-center justify-center gap-1",
                  viewMode === m ? "bg-white text-indigo-600 shadow-xl shadow-indigo-100/50" : "text-slate-400 hover:text-slate-600"
                )}
              >
                {m === "tree" ? "逻辑树" : m === "graph" ? "拓扑网" : m === "sunburst" ? "比例图" : "热力分布"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-3">
          <div className="flex items-center justify-between px-2 mb-4">
             <span className="text-[11px] font-black text-slate-400 uppercase tracking-widest">产业链目录 (Catalog)</span>
             {loading && <RefreshCcw size={14} className="animate-spin text-indigo-500" />}
          </div>
          {AI_INFRA_TREE.map((root) => (
            <RootAccordion 
              key={root.id} 
              node={root} 
              selectedId={selectedId} 
              onSelect={setSelectedId}
              heat={nodeHeatMap[root.id]}
            />
          ))}
        </div>

        <div className="p-6 border-t border-slate-100 bg-white/50">
          <Link href="/research/ai-infra-map" className="flex items-center justify-center gap-3 w-full py-4 rounded-[20px] border border-slate-200 text-xs font-black text-slate-400 hover:bg-white hover:text-indigo-600 hover:border-indigo-100 transition-all shadow-sm active:scale-95">
            <ArrowLeft size={16} /> 返回经典模式
          </Link>
        </div>
      </aside>

      {/* Main Engine */}
      <main className="flex-1 relative flex flex-col">
        <div ref={chartRef} className="flex-1 w-full" />

        {/* Dynamic Tools */}
        <div className="absolute top-10 right-10 flex flex-col gap-4">
           <button 
             onClick={() => setShowInfo(!showInfo)}
             className={cn(
               "p-4 backdrop-blur-xl border rounded-[24px] shadow-2xl transition-all active:scale-90 shadow-slate-200/40 z-40",
               showInfo ? "bg-indigo-600 border-indigo-500 text-white" : "bg-white/90 border-slate-100 text-slate-700 hover:scale-110"
             )}
           >
             <Info size={24} />
           </button>
           <button onClick={exportImg} className="p-4 bg-white/90 backdrop-blur-xl border border-slate-100 rounded-[24px] shadow-2xl hover:scale-110 transition-all active:scale-90 shadow-slate-200/40">
             <Download size={24} className="text-slate-700" />
           </button>
           <button className="p-4 bg-white/90 backdrop-blur-xl border border-slate-100 rounded-[24px] shadow-2xl hover:scale-110 transition-all active:scale-90 shadow-slate-200/40">
             <Maximize2 size={24} className="text-slate-700" />
           </button>
           <div className="h-0.5 bg-slate-100 mx-2" />
           <div className="flex flex-col bg-white/90 backdrop-blur-xl border border-slate-100 rounded-[24px] shadow-2xl shadow-slate-200/40">
             <button 
	               onClick={() => {
	                 if (!chartInstance.current) return;
	                 const zoom = currentChartZoom();
	                 chartInstance.current.setOption({ series: [{ zoom: zoom * 1.2 }] });
	               }}
               className="p-4 hover:bg-slate-50 rounded-t-[24px] border-b border-slate-50"
             >
               <Plus size={20} className="text-slate-500" />
             </button>
	           <button onClick={() => {
	                 if (!chartInstance.current) return;
	                 const zoom = currentChartZoom();
	                 chartInstance.current.setOption({ series: [{ zoom: zoom / 1.2 }] });
	               }}
               className="p-4 hover:bg-slate-50 rounded-b-[24px]"
             >
               <Minus size={20} className="text-slate-500" />
             </button>
             </div>
             </div>

             {/* Hidden Logical Explanation Panel */}
             <AnimatePresence>
             {showInfo && (
             <motion.div 
              initial={{ opacity: 0, scale: 0.9, y: -20, x: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0, x: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: -20, x: 20 }}
              className="absolute top-28 right-10 w-[340px] bg-slate-900/95 backdrop-blur-3xl text-white p-10 rounded-[48px] shadow-[0_40px_80px_-16px_rgba(0,0,0,0.5)] z-40 border border-white/10 ring-1 ring-white/20"
             >
              <div className="flex items-center gap-4 mb-8">
                 <div className="h-10 w-10 rounded-2xl bg-indigo-500 flex items-center justify-center shadow-lg shadow-indigo-500/40">
                    <Target size={20} />
                 </div>
                 <span className="text-[11px] font-black uppercase tracking-[0.3em] text-indigo-300">图谱研报逻辑 (Core)</span>
              </div>

              <div className="space-y-10">
                <div className="group">
                  <div className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3 group-hover:text-indigo-400 transition-colors">方块面积 (Area Weight)</div>
                  <h4 className="text-base font-black mb-3 text-white tracking-tight">市场话题覆盖密度</h4>
                  <p className="text-[12px] leading-relaxed text-slate-400 font-bold">
                    面积代表该环节在近期研报提及、新闻热度及标的活跃度中的**综合总分**。方块越大，代表共识权重越高。
                  </p>
                </div>

                <div className="h-[1px] bg-white/5" />

                <div className="group">
                  <div className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-3 group-hover:text-amber-400 transition-colors">色彩梯度 (Heat Slope)</div>
                  <h4 className="text-base font-black mb-3 text-white tracking-tight">边际爆发强度</h4>
                  <p className="text-[12px] leading-relaxed text-slate-400 font-bold">
                    由黄至红的色彩斜率代表热度的**即时加速度**。颜色越趋近宝石红，代表该逻辑点正在经历剧烈的爆发期。
                  </p>
                </div>
              </div>

              <button 
                onClick={() => setShowInfo(false)}
                className="w-full mt-10 py-5 bg-white/10 hover:bg-white/20 rounded-[24px] text-[11px] font-black uppercase tracking-widest transition-all active:scale-95 border border-white/5"
              >
                了解并返回界面
              </button>
             </motion.div>
             )}
             </AnimatePresence>

             {/* Market Status Legend */}
        <div className="absolute bottom-10 left-10 p-6 bg-white/90 backdrop-blur-xl border border-slate-100 rounded-[40px] shadow-2xl z-20">
          <div className="flex items-center gap-2 mb-4">
            <Radio size={12} className="text-indigo-500 animate-pulse" />
            <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.25em]">实时活跃度分布</span>
          </div>
          <div className="flex items-center gap-1.5 mb-2">
            {HEAT_GRADIENT.map((c, i) => (
              <div key={i} className="h-4 w-9 rounded-md shadow-sm" style={{ backgroundColor: c }} />
            ))}
          </div>
          <div className="flex justify-between text-[9px] font-black text-slate-400">
            <span>基础配置环节</span>
            <span>深度受益环节</span>
          </div>
        </div>

        {/* Intelligence Side Panel */}
        <AnimatePresence mode="wait">
          {selectedNode && (
            <motion.div 
              key={selectedNode.id}
              initial={{ opacity: 0, x: 150 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 150 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              className="absolute top-10 bottom-10 right-10 w-[520px] overflow-y-auto bg-white/98 backdrop-blur-3xl border border-slate-200/60 rounded-[64px] shadow-[0_64px_120px_-32px_rgba(0,0,0,0.18)] p-12 custom-scrollbar z-30 ring-1 ring-white/50"
            >
              <header className="mb-14">
                <div className="flex items-center gap-4 mb-6">
                   <div className="px-5 py-2 bg-slate-900 text-white text-[11px] font-black rounded-full uppercase tracking-[0.2em] shadow-xl shadow-slate-200">{selectedNode.layer}</div>
                   {nodeHeatMap[selectedId] > 120 && (
                     <div className="flex items-center gap-2 px-5 py-2 bg-rose-50 text-rose-600 text-[11px] font-[900] rounded-full uppercase border border-rose-100 shadow-sm animate-pulse">
                       <Flame size={16} /> EXPLOSION
                     </div>
                   )}
                </div>
                <h2 className="text-6xl font-[1000] text-slate-950 tracking-[-0.04em] leading-[0.95] mb-10">{selectedNode.title}</h2>
                
                <div className="grid grid-cols-2 gap-5">
                   <div className="p-8 rounded-[36px] bg-slate-50 border border-slate-100 flex flex-col justify-between">
                      <span className="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-4">活跃指数</span>
                      <div className="text-5xl font-black text-slate-900 tracking-tighter">{nodeHeatMap[selectedId]?.toFixed(0)}</div>
                   </div>
                   <div className="p-8 rounded-[36px] bg-indigo-50 border border-indigo-100 flex flex-col justify-between">
                      <span className="text-[11px] font-black text-indigo-400 uppercase tracking-widest mb-4">链路位置</span>
                      <div className="text-5xl font-black text-indigo-600 tracking-tighter">{selectedNode.depth} LAYER</div>
                   </div>
                </div>
              </header>

              <div className="space-y-14">
                <p className="text-slate-600 text-xl font-bold italic leading-relaxed border-l-[16px] border-slate-100 pl-10 py-2">
                   "{selectedNode.summary}"
                </p>

                {/* Investment Logic Section */}
                {selectedNode.logic && (
                  <div className="p-12 rounded-[56px] bg-slate-950 text-white relative overflow-hidden shadow-2xl">
                    <div className="absolute top-0 right-0 p-12 opacity-5"><Target size={240} /></div>
                    <div className="flex items-center gap-4 mb-10 relative z-10">
                       <div className="h-10 w-10 rounded-2xl bg-amber-400 flex items-center justify-center text-slate-950 shadow-xl shadow-amber-400/20">
                         <Zap size={22} />
                       </div>
                       <span className="text-[14px] font-black uppercase tracking-[0.4em] text-amber-400/60">投研逻辑引擎</span>
                    </div>
                    <ul className="space-y-10 relative z-10">
                      {selectedNode.logic.map((l, i) => (
                        <li key={i} className="text-lg font-bold leading-snug flex gap-6">
                           <span className="h-10 w-10 rounded-2xl bg-white/10 flex items-center justify-center text-[14px] font-black flex-shrink-0 text-white shadow-inner">{i+1}</span>
                           <span className="pt-1">{l}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Target Universe Section */}
                {selectedNode.players && (
                  <div className="space-y-10">
                    <div className="flex items-center gap-4 text-slate-400">
                       <Boxes size={28} />
                       <span className="text-[14px] font-black uppercase tracking-[0.4em]">关联核心标的池</span>
                    </div>
                    <div className="grid grid-cols-1 gap-5">
                      {selectedNode.players.flatMap(p => p.names.map(n => ({ name: n, group: p.group }))).map((obj, i) => (
                        <Link 
                          key={`${obj.name}-${i}`}
                          href={`/stocks/${encodeURIComponent(obj.name)}`}
                          className="group flex items-center justify-between p-8 bg-white border-2 border-slate-100 rounded-[40px] hover:border-slate-950 transition-all hover:shadow-[0_32px_64px_-12px_rgba(0,0,0,0.12)] active:scale-[0.98]"
                        >
                           <div className="flex items-center gap-8">
                              <div className="h-16 w-16 rounded-[28px] bg-slate-50 flex items-center justify-center text-slate-400 group-hover:bg-slate-950 group-hover:text-white transition-all font-black text-2xl shadow-inner uppercase">
                                {obj.name[0]}
                              </div>
                              <div>
                                 <div className="text-2xl font-black text-slate-900 group-hover:text-slate-950 tracking-tight leading-none mb-2">{obj.name}</div>
                                 <div className="text-[11px] font-black text-slate-400 uppercase tracking-[0.2em]">{obj.group}</div>
                              </div>
                           </div>
                           <div className="h-14 w-14 rounded-full border-2 border-slate-50 flex items-center justify-center group-hover:border-slate-950 transition-all group-hover:bg-slate-50">
                              <ArrowUpRight size={24} className="text-slate-300 group-hover:text-slate-950 transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
                           </div>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <footer className="mt-20 sticky bottom-0 bg-white/95 backdrop-blur-3xl pt-10 border-t border-slate-100 flex gap-6">
                 <button className="flex-1 flex items-center justify-center gap-4 py-8 bg-indigo-600 text-white rounded-[36px] text-sm font-black hover:bg-indigo-700 shadow-2xl shadow-indigo-200 active:scale-95 transition-all">
                    <FileText size={24} /> 深度分析报告
                 </button>
                 <button onClick={() => setSelectedId("")} className="px-12 py-8 bg-slate-100 text-slate-500 rounded-[36px] text-sm font-black hover:bg-slate-200 active:scale-95 transition-all">
                    关闭
                 </button>
              </footer>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function RootAccordion({ node, selectedId, onSelect, heat }: { node: AiInfraNode, selectedId: string, onSelect: (id: string) => void, heat: number }) {
  const [isOpen, setIsOpen] = useState(true);
  const isActive = selectedId === node.id;
  const colorSet = getLogicalColor(node.id, node.id);

  return (
    <div className="mb-4">
      <button 
        onClick={() => { onSelect(node.id); setIsOpen(!isOpen); }}
        className={cn(
          "w-full flex items-center justify-between p-5 rounded-[22px] transition-all group",
          isActive ? "bg-white text-slate-950 font-black shadow-xl ring-1 ring-slate-100" : "hover:bg-slate-200/30 text-slate-500 font-bold"
        )}
      >
        <div className="flex items-center gap-4">
          <div className="h-2.5 w-2.5 rounded-full shadow-lg" style={{ backgroundColor: heat > 80 ? getRefinedHeatColor(heat) : colorSet.base }} />
          <span className="text-[13px] truncate tracking-tight">{node.title}</span>
        </div>
        <Plus size={16} className={cn("transition-transform opacity-30", isOpen ? "rotate-45" : "")} />
      </button>
      
      <AnimatePresence>
        {isOpen && node.children && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden ml-6 pl-6 border-l-2 border-slate-200/60 space-y-2 mt-4"
          >
            {node.children.map((child) => (
              <button
                key={child.id}
                onClick={() => onSelect(child.id)}
                className={cn(
                  "w-full text-left p-4 rounded-[18px] text-[12px] font-black transition-all",
                  selectedId === child.id ? "text-indigo-600 bg-indigo-50 shadow-sm" : "text-slate-400 hover:text-slate-800"
                )}
              >
                {child.title}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// --- ECharts Logic Helpers ---

function getLogicalColor(id: string, rootId: string) {
  return LOGIC_COLORS[rootId] || LOGIC_COLORS[id] || { base: "#94a3b8", light: "#cbd5e1", bg: "#f1f5f9" };
}

function getRefinedHeatColor(heat: number) {
  const index = Math.min(HEAT_GRADIENT.length - 1, Math.floor(heat / 30));
  return HEAT_GRADIENT[index];
}

function getTreeOption(rootData: any, selectedId: string) {
  return {
    tooltip: { trigger: 'item' },
    series: [{
      type: 'tree',
      data: [rootData],
      top: '5%', left: '15%', bottom: '5%', right: '20%',
      symbolSize: 18,
      initialTreeDepth: -1,
      expandAndCollapse: true,
      itemStyle: { 
        borderColor: '#fff', borderWidth: 4, shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.1)',
        color: (p: any) => p.data.id === selectedId ? '#1e293b' : p.data.itemStyle?.color || '#4f46e5'
      },
      label: {
        position: 'left', verticalAlign: 'middle', align: 'right', fontSize: 13, fontWeight: '1000',
        color: '#334155', backgroundColor: '#fff', padding: [10, 20], borderRadius: 16, shadowBlur: 20, shadowColor: 'rgba(0,0,0,0.05)'
      },
      leaves: { label: { position: 'right', verticalAlign: 'middle', align: 'left' } },
      lineStyle: { color: '#e5e7eb', width: 4, curveness: 0.5 },
      emphasis: { focus: 'descendant', lineStyle: { width: 6, color: '#818cf8' } }
    }]
  };
}

function getGraphOption(data: any, selectedId: string) {
  return {
    series: [{
      type: 'graph', layout: 'force',
      data: data.nodes, links: data.links, roam: true, draggable: true,
      label: { show: true, position: 'right', formatter: '{b}', fontSize: 12, fontWeight: '900', color: '#334155', textBorderColor: '#fff', textBorderWidth: 4 },
      force: { repulsion: 1500, edgeLength: 220, gravity: 0.1 },
      itemStyle: { borderWidth: (p: any) => p.data.id === selectedId ? 10 : 0, borderColor: '#1e293b' },
      lineStyle: { color: '#f1f5f9', width: 4, opacity: 0.8 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 8, color: '#e2e8f0' } }
    }]
  };
}

function getSunburstOption(rootData: any, selectedId: string) {
  return {
    series: {
      type: 'sunburst', data: rootData.children, radius: [0, '95%'], emphasis: { focus: 'descendant' },
      levels: [
        {},
        { r0: '0%', r: '25%', itemStyle: { borderWidth: 4, borderColor: '#fff' }, label: { rotate: 'tangential', fontSize: 12, fontWeight: '1000', color: '#fff' } },
        { r0: '25%', r: '60%', itemStyle: { borderWidth: 2, borderColor: '#fff' }, label: { align: 'center', fontSize: 10, fontWeight: '800' } },
        { r0: '60%', r: '75%', label: { position: 'outside', padding: 8, fontSize: 9, fontWeight: '1000', color: '#64748b' } }
      ],
      itemStyle: { color: (p: any) => p.data.id === selectedId ? '#1e293b' : p.data.itemStyle?.color }
    }
  };
}

function getTreeMapOption(rootData: any, selectedId: string) {
  return {
    visualMap: { show: false, min: 10, max: 250, inRange: { color: HEAT_GRADIENT } },
    series: [{
      type: 'treemap', data: rootData.children, breadcrumb: { show: false },
      label: { show: true, formatter: (p: any) => `{name|${p.name}}\n{heat|Heat Index: ${p.value.toFixed(0)}}`, rich: { name: { fontSize: 16, fontWeight: '1000', color: '#fff', lineHeight: 24 }, heat: { fontSize: 10, fontWeight: 'bold', color: 'rgba(255,255,255,0.8)' } } },
      itemStyle: { borderColor: '#fff', borderWidth: 8, gapWidth: 8, borderRadius: 32 },
      emphasis: { itemStyle: { shadowBlur: 40, shadowColor: 'rgba(0,0,0,0.3)' } }
    }]
  };
}
