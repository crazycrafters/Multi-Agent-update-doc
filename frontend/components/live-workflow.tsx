"use client";
import {
  Activity,
  FileText,
  MessageSquare,
  Search,
  Sparkles,
} from "lucide-react";
import { type Row, type StreamEvent } from "@/lib/api";
const phases = [
  ["RESUME_ANALYSIS", "Analyze"],
  ["RESUME_DRAFTING", "Draft"],
  ["INTERVIEW_PREPARATION", "Prepare"],
  ["INTERVIEWING", "Interview"],
  ["INTERVIEW_EVALUATION", "Evaluate"],
  ["RESEARCHING", "Research"],
  ["EVIDENCE_VALIDATION", "Audit"],
  ["RESUME_REVISION", "Revise"],
];
export function LiveWorkflow({
  run,
  events,
}: {
  run?: Row;
  events: StreamEvent[];
}) {
  const iteration = run?.iteration;
  const state = iteration?.state || "IDLE";
  const current = phases.findIndex(([s]) => s === state);
  const running =
    iteration &&
    !["AWAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED"].includes(
      state,
    ) &&
    !iteration.paused;
  const working = running
    ? run?.executions.findLast((e: Row) => e.status === "running") || {
        agent: ["INTERVIEW_PREPARATION", "INTERVIEW_EVALUATION"].includes(state)
          ? "interviewee"
          : state === "INTERVIEWING"
            ? "interviewer"
            : "resume",
        task: "Preparing phase context…",
      }
    : null;
  return (
    <section className="space-y-4">
      <div className="panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="eyebrow">Live workflow</div>
            <h2 className="text-lg font-semibold mt-2">
              {iteration?.paused ? "Paused" : state.replaceAll("_", " ")}
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              {working?.task ||
                (state === "AWAITING_APPROVAL"
                  ? "Review the proposed strategies below."
                  : "Current work and retrieved context appear as the agents execute.")}
            </p>
          </div>
          <div className="text-xs text-teal-200">
            Iteration {iteration?.run_step || 1} /{" "}
            {iteration?.planned_iterations || 1} ·{" "}
            {run?.transcript.filter((t: Row) => !t.question.followup).length ||
              0}{" "}
            / {iteration?.checkpoint?.settings?.workflow?.question_count || 10}{" "}
            primary questions
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-2 mt-6">
          {phases.map(([key, title], i) => (
            <div
              key={key}
              className={`rounded-xl border p-3 text-xs ${current === i ? "border-teal-300 bg-teal-950 text-teal-100" : i < current || ["AWAITING_APPROVAL", "COMPLETED"].includes(state) ? "border-teal-900 text-teal-300" : "border-slate-700 text-slate-500"}`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 rounded-full ${current === i && running ? "agent-spark bg-teal-200" : "bg-current"}`}
                />
                {i + 1}. {title}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="grid xl:grid-cols-3 gap-4">
        {[
          ["resume", "Resume builder", FileText],
          ["interviewee", "Interviewee", MessageSquare],
          ["interviewer", "Adversarial interviewer", Activity],
        ].map(([role, title, Icon]) => {
          const agent = String(role),
            isWorking = working?.agent === agent;
          const messages = events.filter((e) => e.agent === agent);
          const lastTask = messages.findLast((e) => e.kind === "task_started")
            ?.data.task;
          const live = messages.findLast(
            (e) => e.kind === "answer_snapshot" && e.data.task === lastTask,
          );
          const complete = messages.findLast(
            (e) => e.kind === "task_completed" && e.data.task === lastTask,
          );
          const retrieval = messages.findLast(
            (e) => e.kind === "knowledge_retrieved",
          );
          return (
            <article
              key={agent}
              className={`panel !p-5 transition-shadow ${isWorking ? "border-teal-400 shadow-[0_0_24px_#2dd4bf18]" : ""}`}
            >
              <div className="flex gap-2 items-center">
                <span
                  className={`w-2 h-2 rounded-full ${isWorking ? "agent-spark bg-teal-200" : "bg-slate-600"}`}
                />
                {typeof Icon !== "string" && (
                  <Icon size={16} className="text-teal-200" />
                )}
                <h3 className="font-semibold text-sm">{String(title)}</h3>
                {isWorking && (
                  <Sparkles
                    size={14}
                    className="ml-auto text-teal-200 animate-pulse"
                  />
                )}
              </div>
              <p className="text-xs text-slate-400 mt-3 min-h-8">
                {lastTask || "Waiting for work"}
              </p>
              <div
                aria-live="polite"
                className="mt-3 h-60 overflow-auto rounded-lg bg-slate-950/60 p-4"
              >
                <pre className="text-slate-200 leading-6">
                  {live?.data.text ||
                    complete?.data.output?.text ||
                    complete?.data.output?.summary ||
                    (complete
                      ? JSON.stringify(complete.data.output, null, 2)
                      : "Observable generation and chat will stream here…")}
                </pre>
              </div>
              {retrieval && (
                <details open className="mt-4 max-h-56 overflow-auto">
                  <summary className="text-xs text-teal-200 flex gap-2">
                    <Search size={13} />
                    Retrieved context · {retrieval.data.passages.length}{" "}
                    passages
                  </summary>
                  {retrieval.data.passages.map((p: Row) => (
                    <div
                      key={p.id}
                      className="mt-3 text-xs border-t border-slate-700 pt-2"
                    >
                      <p className="text-amber-200">
                        {p.title} · {p.kind} · {p.status}
                      </p>
                      <p className="text-slate-400 whitespace-pre-wrap mt-1">
                        {p.text}
                      </p>
                      <p className="text-slate-600 mt-1">{p.id}</p>
                    </div>
                  ))}
                </details>
              )}
              <details className="mt-4">
                <summary className="text-xs text-slate-400">
                  Execution history · {messages.length} events
                </summary>
                <div className="max-h-52 overflow-auto mt-2">
                  {messages
                    .filter((e) => e.kind !== "answer_snapshot")
                    .map((e) => (
                      <details
                        key={e.id}
                        className="border-t border-slate-700 py-2"
                      >
                        <summary className="text-xs">
                          {e.kind.replaceAll("_", " ")}
                        </summary>
                        <pre className="text-slate-400">
                          {JSON.stringify(e.data, null, 2)}
                        </pre>
                      </details>
                    ))}
                </div>
              </details>
            </article>
          );
        })}
      </div>
    </section>
  );
}
