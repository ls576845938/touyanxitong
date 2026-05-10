export function LoadingState({ label = "加载中" }: { label?: string }) {
  return <div className="panel p-6 text-sm text-slate-600">{label}</div>;
}
