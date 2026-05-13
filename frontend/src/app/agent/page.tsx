"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Bot, CheckCircle2, Clock, Download, FileText, Loader2, MessageSquare, Play, Printer, Radio, Save, ShieldAlert, Sparkles, Wrench, XCircle } from "lucide-react";
import { api, type AgentArtifact, type AgentFollowupRequest, type AgentMessage, type AgentRunDetail, type AgentRunListItem, type AgentRunResponse, type AgentSSEEvent, type AgentSkill, type AgentStep, type AgentTaskType, type BarRow, type RuntimeHealth } from "@/lib/api";

const FALLBACK_SKILLS: AgentSkill[] = [
  { id: "system:stock_deep_research", name: "个股深度投研", description: "趋势、评分、产业链和证据链报告。", skill_type: "stock_deep_research", skill_md: "", skill_config: {}, owner_user_id: null, is_system: true, created_at: null, updated_at: null },
  { id: "system:industry_chain_radar", name: "产业链雷达", description: "产业链热度、节点和核心股票。", skill_type: "industry_chain_radar", skill_md: "", skill_config: {}, owner_user_id: null, is_system: true, created_at: null, updated_at: null },
  { id: "system:trend_pool_scan", name: "趋势股票池扫描", description: "按评分和动量筛出观察池。", skill_type: "trend_pool_scan", skill_md: "", skill_config: {}, owner_user_id: null, is_system: true, created_at: null, updated_at: null },
  { id: "system:tenbagger_candidate", name: "十倍股早期特征", description: "候选清单和证据缺口。", skill_type: "tenbagger_candidate", skill_md: "", skill_config: {}, owner_user_id: null, is_system: true, created_at: null, updated_at: null },
  { id: "system:daily_market_brief", name: "每日市场简报", description: "强产业链、催化和风险预警。", skill_type: "daily_market_brief", skill_md: "", skill_config: {}, owner_user_id: null, is_system: true, created_at: null, updated_at: null }
];

const EXAMPLES = [
  "帮我分析中际旭创是不是还在主升趋势。",
  "帮我找 AI 服务器产业链今天最强的节点。",
  "帮我筛出当前最有十倍股早期特征的股票池。"
];

function readString(value: unknown, fallback = "未提供") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function readIdList(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" || typeof item === "number" ? String(item) : ""))
    .filter(Boolean);
}

function readConfidence(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) return `${Math.round(value * 100)}%`;
  if (typeof value === "string" && value.trim()) return value;
  return "未提供";
}

