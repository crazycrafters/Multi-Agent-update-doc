"use client";
import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Row } from "@/lib/api";
import { ProviderConnection } from "./provider-connection";
import { Button } from "./ui/button";
export function WorkspaceSettings() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api("/settings"),
  });
  const [draft, setDraft] = useState<Row | null>(null),
    [message, setMessage] = useState("");
  useEffect(() => {
    if (data) setDraft(data);
  }, [data]);
  async function save() {
    try {
      await api("/settings", { method: "PUT", body: JSON.stringify(draft) });
      setMessage(
        "Saved. New runs use these settings; running workflows keep their original snapshot.",
      );
      await qc.invalidateQueries({ queryKey: ["usage"] });
    } catch (e) {
      setMessage(String(e));
    }
  }
  return (
    <div className="space-y-5">
      <ProviderConnection />
      {draft && (
        <>
          <section className="panel">
            <h2 className="text-xl font-semibold">Agent working strategies</h2>
            <p className="text-sm text-slate-400 mt-2">
              Customize focus, tone and questioning. Evidence, profile isolation
              and approval rules always apply.
            </p>
            <div className="grid xl:grid-cols-3 gap-4 mt-5">
              {[
                ["resume", "Resume builder"],
                ["interviewee", "Interviewee"],
                ["interviewer", "Adversarial interviewer"],
              ].map(([key, title]) => (
                <label key={key}>
                  {title}
                  <textarea
                    rows={8}
                    maxLength={6000}
                    placeholder={`Working strategy for ${title.toLowerCase()}…`}
                    value={draft.strategies[key]}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        strategies: {
                          ...draft.strategies,
                          [key]: e.target.value,
                        },
                      })
                    }
                  />
                </label>
              ))}
            </div>
          </section>
          <section className="panel">
            <h2 className="text-xl font-semibold">Workflow editor</h2>
            <p className="text-sm text-slate-400 mt-2">
              Customize optional steps. Evidence audit and your final strategy
              choice remain required.
            </p>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-teal-100">
              {[
                "Analyze",
                "Draft",
                "Prepare",
                "Interview",
                "Evaluate",
                "Research",
                "Audit",
                "Choose strategy",
                "Apply & review",
              ].map((x, i) => (
                <span className="rounded bg-slate-800 px-3 py-2" key={x}>
                  {i + 1}. {x}
                </span>
              ))}
            </div>
            <div className="grid md:grid-cols-2 gap-4 mt-5">
              <label>
                Primary questions per iteration
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={draft.workflow.question_count}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      workflow: {
                        ...draft.workflow,
                        question_count: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
              {[
                ["followups", "Adaptive follow-up questions"],
                ["initial_draft", "Initial resume draft"],
                ["research", "External research step (also needs run consent)"],
                [
                  "semantic_retrieval",
                  "Semantic RAG (OpenAI embeddings; also needs run consent)",
                ],
              ].map(([k, t]) => (
                <label className="flex gap-2 items-center" key={k}>
                  <input
                    type="checkbox"
                    checked={draft.workflow[k]}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        workflow: { ...draft.workflow, [k]: e.target.checked },
                      })
                    }
                  />
                  {t}
                </label>
              ))}
            </div>
          </section>
          <section className="panel">
            <h2 className="text-xl font-semibold">API budget & pricing</h2>
            <p className="text-sm text-slate-400 mt-2">
              Enter your provider/model prices. Remaining budget is an estimate,
              not an account balance. One in-flight call can exceed a budget;
              unpriced calls cannot be priced retroactively.
            </p>
            <div className="grid md:grid-cols-3 gap-4 mt-5">
              {[
                ["api_budget_usd", "Budget (USD)"],
                ["input_usd_per_million", "Input / million tokens"],
                ["output_usd_per_million", "Output / million tokens"],
                ["search_usd_per_call", "Web search / call"],
                ["embedding_usd_per_million", "Embeddings / million tokens"],
              ].map(([k, t]) => (
                <label key={k}>
                  {t}
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={draft[k] ?? ""}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        [k]:
                          e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                  />
                </label>
              ))}
            </div>
          </section>
          <Button onClick={save}>Save settings</Button>
          <p role="status" className="text-sm text-teal-200">
            {message}
          </p>
        </>
      )}
    </div>
  );
}
