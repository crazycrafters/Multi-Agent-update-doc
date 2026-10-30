"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
export function UsageBar() {
  const { data } = useQuery({
    queryKey: ["usage"],
    queryFn: () => api("/usage"),
    refetchInterval: 5000,
  });
  const budget = data?.api.budget_usd,
    spent = data?.api.estimated_spent_usd || 0,
    remaining = data?.api.remaining_budget_usd;
  return (
    <div className="flex flex-wrap items-center gap-5 rounded-xl border border-slate-700 bg-slate-900/80 px-5 py-3 mb-6">
      <div>
        <div className="eyebrow">
          Usage ·{" "}
          {data?.provider === "codex" ? "Codex / ChatGPT" : "OpenAI API"}
        </div>
        <div className="text-sm font-semibold text-teal-200 mt-1">
          {data?.provider === "codex"
            ? `${(data.codex.tokens || 0).toLocaleString()} tokens in this app`
            : remaining != null
              ? `$${remaining.toFixed(2)} remaining budget`
              : budget == null
                ? "Set a budget in Settings"
                : "Remaining budget unavailable"}
        </div>
      </div>
      {data?.provider !== "codex" ? (
        <div className="flex-1 min-w-48">
          <div className="flex justify-between text-xs text-slate-400 mb-2">
            <span>Estimated spend ${spent.toFixed(4)}</span>
            <span>
              {budget == null
                ? "Set a budget in Settings"
                : `Budget $${budget.toFixed(2)}`}
            </span>
          </div>
          <div className="h-1.5 rounded bg-slate-700">
            <div
              className="h-full rounded bg-teal-300"
              style={{
                width: budget
                  ? `${Math.min(100, (spent / budget) * 100)}%`
                  : "0%",
              }}
            />
          </div>
          <p className="text-[10px] text-slate-500 mt-1">
            User-set budget, not your OpenAI balance.
            {data?.api.unpriced_calls > 0
              ? ` ${data?.api.unpriced_calls} calls have unknown cost.`
              : ""}
          </p>
        </div>
      ) : (
        <div className="flex flex-1 flex-wrap gap-6">
          {["primary", "secondary"].map((k) => {
            const w = data?.codex.limits?.[k];
            return (
              <div key={k} className="min-w-40 flex-1">
                <div className="text-xs text-slate-400 mb-2">
                  {k === "primary" ? "Primary limit" : "Secondary limit"} ·{" "}
                  {w ? `${w.usedPercent}% used` : "Unavailable"}
                </div>
                <div className="h-1.5 rounded bg-slate-700">
                  <div
                    className={`h-full rounded ${w?.usedPercent >= 90 ? "bg-amber-300" : "bg-violet-400"}`}
                    style={{
                      width: `${Math.max(0, Math.min(100, w?.usedPercent || 0))}%`,
                    }}
                  />
                </div>
                {w?.resetsAt && (
                  <p className="text-[10px] text-slate-500 mt-1">
                    Resets {new Date(w.resetsAt * 1000).toLocaleString()}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
