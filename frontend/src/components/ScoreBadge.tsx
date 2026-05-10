export function ScoreBadge({ score, rating }: { score: number | null; rating: string | null }) {
  const value = score ?? 0;
  const tone =
    value >= 85 ? "bg-mint text-white" : value >= 70 ? "bg-amber text-white" : "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-flex min-w-24 items-center justify-center rounded-md px-3 py-1 text-sm font-semibold ${tone}`}>
      {rating ?? "未评分"} {score === null ? "" : value.toFixed(1)}
    </span>
  );
}