function downloadMarkdown(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function AgentPage() {
  const [prompt, setPrompt] = useState(EXAMPLES[0]);
  const [taskType, setTaskType] = useState<AgentTaskType>("auto");
  const [skills, setSkills] = useState<AgentSkill[]>(FALLBACK_SKILLS);
  const [run, setRun] = useState<AgentRunResponse | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [artifact, setArtifact] = useState<AgentArtifact | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sseStatus, setSseStatus] = useState<"idle" | "connecting" | "connected" | "failed">("idle");
  const sseRef = useRef<EventSource | null>(null);
  const completedRef = useRef(false);
  const [followupMessages, setFollowupMessages] = useState<AgentMessage[]>([]);
  const [followupInput, setFollowupInput] = useState("");
  const [followupMode, setFollowupMode] = useState<string>("auto");
  const [sendingFollowup, setSendingFollowup] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingFollowupContent, setStreamingFollowupContent] = useState("");
  const lastSeqRef = useRef<number>(0);
  const [runtimeHealth, setRuntimeHealth] = useState<RuntimeHealth | null>(null);
  const [runHistory, setRunHistory] = useState<AgentRunListItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    api.agentSkills()
      .then((rows) => setSkills(rows.filter((row) => row.is_system).slice(0, 5)))
      .catch(() => setSkills(FALLBACK_SKILLS));
    api.agentRuntimeHealth()
      .then(setRuntimeHealth)
      .catch(() => {});
    setHistoryLoading(true);
    api.agentRunList({ limit: 20 })
      .then(setRunHistory)
      .catch((err) => setHistoryError(err.message))
      .finally(() => setHistoryLoading(false));
  }, []);

  useEffect(() => {
    return () => {
      sseRef.current?.close();
      sseRef.current = null;
    };
  }, []);

  // Replay: reconnect SSE if a run was in progress before page refresh
  useEffect(() => {
    const storedRunId = sessionStorage.getItem("agent_last_run_id");
    if (storedRunId) {
      const runId = parseInt(storedRunId, 10);
      if (!isNaN(runId) && !completedRef.current) {
        api.agentRunDetail(runId).then((detail) => {
          if (detail.status === "running" || detail.status === "pending") {
            setRun({
              run_id: detail.id,
              status: detail.status,
              selected_task_type: detail.task_type,
              report_title: detail.latest_artifact?.title || "Agent 运行中",
              summary: detail.latest_artifact?.content_md?.slice(0, 100) || "正在处理数据...",
              artifact_id: detail.latest_artifact?.id || null,
              warnings: []
            });
            setLoading(true);
            connectSSE(runId, 0);
          } else {
            sessionStorage.removeItem("agent_last_run_id");
          }
        }).catch(() => {
          sessionStorage.removeItem("agent_last_run_id");
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedSkill = useMemo(
    () => skills.find((skill) => skill.skill_type === taskType),
    [skills, taskType]
  );

  async function startRun() {
    const cleaned = prompt.trim();
    if (!cleaned) {
      setError("请输入一个投研问题。");
      return;
    }
    sseRef.current?.close();
    sseRef.current = null;
    completedRef.current = false;
    setLoading(true);
    setError("");
    setRun(null);
    setSteps([]);
    setArtifact(null);
    setSseStatus("idle");
    setFollowupMessages([]);
    setFollowupInput("");
    try {
      const response = await api.agentRun({
        user_prompt: cleaned,
        task_type: taskType,
        time_window: "120d",
        save_as_skill: false
      });
      setRun(response);
      sessionStorage.setItem("agent_last_run_id", String(response.run_id));

      // Try SSE first, fall back to polling
      if (!connectSSE(response.run_id)) {
        pollRunStatus(response.run_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent 投研请求发送失败");
      setLoading(false);
    }
  }

  async function pollRunStatus(runId: number) {
    let attempts = 0;
    const maxAttempts = 30; // 30 seconds max for MVP
    
    const interval = setInterval(async () => {
      attempts++;
      try {
        const detail = await api.agentRunDetail(runId);
        setRun({
          run_id: detail.id,
          status: detail.status,
          selected_task_type: detail.task_type,
          report_title: detail.latest_artifact?.title || "Agent 运行中",
          summary: detail.status === "failed" ? detail.error_message : (detail.latest_artifact?.content_md?.slice(0, 100) || "正在处理数据..."),
          artifact_id: detail.latest_artifact?.id || null,
          warnings: []
        });

        const stepRows = await api.agentRunSteps(runId);
        setSteps(stepRows);

        if (detail.status === "success" || detail.status === "failed") {
          clearInterval(interval);
          setLoading(false);
          if (detail.latest_artifact) {
            setArtifact(detail.latest_artifact);
          }
        }
        
        if (attempts >= maxAttempts) {
          clearInterval(interval);
          setLoading(false);
          setError("等待 Agent 运行超时，请稍后在历史记录中查看。");
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 1000);
  }

  function connectSSE(runId: number, sinceSeq?: number): boolean {
    setSseStatus("connecting");
    let es: EventSource;
    try {
      es = api.agentRunEvents(runId, sinceSeq);
    } catch {
      setSseStatus("failed");
      return false;
    }
    sseRef.current = es;

    function handleSSEEvent(data: AgentSSEEvent) {
      const { event, payload } = data;

      // Dedup by seq
      const seq = data.seq || 0;
      if (seq > 0 && seq <= lastSeqRef.current) return;
      if (seq > 0) lastSeqRef.current = seq;

      switch (event) {
        case "run_started":
          setRun((prev) => prev ? { ...prev, status: "running" } : prev);
          break;
        case "step_started": {
          const step = payload as unknown as AgentStep;
          if (step?.step_name) {
            setSteps((prev) => [...prev, step]);
          }
          break;
        }
        case "tool_call_started": {
          const toolName = String(payload?.tool_name ?? payload?.name ?? "工具调用");
          setSteps((prev) => [
            ...prev,
            {
              id: -(Date.now() * 1000 + Math.floor(Math.random() * 1000)),
              run_id: runId,
              step_name: toolName,
              agent_role: "tool",
              status: "running",
              input_json: payload as Record<string, unknown>,
              output_json: {},
              error_message: "",
              created_at: data.timestamp
            } as AgentStep
          ]);
          break;
        }
        case "tool_call_completed": {
          setSteps((prev) => {
            const copy = [...prev];
            for (let i = copy.length - 1; i >= 0; i--) {
              if (copy[i].agent_role === "tool" && copy[i].status === "running") {
                copy[i] = { ...copy[i], status: "success", output_json: payload as Record<string, unknown> };
                break;
              }
            }
            return copy;
          });
          break;
        }
        case "step_completed": {
          const stepUpd = payload as unknown as AgentStep;
          if (stepUpd?.id) {
            setSteps((prev) => prev.map((s) => s.id === stepUpd.id ? { ...s, ...stepUpd } : s));
          }
          break;
        }
        case "token_delta":
          setStreamingContent((prev) => prev + (typeof payload?.delta === "string" ? payload.delta : ""));
          break;
        case "artifact_created":
          setStreamingContent("");
          api.agentRunArtifacts(runId).then((arts) => {
            if (arts.length > 0) setArtifact(arts[arts.length - 1]);
          }).catch(() => {});
          break;
        case "run_completed":
          completedRef.current = true;
          setStreamingContent("");
          setLoading(false);
          setRun((prev) => prev ? { ...prev, status: "success" } : prev);
          setSseStatus("idle");
          es.close();
          sseRef.current = null;
          sessionStorage.removeItem("agent_last_run_id");
          api.agentRunArtifacts(runId).then((arts) => {
            if (arts.length > 0) setArtifact(arts[arts.length - 1]);
          }).catch(() => {});
          loadFollowupMessages(runId);
          break;
        case "run_failed":
          completedRef.current = true;
          setStreamingContent("");
          setLoading(false);
          setRun((prev) => prev ? { ...prev, status: "failed" } : prev);
          setSseStatus("idle");
          es.close();
          sseRef.current = null;
          sessionStorage.removeItem("agent_last_run_id");
          setError(typeof payload?.error === "string" ? payload.error : "Agent 运行失败");
          break;
        case "followup_started":
          setStreamingFollowupContent("");
          break;
        case "followup_token_delta":
          setStreamingFollowupContent((prev) => prev + (typeof payload?.delta === "string" ? payload.delta : ""));
          break;
        case "followup_completed":
          setStreamingFollowupContent("");
          loadFollowupMessages(runId);
          break;
        case "heartbeat":
          break;
      }
    }

    const sseEventTypes = ["run_started", "step_started", "tool_call_started", "tool_call_completed", "step_completed", "token_delta", "artifact_created", "run_completed", "run_failed", "heartbeat", "followup_started", "followup_token_delta", "followup_completed"];
    for (const evt of sseEventTypes) {
      es.addEventListener(evt, ((msg: MessageEvent) => {
        try { handleSSEEvent(JSON.parse(msg.data) as AgentSSEEvent); }
        catch (e) { console.error(`SSE "${evt}" parse error:`, e); }
      }) as EventListener);
    }

    es.addEventListener("open", () => setSseStatus("connected"));

    es.onerror = () => {
      if (completedRef.current) return;
      es.close();
      sseRef.current = null;
      setSseStatus("failed");
      pollRunStatus(runId);
    };

    return true;
  }

  function loadFollowupMessages(runId: number) {
    api.agentRunMessages(runId).then(setFollowupMessages).catch(() => {});
  }

  async function sendFollowup() {
    const msg = followupInput.trim();
    if (!msg || !run) return;
    setSendingFollowup(true);
    const userMsg: AgentMessage = { role: "user", content: msg, created_at: new Date().toISOString() };
    setFollowupMessages((prev) => [...prev, userMsg]);
    setFollowupInput("");
    try {
      const response = await api.agentRunFollowup(run.run_id, {
        message: msg,
        mode: followupMode as AgentFollowupRequest["mode"]
      });
      const assistantMsg: AgentMessage = {
        role: "assistant",
        content: response.answer_md,
        followup_id: response.followup_id,
        mode: response.mode,
        created_at: response.created_at
      };
      setFollowupMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "追问发送失败");
    } finally {
      setSendingFollowup(false);
    }
  }

  async function loadHistoryRun(item: AgentRunListItem) {
    sseRef.current?.close();
    sseRef.current = null;
    completedRef.current = false;
    setLoading(true);
    setError("");
    setRun(null);
    setSteps([]);
    setArtifact(null);
    setSseStatus("idle");
    setFollowupMessages([]);
    setFollowupInput("");
    try {
      const detail = await api.agentRunDetail(item.id);
      setRun({
        run_id: detail.id,
        status: detail.status,
        selected_task_type: detail.task_type,
        report_title: detail.latest_artifact?.title || item.report_title || "历史运行",
        summary: detail.latest_artifact?.content_md?.slice(0, 100) || "",
        artifact_id: detail.latest_artifact?.id || null,
        warnings: []
      });
      const stepRows = await api.agentRunSteps(item.id);
      setSteps(stepRows);
      const artifacts = await api.agentRunArtifacts(item.id);
      if (artifacts.length > 0) {
        setArtifact(artifacts[artifacts.length - 1]);
      }
      loadFollowupMessages(item.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载历史运行失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
              <Bot size={14} />
              Agent Research
            </div>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-900">Agent 一键投研</h1>
            <p className="mt-2 max-w-3xl text-sm font-medium leading-6 text-slate-500">
              用一句自然语言生成投研工作流，系统只读取平台已有数据，输出投研分析、观察清单、风险提示和证据链。
            </p>
          </div>
          <RuntimeHealthBadge health={runtimeHealth} />
        </section>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <main className="space-y-6">
            <AgentCommandBox
              prompt={prompt}
              loading={loading}
              error={error}
              onPromptChange={setPrompt}
              onSubmit={startRun}
              onExample={setPrompt}
            />

            <SkillTemplatePicker
              skills={skills}
              value={taskType}
              selectedSkill={selectedSkill}
              onChange={setTaskType}
            />

            <ResearchReportViewer loading={loading} run={run} artifact={artifact} error={error} streamingContent={streamingContent} />

            <FollowUpSection
              run={run}
              artifact={artifact}
              followupMessages={followupMessages}
              followupInput={followupInput}
              followupMode={followupMode}
              sendingFollowup={sendingFollowup}
              streamingFollowupContent={streamingFollowupContent}
              show={!!(run && artifact && run.status === "success")}
              onInputChange={setFollowupInput}
              onModeChange={setFollowupMode}
              onSubmit={sendFollowup}
            />
          </main>

          <aside className="space-y-6">
            <AgentRunTimeline loading={loading} steps={steps} run={run} sseStatus={sseStatus} isGenerating={streamingContent !== ""} />
            <RunHistoryPanel runs={runHistory} loading={historyLoading} error={historyError} onSelectRun={loadHistoryRun} />
            <EvidencePanel artifact={artifact} run={run} />
            <SkillBuilderPanel prompt={prompt} run={run} artifact={artifact} />
          </aside>
        </div>
      </div>
    </div>
  );
}

function RunHistoryPanel({ runs, loading, error, onSelectRun }: { runs: AgentRunListItem[]; loading: boolean; error: string; onSelectRun: (item: AgentRunListItem) => void }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
        <Clock size={16} className="text-indigo-600" />
        历史运行
      </div>
      {loading && (
        <div className="flex items-center gap-2 text-sm font-bold text-slate-500">
          <Loader2 size={14} className="animate-spin" />
          加载中...
        </div>
      )}
      {error && (
        <div className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700">{error}</div>
      )}
      {!loading && !error && runs.length === 0 && (
        <div className="rounded-lg bg-slate-50 px-3 py-3 text-xs font-medium text-slate-500">暂无历史运行记录。</div>
      )}
      {!loading && !error && runs.length > 0 && (
        <div className="max-h-80 space-y-2 overflow-y-auto">
          {runs.map((item) => {
            const statusTone =
              item.status === "success"
                ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                : item.status === "failed" || item.status === "error"
                  ? "text-rose-700 bg-rose-50 border-rose-200"
                  : "text-amber-700 bg-amber-50 border-amber-200";
            const dateStr = item.created_at ? new Date(item.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectRun(item)}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-left transition-colors hover:border-indigo-200 hover:bg-indigo-50"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="truncate text-xs font-bold text-slate-800">{item.report_title}</div>
                  <span className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${statusTone}`}>
                    {item.status}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-[10px] font-bold text-slate-400">
                  <span>{item.task_type}</span>
                  {dateStr && <span>&middot; {dateStr}</span>}
                  <span>&middot; #{item.id}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function AgentCommandBox({
  prompt,
  loading,
  error,
  onPromptChange,
  onSubmit,
  onExample
}: {
  prompt: string;
  loading: boolean;
  error: string;
  onPromptChange: (value: string) => void;
  onSubmit: () => void;
  onExample: (value: string) => void;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
        <Sparkles size={16} className="text-indigo-600" />
        Command
      </div>
      <textarea
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
        rows={4}
        className="w-full resize-none rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm font-medium leading-6 text-slate-800 outline-none focus:border-indigo-400 focus:bg-white"
        placeholder="输入你的投研问题"
      />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => onExample(item)}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-500 hover:border-indigo-200 hover:text-indigo-700"
            >
              {item}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onSubmit}
          disabled={loading}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-black text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          开始一键投研
        </button>
      </div>
      {error && (
        <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
          {error}
        </div>
      )}
    </section>
  );
}

function SkillTemplatePicker({
  skills,
  value,
  selectedSkill,
  onChange
}: {
  skills: AgentSkill[];
  value: AgentTaskType;
  selectedSkill?: AgentSkill;
  onChange: (value: AgentTaskType) => void;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="text-xs font-black uppercase tracking-widest text-slate-500">System Skills</div>
        <select
          value={value}
          onChange={(event) => onChange(event.target.value as AgentTaskType)}
          className="h-9 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs font-bold text-slate-600 outline-none"
        >
          <option value="auto">Auto</option>
          {skills.map((skill) => (
            <option key={String(skill.id)} value={skill.skill_type}>
              {skill.name}
            </option>
          ))}
        </select>
      </div>
      <div className="grid gap-3 md:grid-cols-5">
        {skills.map((skill) => {
          const active = value === skill.skill_type;
          return (
            <button
              key={String(skill.id)}
              type="button"
              onClick={() => onChange(skill.skill_type as AgentTaskType)}
              className={`min-h-28 rounded-lg border p-3 text-left transition-colors ${
                active ? "border-indigo-300 bg-indigo-50 text-indigo-900" : "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300"
              }`}
            >
              <div className="text-sm font-black">{skill.name}</div>
              <div className="mt-2 text-xs font-medium leading-5 text-slate-500">{skill.description}</div>
            </button>
          );
        })}
      </div>
      <div className="mt-3 text-xs font-medium text-slate-500">
        当前模板：{value === "auto" ? "系统自动识别" : selectedSkill?.name ?? value}
      </div>
    </section>
  );
}

function AgentRunTimeline({ loading, steps, run, sseStatus, isGenerating }: { loading: boolean; steps: AgentStep[]; run: AgentRunResponse | null; sseStatus: "idle" | "connecting" | "connected" | "failed"; isGenerating: boolean }) {
  const failedSteps = steps.filter((step) => step.status !== "success");

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="text-xs font-black uppercase tracking-widest text-slate-500">Run Timeline</div>
          {sseStatus === "connected" && (
            <span className="flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-600">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              SSE
            </span>
          )}
          {sseStatus === "connecting" && (
            <span className="flex items-center gap-1 rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold text-amber-600">
              <Radio size={10} />
              Conn
            </span>
          )}
          {sseStatus === "failed" && (
            <span className="flex items-center gap-1 rounded-md bg-rose-50 px-1.5 py-0.5 text-[10px] font-bold text-rose-600">
              Polling
            </span>
          )}
        </div>
        {run && <span className="rounded-lg bg-slate-100 px-2 py-1 text-[10px] font-black uppercase text-slate-500">#{run.run_id}</span>}
      </div>
      {run && <RunSummaryCard loading={loading} run={run} />}
      {loading && steps.length === 0 && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-3 text-sm font-bold text-indigo-700">
          <Loader2 size={16} className="animate-spin" />
          正在执行投研工作流，步骤和报告会在本次运行完成后刷新。
        </div>
      )}
      {isGenerating && (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-3 text-sm font-bold text-indigo-700">
          <Loader2 size={16} className="animate-spin" />
          报告生成中...
        </div>
      )}
      {!loading && steps.length === 0 && (
        <div className="mt-4 rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium leading-6 text-slate-500">
          {run ? "本次运行还没有返回步骤明细。可以先查看摘要、报告区和证据面板。" : "执行后会展示任务识别、工具调用、报告生成和合规检查步骤。"}
        </div>
      )}
      {failedSteps.length > 0 && (
        <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-bold leading-5 text-rose-700">
          {failedSteps.length} 个步骤未成功，请优先检查带红色提示的节点。
        </div>
      )}
      <div className="mt-4 space-y-3">
        {steps.map((step) => (
          <div key={step.id} className="flex gap-3">
            <div className="mt-0.5">
              {step.agent_role === "tool" ? (
                <Wrench size={16} className={step.status === "success" ? "text-indigo-500" : "text-amber-500 animate-pulse"} />
              ) : step.status === "success" ? (
                <CheckCircle2 size={16} className="text-emerald-600" />
              ) : (
                <XCircle size={16} className="text-rose-600" />
              )}
            </div>
            <div>
              <div className="text-sm font-black text-slate-800">{step.step_name}</div>
              <div className="text-xs font-bold text-slate-400">{step.agent_role}</div>
              {step.error_message && <div className="mt-1 text-xs font-bold text-rose-600">{step.error_message}</div>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RunSummaryCard({ loading, run }: { loading: boolean; run: AgentRunResponse }) {
  const statusTone =
    run.status === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : run.status === "failed" || run.status === "error"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : "border-indigo-200 bg-indigo-50 text-indigo-700";

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-black text-slate-900">{run.report_title || "未命名运行"}</div>
        <span className={`rounded-lg border px-2 py-1 text-[10px] font-black uppercase ${statusTone}`}>
          {loading ? "running" : run.status}
        </span>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <SummaryMetric label="Task Type" value={run.selected_task_type} />
        <SummaryMetric label="Artifact ID" value={run.artifact_id === null ? "待生成" : String(run.artifact_id)} />
        <SummaryMetric label="Run ID" value={`#${run.run_id}`} />
      </div>
      <div className="mt-3 rounded-lg bg-white px-3 py-3 text-sm font-medium leading-6 text-slate-600">
        {run.summary || "本次运行暂未返回摘要。"}
      </div>
    </div>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white px-3 py-2">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className="mt-1 text-sm font-bold text-slate-700">{value}</div>
    </div>
  );
}

function ResearchReportViewer({
  loading,
  run,
  artifact,
  error,
  streamingContent
}: {
  loading: boolean;
  run: AgentRunResponse | null;
  artifact: AgentArtifact | null;
  error: string;
  streamingContent: string;
}) {
  function handleDownloadMarkdown() {
    if (!artifact) return;
    const title = artifact.title || "投研报告";
    const filename = `alpha-radar-report-${artifact.run_id}.md`;
    const content = `# ${title}\n\n${artifact.content_md}`;
    downloadMarkdown(content, filename);
  }

  function handlePrintPdf() {
    window.print();
  }

  function handleOpenPrintView() {
    if (!artifact) return;
    window.open(api.agentRunExportPrintUrl(artifact.run_id), "_blank");
  }

  function handleOpenRichReport() {
    if (!artifact) return;
    window.open(api.agentRunExportRichHtmlUrl(artifact.run_id), "_blank");
  }

  function handleExportWithCharts() {
    if (!artifact) return;
    const chartDataUrls = captureAllChartDataUrls();
    const html = buildExportHtml(artifact, chartDataUrls);
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    window.open(URL.createObjectURL(blob));
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
      {/* Print CSS: hides sidebar, inputs, buttons, timeline, evidence panel */}
      <style>{`
        @media print {
          body * {
            visibility: hidden;
          }
          .report-print-area,
          .report-print-area * {
            visibility: visible;
          }
          .report-print-area {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            padding: 0.5in;
          }
          .report-print-area h1 { font-size: 22pt; }
          .report-print-area h2 { font-size: 16pt; }
          .report-print-area p, .report-print-area li { font-size: 11pt; }
          .no-print { display: none !important; }
          @page { margin: 0.5in; }
        }
      `}</style>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
          <FileText size={16} className="text-indigo-600" />
          Research Report
        </div>
        <div className="flex items-center gap-2">
          {run && <div className="text-xs font-bold text-slate-500">{run.selected_task_type}</div>}
          {artifact && (
            <div className="flex flex-wrap items-center gap-1.5 no-print">
              <button
                type="button"
                onClick={handleDownloadMarkdown}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 hover:border-slate-300 hover:text-slate-800"
                title="导出 Markdown"
              >
                <Download size={14} />
                导出 .md
              </button>
              <button
                type="button"
                onClick={handleExportWithCharts}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-indigo-200 bg-white px-3 text-xs font-bold text-indigo-600 hover:border-indigo-300 hover:text-indigo-800"
                title="导出含图表 HTML（捕获当前页面中的动态图表截图）"
              >
                <Download size={14} />
                导出含图表 HTML
              </button>
              <button
                type="button"
                onClick={handleOpenRichReport}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-3 text-xs font-bold text-emerald-600 hover:border-emerald-300 hover:text-emerald-800"
                title="导出图文报告（在新标签页中打开含图表描述的打印版）"
              >
                <FileText size={14} />
                导出图文报告
              </button>
              <button
                type="button"
                onClick={handleOpenPrintView}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 hover:border-slate-300 hover:text-slate-800"
                title="打开打印版（Ctrl+P 保存为 PDF）"
              >
                <Printer size={14} />
                打印版导出
              </button>
              <button
                type="button"
                onClick={handlePrintPdf}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-xs font-bold text-slate-600 hover:border-slate-300 hover:text-slate-800"
                title="打印 PDF"
              >
                <Printer size={14} />
                打印 PDF
              </button>
            </div>
          )}
        </div>
      </div>
      <div className="report-print-area p-5">
        {loading && (
          <div className="flex min-h-80 items-center justify-center text-sm font-bold text-slate-500">
            <Loader2 size={18} className="mr-2 animate-spin" />
            正在生成结构化报告
          </div>
        )}
        {!loading && error && !artifact && (
          <div className="flex min-h-80 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-6 text-sm font-bold leading-6 text-rose-700">
            运行未完成，暂时没有可展示的报告。请先处理上方错误后重新执行。
          </div>
        )}
        {!loading && run && !error && !artifact && (
          <div className="flex min-h-80 flex-col items-center justify-center rounded-lg border border-dashed border-amber-200 bg-amber-50 px-6 text-center text-sm font-medium leading-6 text-amber-800">
            <div className="font-black">本次运行已返回摘要，但还没有生成最终报告。</div>
            <div className="mt-2 max-w-xl">{run.summary || "请查看右侧时间线和证据面板，确认是否有失败步骤或缺失输出。"}</div>
          </div>
        )}
        {!loading && !run && !artifact && (
          <div className="flex min-h-80 items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-sm font-medium text-slate-500">
            输入投研问题后，这里会显示 Markdown 报告。
          </div>
        )}
        {artifact && <MarkdownBlock content={artifact.content_md} />}
        {streamingContent && (
          <div className="mt-4 rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
            <div className="mb-2 flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-indigo-400">
              <Loader2 size={12} className="animate-spin" />
              报告生成中...
            </div>
            <MarkdownBlock content={streamingContent} />
          </div>
        )}
      </div>
    </section>
  );
}

function EvidencePanel({ artifact, run }: { artifact: AgentArtifact | null; run: AgentRunResponse | null }) {
  const refs = artifact?.evidence_refs ?? [];
  const claims = artifact?.claims?.length
    ? artifact.claims
    : Array.isArray(artifact?.content_json?.claims)
    ? (artifact.content_json.claims as Record<string, unknown>[])
    : [];
  const warnings = run?.warnings ?? [];
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
        <ShieldAlert size={16} className="text-amber-600" />
        Evidence & Risk
      </div>
      <div className="space-y-4">
        <InfoBlock label="证据来源" empty={run ? "本次运行未返回证据来源。" : "运行后会展示证据来源。"}>
          {refs.map((ref, index) => (
            <div key={index} className="rounded-lg bg-slate-50 p-3 text-xs font-medium leading-5 text-slate-600">
              <div className="flex items-start gap-2">
                <span className="rounded-md bg-slate-900 px-1.5 py-0.5 text-[10px] font-black text-white">{String(ref.id ?? `S${index + 1}`)}</span>
                <div className="font-black text-slate-800">{String(ref.title ?? ref.source ?? `证据 ${index + 1}`)}</div>
              </div>
              <div className="mt-1 text-[11px] font-bold text-slate-400">
                {String(ref.source ?? "alpha_radar_tool")} · {String(ref.tool_name ?? ref.kind ?? "source")}
              </div>
              {typeof ref.url === "string" && ref.url && <div className="mt-1 break-all text-slate-400">{ref.url}</div>}
            </div>
          ))}
        </InfoBlock>
        <InfoBlock label="Claim 引用" empty={run ? "本次运行未返回 Claim 级引用。" : "运行后会展示 Claim 级引用。"}>
          {claims.map((claim, index) => {
            const claimRow = claim as Record<string, unknown>;
            const claimId = readString(claimRow.id, `C${index + 1}`);
            const section = readString(claimRow.section, "结论");
            const text = readString(claimRow.text, "该 Claim 未返回正文。");
            const sourceIds = readIdList(claimRow.evidence_ref_ids ?? claimRow.source_ids ?? claimRow.sources);
            const confidence = readConfidence(claimRow.confidence);
            const uncertainty = readString(claimRow.uncertainty, readString(claimRow.uncertainty_note, "未说明"));

            return (
              <div key={claimId} className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs font-medium leading-5 text-slate-600">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-slate-900 px-1.5 py-0.5 text-[10px] font-black text-white">{claimId}</span>
                  <div className="font-black text-slate-800">{section}</div>
                </div>
                <div className="mt-2 text-sm leading-6 text-slate-700">{text}</div>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  <ClaimMeta label="来源 ID" value={sourceIds.length > 0 ? sourceIds.join("、") : "未提供"} />
                  <ClaimMeta label="置信度" value={confidence} />
                  <ClaimMeta label="不确定性" value={uncertainty} />
                </div>
              </div>
            );
          })}
        </InfoBlock>
        <InfoBlock label="风险提示" empty={run ? "本次运行没有返回额外风险提示。" : "执行后展示风险提示。"}>
          {warnings.map((item) => (
            <div key={item} className="rounded-lg bg-amber-50 p-3 text-xs font-bold leading-5 text-amber-800">{item}</div>
          ))}
        </InfoBlock>
        {artifact && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs font-bold leading-5 text-slate-600">
            {artifact.risk_disclaimer}
          </div>
        )}
      </div>
    </section>
  );
}

function ClaimMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white px-3 py-2">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      <div className="mt-1 text-xs font-bold text-slate-700">{value}</div>
    </div>
  );
}

function SkillBuilderPanel({ prompt, run, artifact }: { prompt: string; run: AgentRunResponse | null; artifact: AgentArtifact | null }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<AgentSkill | null>(null);
  const [error, setError] = useState("");

  async function saveSkill() {
    if (!run || !artifact) return;
    setSaving(true);
    setError("");
    try {
      const skill = await api.createAgentSkill({
        name: `${artifact.title} Skill`,
        description: `由一键投研保存：${prompt.slice(0, 80)}`,
        skill_type: run.selected_task_type,
        skill_md: artifact.content_md,
        skill_config: {
          run_id: run.run_id,
          artifact_id: artifact.id,
          user_prompt: prompt,
          selected_task_type: run.selected_task_type
        },
        is_system: false
      });
      setSaved(skill);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存 Skill 失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 text-xs font-black uppercase tracking-widest text-slate-500">Skill Builder</div>
      <p className="text-sm font-medium leading-6 text-slate-500">将当前成功流程保存为可复用 Skill，下次可直接选择模板复用。</p>
      <button
        type="button"
        disabled={!run || !artifact || saving}
        onClick={saveSkill}
        className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 text-sm font-black text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
        保存为我的 Skill
      </button>
      {!run && <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs font-bold text-slate-500">运行完成并生成报告后，才能保存为 Skill。</div>}
      {run && !artifact && <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs font-bold text-slate-500">本次运行还没有可复用的报告产物，暂不能保存。</div>}
      {saved && <div className="mt-3 rounded-lg bg-emerald-50 p-3 text-xs font-black text-emerald-700">已保存：{saved.name}</div>}
      {error && <div className="mt-3 rounded-lg bg-rose-50 p-3 text-xs font-black text-rose-700">{error}</div>}
    </section>
  );
}

function RuntimeHealthBadge({ health }: { health: RuntimeHealth | null }) {
  const [expanded, setExpanded] = useState(false);

  if (!health) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs font-bold text-slate-400">
        检查运行时状态...
      </div>
    );
  }

  const isHealthy = health.llm_configured || health.hermes_configured;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs font-bold text-slate-500 hover:border-slate-300"
      >
        <span className={`inline-block h-2 w-2 rounded-full ${isHealthy ? 'bg-emerald-500' : 'bg-amber-500'}`} />
        Runtime: {health.runtime_provider}
      </button>
      {expanded && (
        <div className="absolute right-0 top-full z-20 mt-2 w-64 rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-400">LLM</span>
              <span className={health.llm_configured ? 'font-bold text-emerald-600' : 'font-bold text-rose-600'}>
                {health.llm_configured ? '已配置' : '未配置'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Hermes</span>
              <span className={health.hermes_configured ? 'font-bold text-emerald-600' : 'text-slate-400'}>
                {health.hermes_configured ? '已配置' : '未配置'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">流式支持</span>
              <span className={health.streaming_supported ? 'font-bold text-emerald-600' : 'font-bold text-amber-600'}>
                {health.streaming_supported ? '支持' : '不支持'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">追问 LLM</span>
              <span className={health.followup_llm_enabled ? 'font-bold text-emerald-600' : 'text-slate-400'}>
                {health.followup_llm_enabled ? '已启用' : '模板回退'}
              </span>
            </div>
            {health.warnings.length > 0 && (
              <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
                {health.warnings.map((w, i) => (
                  <div key={i} className="rounded bg-amber-50 px-2 py-1 text-[10px] text-amber-700">{w}</div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function InfoBlock({ label, empty, children }: { label: string; empty: string; children: ReactNode }) {
  const childArray = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : [];
  return (
    <div>
      <div className="mb-2 text-[10px] font-black uppercase tracking-widest text-slate-400">{label}</div>
      {childArray.length > 0 ? <div className="space-y-2">{children}</div> : <div className="rounded-lg bg-slate-50 p-3 text-xs font-bold text-slate-400">{empty}</div>}
    </div>
  );
}

import { CandleChart, captureAllChartDataUrls } from "@/components/CandleChart";
import { IndustryHeatChart } from "@/components/IndustryHeatChart";

function MarkdownBlock({ content }: { content: string }) {
  return (
    <article className="space-y-3 text-sm leading-7 text-slate-700">
      {content.split("\n").map((line, index) => {
        const trimmed = line.trim();
        
        // Dynamic Chart Parsing
        if (trimmed.startsWith(":::chart") && trimmed.endsWith(":::")) {
          try {
            const rawJson = trimmed.slice(8, -3);
            const config = JSON.parse(rawJson);
            if (config.type === "candle" && config.symbol) {
              return <StockChartMount key={index} symbol={config.symbol} />;
            }
            if (config.type === "industry_heat") {
              return <IndustryHeatMount key={index} />;
            }
          } catch (err) {
            console.error("Failed to parse chart tag:", err);
            return <div key={index} className="text-xs text-rose-400 italic">[无效的图表配置]</div>;
          }
        }

        if (line.startsWith("# ")) {
          return <h1 key={index} className="pb-2 text-2xl font-black tracking-tight text-slate-950">{line.replace(/^# /, "")}</h1>;
        }
        if (line.startsWith("## ")) {
          return <h2 key={index} className="pt-4 text-base font-black text-slate-900">{line.replace(/^## /, "")}</h2>;
        }
        if (line.startsWith("- ")) {
          return <p key={index} className="rounded-lg bg-slate-50 px-3 py-2 font-medium text-slate-600">{line}</p>;
        }
        if (line.trim() === "---") {
          return <hr key={index} className="border-slate-200" />;
        }
        if (!line.trim()) {
          return <div key={index} className="h-1" />;
        }
        return <p key={index} className="font-medium text-slate-600">{line}</p>;
      })}
    </article>
  );
}

function buildExportHtml(
  artifact: AgentArtifact,
  chartDataUrls: Record<string, string>,
): string {
  const title = artifact.title || "投研报告";
  const contentMd = artifact.content_md || "";

  // Parse content_md into basic HTML, replacing chart tags with <img>
  const lines = contentMd.split("\n");
  const htmlParts: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();

    // Chart tag replacement
    if (trimmed.startsWith(":::chart") && trimmed.endsWith(":::")) {
      try {
        const rawJson = trimmed.slice(8, -3);
        const config = JSON.parse(rawJson);
        const chartType = config.type as string;
        const symbol = config.symbol as string | undefined;

        let imgSrc: string | undefined;
        if (chartType === "candle" && symbol && chartDataUrls[symbol]) {
          imgSrc = chartDataUrls[symbol];
        } else if (chartType === "industry_heat" && chartDataUrls["industry-heat"]) {
          imgSrc = chartDataUrls["industry-heat"];
        }

        if (imgSrc) {
          htmlParts.push(`<div style="margin:1em 0;text-align:center;"><img src="${imgSrc}" style="max-width:100%;border:1px solid #e2e8f0;border-radius:8px;" alt="chart" /></div>`);
        } else {
          // Fallback to placeholder
          const label = chartType === "candle" ? `K线图${symbol ? ` - ${symbol}` : ""}` : chartType || "图表";
          htmlParts.push(`<div style="background:#f1f5f9;border:1px dashed #94a3b8;border-radius:8px;padding:1.5em;text-align:center;color:#64748b;margin:1em 0;font-weight:600;">[图表: ${label}]</div>`);
        }
      } catch {
        htmlParts.push(`<div style="background:#f1f5f9;border:1px dashed #94a3b8;border-radius:8px;padding:1.5em;text-align:center;color:#64748b;margin:1em 0;">[图表占位]</div>`);
      }
      continue;
    }

    if (trimmed.startsWith("# ")) {
      htmlParts.push(`<h1 style="font-size:1.8rem;font-weight:800;margin-top:0;margin-bottom:0.5em;border-bottom:2px solid #1e293b;padding-bottom:0.3em;">${escapeHtml(trimmed.slice(2))}</h1>`);
    } else if (trimmed.startsWith("## ")) {
      htmlParts.push(`<h2 style="font-size:1.35rem;font-weight:700;margin-top:1.5em;margin-bottom:0.5em;color:#0f172a;">${escapeHtml(trimmed.slice(3))}</h2>`);
    } else if (trimmed.startsWith("### ")) {
      htmlParts.push(`<h3 style="font-size:1.1rem;font-weight:700;margin-top:1.2em;margin-bottom:0.4em;color:#334155;">${escapeHtml(trimmed.slice(4))}</h3>`);
    } else if (trimmed.startsWith("- ")) {
      htmlParts.push(`<li style="margin-bottom:0.3em;">${escapeHtml(trimmed.slice(2))}</li>`);
    } else if (trimmed === "---") {
      htmlParts.push(`<hr style="border:none;border-top:1px solid #e2e8f0;margin:1.5em 0;" />`);
    } else if (trimmed) {
      htmlParts.push(`<p style="margin-bottom:0.8em;line-height:1.8;">${escapeHtml(trimmed)}</p>`);
    } else {
      htmlParts.push(`<br />`);
    }
  }

  const body = htmlParts.join("\n");

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>${escapeHtml(title)} - Alpha Radar 报告</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    color: #1e293b; line-height: 1.8; max-width: 210mm; margin: 0 auto; padding: 2em;
  }
  h1, h2, h3 { color: #0f172a; }
  img { max-width: 100%; height: auto; }
  .risk-disclaimer {
    font-size: 0.8rem; color: #64748b; text-align: center;
    margin-top: 2em; padding: 1em;
    border: 1px solid #e2e8f0; border-radius: 6px; background: #fafafa;
  }
  @media print {
    @page { margin: 15mm 20mm; size: A4; }
    body { padding: 0; color: #000; }
  }
</style>
</head>
<body>
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:0.5em;border-bottom:2px solid #1e293b;padding-bottom:0.3em;">${escapeHtml(title)}</h1>
${body}
<hr style="border:none;border-top:1px solid #e2e8f0;margin:2em 0;" />
<div class="risk-disclaimer">${escapeHtml(artifact.risk_disclaimer)}</div>
</body>
</html>`;
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function StockChartMount({ symbol }: { symbol: string }) {
  const [rows, setRows] = useState<BarRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.stockBars(symbol)
      .then(setRows)
      .finally(() => setLoading(false));
  }, [symbol]);

  return (
    <div className="my-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/50 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
        Interactive Chart: {symbol}
      </div>
      <div className="p-4">
        {loading ? (
          <div className="flex h-[400px] items-center justify-center text-xs font-bold text-slate-400">
            <Loader2 size={16} className="mr-2 animate-spin" />
            正在加载行情数据...
          </div>
        ) : (
          <CandleChart rows={rows} chartId={symbol} />
        )}
      </div>
    </div>
  );
}

function IndustryHeatMount() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.industryRadar()
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="my-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50/50 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-400">
        Industry Heatmap
      </div>
      <div className="p-4">
        {loading ? (
          <div className="flex h-[400px] items-center justify-center text-xs font-bold text-slate-400">
            <Loader2 size={16} className="mr-2 animate-spin" />
            正在生成热力图...
          </div>
        ) : (
          <IndustryHeatChart rows={data || []} chartId="industry-heat" />
        )}
      </div>
    </div>
  );
}

function FollowUpSection({
  run,
  artifact,
  followupMessages,
  followupInput,
  followupMode,
  sendingFollowup,
  streamingFollowupContent,
  show,
  onInputChange,
  onModeChange,
  onSubmit
}: {
  run: AgentRunResponse | null;
  artifact: AgentArtifact | null;
  followupMessages: AgentMessage[];
  followupInput: string;
  followupMode: string;
  sendingFollowup: boolean;
  streamingFollowupContent: string;
  show: boolean;
  onInputChange: (value: string) => void;
  onModeChange: (value: string) => void;
  onSubmit: () => void;
}) {
  if (!show) return null;

  const modes = [
    { key: "auto", label: "Auto" },
    { key: "expand_risk", label: "展开风险" },
    { key: "evidence_drilldown", label: "证据深挖" },
    { key: "explain", label: "展开说说" }
  ];

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-xs font-black uppercase tracking-widest text-slate-500">
        <MessageSquare size={16} className="text-indigo-600" />
        追问
      </div>

      {followupMessages.length > 0 && (
        <div className="mb-4 max-h-80 space-y-3 overflow-y-auto">
          {followupMessages.map((msg, i) => (
            <div key={msg.followup_id ?? msg.id ?? i} className={`rounded-lg p-3 ${msg.role === "user" ? "border border-indigo-100 bg-indigo-50" : "bg-slate-50"}`}>
              <div className="mb-1 text-[10px] font-black uppercase tracking-widest text-slate-400">
                {msg.role === "user" ? "我的提问" : `Agent${msg.mode ? ` · ${msg.mode}` : ""}`}
              </div>
              <div className="text-sm font-medium leading-6 text-slate-700">{msg.content}</div>
            </div>
          ))}
          {streamingFollowupContent && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50/50 p-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-indigo-400">
                <Loader2 size={10} className="animate-spin" />
                Agent 思考中...
              </div>
              <div className="text-sm font-medium leading-6 text-slate-700">{streamingFollowupContent}</div>
            </div>
          )}
        </div>
      )}

      <div className="mb-3 flex flex-wrap gap-2">
        {modes.map((m) => (
          <button
            key={m.key}
            type="button"
            onClick={() => onModeChange(m.key)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-bold ${
              followupMode === m.key ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "border-slate-200 text-slate-500 hover:border-slate-300"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={followupInput}
          onChange={(e) => onInputChange(e.target.value)}
          placeholder="追问：展开说说风险因素"
          className="flex-1 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-medium text-slate-800 outline-none focus:border-indigo-400 focus:bg-white"
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={sendingFollowup || !followupInput.trim()}
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-indigo-600 px-4 text-sm font-black text-white disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {sendingFollowup ? <Loader2 size={16} className="animate-spin" /> : <MessageSquare size={16} />}
          发送
        </button>
      </div>
    </section>
  );
}
