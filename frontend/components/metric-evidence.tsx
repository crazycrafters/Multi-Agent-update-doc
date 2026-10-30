"use client";
import { Button } from "@/components/ui/button";
import { post, type Row } from "@/lib/api";
const names = [
  "Evaluation-job failure rate",
  "p50 latency",
  "p95 latency",
  "p99 latency",
  "Job throughput",
  "Successful cases per minute",
  "Validation correctness",
  "Retrieval recall@k",
  "Retrieval precision@k",
  "Hallucination rate",
  "Answer correctness",
  "Cost per successful evaluation",
];
const fields = [
  "project_name",
  "metric_definition",
  "unit",
  "observation_window",
  "workload_description",
  "hardware_configuration",
  "model_configuration",
  "measurement_method",
  "source_reference",
  "limitations",
];
const numbers = [
  "numerator",
  "denominator",
  "baseline_value",
  "final_value",
  "sample_size",
  "concurrency",
];
export function MetricEvidence({
  rid,
  metrics,
  disabled,
  act,
}: {
  rid: string;
  metrics: Row[];
  disabled: boolean;
  act: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  return (
    <details className="border-t border-slate-700 pt-5">
      <summary className="font-semibold">
        Measurement evidence · {metrics.length} records
      </summary>
      <p className="mt-3 text-sm text-slate-400">
        Record the measurement method and source before reviewing an
        achievement. Candidate recollection alone does not verify a metric.
      </p>
      <form
        className="grid md:grid-cols-2 gap-3 mt-4"
        action={(form) =>
          act(() => {
            const body: Row = {
              metric_name: form.get("metric_name"),
              relationship: form.get("relationship"),
            };
            for (const f of fields) body[f] = form.get(f);
            for (const f of numbers) {
              const v = form.get(f);
              body[f] = v ? Number(v) : null;
            }
            return post(`/resumes/${rid}/metrics`, body);
          })
        }
      >
        <label>
          Metric
          <select name="metric_name">
            {names.map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        <label>
          Relationship
          <select name="relationship">
            {[
              "correlation",
              "causal_evidence",
              "absolute_change",
              "relative_percentage_change",
              "percentage_point_change",
            ].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
        {fields.map((f) => (
          <label key={f}>
            {f.replaceAll("_", " ")}
            <input
              name={f}
              required={
                ![
                  "limitations",
                  "hardware_configuration",
                  "model_configuration",
                ].includes(f)
              }
            />
          </label>
        ))}
        {numbers.map((f) => (
          <label key={f}>
            {f.replaceAll("_", " ")}
            <input
              name={f}
              type="number"
              step="any"
              required={["final_value", "sample_size"].includes(f)}
            />
          </label>
        ))}
        <Button disabled={disabled}>Record unverified measurement</Button>
      </form>
      {metrics.map((m) => (
        <div key={m.id} className="mt-4 border border-slate-700 rounded-lg p-4">
          <p className="text-sm">
            {m.metric_name} · {m.evidence_status}
          </p>
          <p className="text-xs text-slate-400 mt-1">
            {m.baseline_value ?? "No baseline"} → {m.final_value} {m.unit} ·{" "}
            {m.source_reference}
          </p>
          {m.evidence_status !== "VERIFIED" && (
            <form
              className="space-y-3 mt-4"
              action={(form) =>
                act(() =>
                  post(`/metrics/${m.id}/review`, {
                    reviewed_direct_measurement: form.get("reviewed") === "on",
                    review_note: form.get("review_note"),
                    supported_statement: form.get("supported_statement"),
                  }),
                )
              }
            >
              <label>
                Exact wording supported by this artifact
                <textarea name="supported_statement" required />
              </label>
              <label>
                Review notes
                <textarea name="review_note" required minLength={10} />
              </label>
              <label className="flex gap-2">
                <input name="reviewed" type="checkbox" required />I inspected
                the direct measurement artifact and verified the definition,
                baseline, sample, method and limitations.
              </label>
              <Button variant="outline" disabled={disabled}>
                Save human artifact review
              </Button>
            </form>
          )}
        </div>
      ))}
    </details>
  );
}
