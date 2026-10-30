"use client";
import { useState, useEffect, useRef } from "react";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowUpRight,
  FileText,
  Activity,
  ShieldCheck,
  GitCompare,
  Plus,
  Play,
  Pause,
  Square,
  Download,
  ChevronRight,
} from "lucide-react";
import Markdown from "react-markdown";
import { MetricEvidence } from "@/components/metric-evidence";
import { diffLines } from "diff";
import { Button } from "@/components/ui/button";
import { api, post, streamEvents, type Row, type StreamEvent } from "@/lib/api";
const client = new QueryClient();
export default function Page() {
  return (
    <QueryClientProvider client={client}>
      <Workspace />
    </QueryClientProvider>
  );
}
function Workspace() {
  const qc = useQueryClient();
  const [rid, setRid] = useState(""),
    [tab, setTab] = useState("resume"),
    [mode, setMode] = useState("resume"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(""),
    [compare, setCompare] = useState(""),
    [editing, setEditing] = useState(false),
    [edit, setEdit] = useState("");
  const [providerConsent, setProviderConsent] = useState(false),
    [researchConsent, setResearchConsent] = useState(false),
    [events, setEvents] = useState<StreamEvent[]>([]);
  const [iid, setIid] = useState("");
  const cursor = useRef(0);
  const list = useQuery({
    queryKey: ["resumes"],
    queryFn: () => api<Row[]>("/resumes"),
  });
  const detail = useQuery({
    queryKey: ["resume", rid],
    queryFn: () => api(`/resumes/${rid}`),
    enabled: !!rid,
    refetchInterval: 3000,
  });
  const data = detail.data;
  const latest = data?.iterations.at(-1);
  const iterationId = iid || latest?.id || "";
  const run = useQuery({
    queryKey: ["iteration", iterationId],
    queryFn: () => api(`/iterations/${iterationId}`),
    enabled: !!iterationId,
    refetchInterval: 2000,
  });
  const it = run.data?.iteration;
  const versions: Row[] = data?.versions || [];
  const version = versions.find(
    (v) => v.id === (selected || data?.resume.current_version_id),
  );
  const previous = versions.find(
    (v) => v.id === (compare || versions.at(-2)?.id),
  );
  const active =
    it &&
    !["AWAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED"].includes(
      it.state,
    );
  const locked = latest && !["COMPLETED", "CANCELLED"].includes(latest.state);
  useEffect(() => {
    if (!rid && list.data?.length) setRid(list.data.at(-1)!.id);
  }, [list.data, rid]);
  useEffect(() => {
    setIid("");
    setSelected("");
    setCompare("");
    setEditing(false);
  }, [rid]);
  useEffect(() => {
    if (!iterationId) return;
    setEvents([]);
    cursor.current = 0;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const connect = async () => {
      try {
        await streamEvents(
          iterationId,
          cursor.current,
          controller.signal,
          (e) => {
            cursor.current = e.id;
            setEvents((old) => [...old, e]);
            qc.invalidateQueries({ queryKey: ["iteration", iterationId] });
          },
        );
      } catch (e) {
        if (!controller.signal.aborted) setError(String(e));
      }
      if (!controller.signal.aborted) timer = setTimeout(connect, 2000);
    };
    connect();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [iterationId, qc]);
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await qc.invalidateQueries();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function upload(form: FormData) {
    await act(async () => {
      const result = await api("/resumes", { method: "POST", body: form });
      setRid(result.id);
    });
  }
  async function control(action: string) {
    await act(() => post(`/iterations/${iterationId}/${action}`));
  }
  async function start(next = false) {
    await act(async () => {
      const result = await post(
        next ? `/iterations/${iterationId}/next` : `/resumes/${rid}/iterations`,
        {
          provider_consent: providerConsent,
          research_consent: researchConsent,
        },
      );
      setIid(result.id);
      setSelected("");
    });
  }
  async function download(fmt: string) {
    await act(async () => {
      const token = sessionStorage.getItem("apiToken");
      const res = await fetch(`/api/versions/${version?.id}/export/${fmt}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error("Export failed");
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `resume-v${version?.number}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-r border-slate-800 p-6 flex flex-col gap-8 lg:min-h-screen">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-teal-300 p-2 text-slate-950">
            <FileText size={22} />
          </div>
          <div className="font-bold leading-5">
            Resume
            <br />
            <span className="text-teal-300">Evolution</span>
          </div>
        </div>
        <div>
          <div className="eyebrow mb-3">Your workspace</div>
          <button
            onClick={() => {
              setRid("");
              setTab("new");
            }}
            className="flex gap-2 text-sm text-teal-200"
          >
            <Plus size={16} />
            New target role
          </button>
          <div className="mt-4 space-y-2">
            {list.data?.map((r) => (
              <button
                key={r.id}
                onClick={() => {
                  setRid(r.id);
                  setTab("resume");
                }}
                className={`block text-left w-full rounded-lg p-3 text-sm ${rid === r.id ? "bg-teal-950 text-teal-200" : "text-slate-400 hover:bg-slate-800"}`}
              >
                {r.target_role}
                <span className="block text-xs text-slate-500 mt-1 truncate">
                  {r.title}
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="mt-auto text-xs leading-5 text-slate-500">
          <ShieldCheck className="mb-2 text-teal-300" size={18} />
          Your experience. Supported by evidence.
          <details className="mt-4">
            <summary>API access</summary>
            <input
              aria-label="API access token"
              type="password"
              placeholder="Optional backend access token"
              onChange={(e) =>
                sessionStorage.setItem("apiToken", e.target.value)
              }
            />
            <p>Stored only for this browser session.</p>
          </details>
        </div>
      </aside>
      <main className="p-5 md:p-10 max-w-[1600px] w-full mx-auto">
        <header className="flex flex-wrap justify-between gap-4 mb-8">
          <div>
            <div className="eyebrow mb-2">
              Career workspace / {data?.resume.target_role || "Get started"}
            </div>
            <h1 className="text-3xl font-semibold tracking-tight">
              Build a resume you can defend.
            </h1>
            <p className="text-slate-400 text-sm mt-3">
              Turn your experience into a stronger application for your next
              role.
            </p>
          </div>
          <div className="flex h-fit rounded-lg border border-slate-700 p-1">
            <Button
              variant={mode === "resume" ? "default" : "outline"}
              onClick={() => setMode("resume")}
            >
              Resume only
            </Button>
            <Button
              variant={mode === "monitor" ? "default" : "outline"}
              onClick={() => setMode("monitor")}
            >
              <Activity size={15} />
              Agent monitoring
            </Button>
          </div>
        </header>
        {(error || list.error || detail.error) && (
          <div
            role="alert"
            className="mb-5 rounded-lg border border-rose-800 bg-rose-950 p-4 text-rose-100"
          >
            {error || String(list.error || detail.error)}
          </div>
        )}
        {!rid || tab === "new" ? (
          <form action={upload} className="panel max-w-3xl space-y-6">
            <div>
              <div className="eyebrow">01 / Set your direction</div>
              <h2 className="text-xl mt-2 font-semibold">
                One seed resume. Any target role.
              </h2>
              <p className="text-sm text-slate-400 mt-2">
                Add a role name, job description, or both. Your original resume
                is always preserved.
              </p>
            </div>
            <label>
              Target role
              <input
                name="target_role"
                placeholder="e.g. Product Manager, Data Analyst, Staff Engineer"
                maxLength={500}
              />
            </label>
            <label>
              Job description
              <textarea
                name="job_description"
                rows={6}
                placeholder="Paste the responsibilities, requirements and seniority…"
                maxLength={30000}
              />
            </label>
            <label>
              Seed resume
              <input
                name="file"
                type="file"
                accept=".txt,.md,.pdf,.docx"
                required
              />
            </label>
            <p className="text-xs text-slate-500">
              Text PDF, DOCX, Markdown or text • Up to 2 MB • No external
              sharing on upload
            </p>
            <Button disabled={busy}>
              Create workspace <ArrowUpRight size={16} />
            </Button>
          </form>
        ) : !data ? (
          <p className="text-slate-400">Loading workspace…</p>
        ) : (
          <>
            <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
              {[
                [
                  "Workflow",
                  it?.paused
                    ? "Paused"
                    : it?.state?.replaceAll("_", " ") || "Ready to start",
                ],
                ["Iteration", it?.number || "—"],
                ["Resume version", `v${versions.at(-1)?.number || 1}`],
                [
                  "API usage",
                  `${run.data?.tokens || 0} tokens · ${run.data?.estimated_cost == null ? "cost unconfigured" : `~$${run.data.estimated_cost.toFixed(4)}`}`,
                ],
              ].map(([label, value]) => (
                <div className="panel !p-5" key={label}>
                  <div className="eyebrow">{label}</div>
                  <div className="mt-3 font-semibold text-sm text-teal-100">
                    {value}
                  </div>
                </div>
              ))}
            </div>
            <section className="panel mb-6">
              <div className="flex flex-wrap gap-3 justify-between">
                <div>
                  <h2 className="font-semibold">
                    {it?.state === "AWAITING_APPROVAL"
                      ? "Your iteration is ready for review"
                      : "Your next improvement cycle"}
                  </h2>
                  <p className="mt-1 text-sm text-slate-400">
                    Analyze → Interview → Research → Audit → Revise → Your
                    approval
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {!locked && (
                    <Button
                      disabled={busy || !providerConsent}
                      onClick={() => start()}
                    >
                      <Play size={15} />
                      Start iteration
                    </Button>
                  )}
                  {active && (
                    <>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => control(it.paused ? "resume" : "pause")}
                      >
                        {it.paused ? <Play size={15} /> : <Pause size={15} />}{" "}
                        {it.paused ? "Resume" : "Pause"}
                      </Button>
                      <Button
                        variant="destructive"
                        disabled={busy}
                        onClick={() => control("cancel")}
                      >
                        Cancel
                      </Button>
                    </>
                  )}
                  {it?.state === "FAILED" && (
                    <>
                      <Button onClick={() => control("retry")} disabled={busy}>
                        Retry checkpoint
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => control("cancel")}
                      >
                        Cancel
                      </Button>
                    </>
                  )}
                  {it?.state === "AWAITING_APPROVAL" && (
                    <>
                      <Button
                        disabled={busy || !providerConsent}
                        onClick={() => start(true)}
                      >
                        Approve & next iteration
                        <ChevronRight size={15} />
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => control("stop")}
                        disabled={busy}
                      >
                        <Square size={14} />
                        Stop
                      </Button>
                    </>
                  )}
                </div>
              </div>
              <div className="mt-5 flex flex-col gap-2">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={providerConsent}
                    onChange={(e) => setProviderConsent(e.target.checked)}
                  />
                  I authorize sending my resume, target and evidence to OpenAI
                  for this iteration.
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={researchConsent}
                    onChange={(e) => setResearchConsent(e.target.checked)}
                  />
                  Allow external web research using generated topic queries.
                  Queries may reveal context.
                </label>
              </div>
              {it?.error && (
                <p className="mt-4 text-sm text-rose-300">{it.error}</p>
              )}
              {active && (
                <p className="mt-4 text-xs text-slate-400">
                  {run.data?.transcript.filter((t: Row) => !t.question.followup)
                    .length || 0}{" "}
                  / 10 primary questions · Pause takes effect after the current
                  durable step.
                </p>
              )}
            </section>
            <nav
              className="flex gap-2 mb-5 overflow-auto"
              aria-label="Workspace views"
            >
              {[
                ["resume", "Resume", FileText],
                ["compare", "Compare", GitCompare],
                ["evidence", "Evidence", ShieldCheck],
                ["interview", "Interview", Activity],
                ["research", "Research", ArrowUpRight],
              ].map(([key, label, Icon]) => (
                <Button
                  key={String(key)}
                  variant={tab === key ? "default" : "outline"}
                  onClick={() => setTab(String(key))}
                >
                  {typeof Icon !== "string" && <Icon size={15} />}{" "}
                  {String(label)}
                </Button>
              ))}
            </nav>
            {tab === "resume" && (
              <section className="panel">
                <div className="flex flex-wrap justify-between gap-3 mb-5">
                  <div>
                    <div className="eyebrow">
                      Resume version {version?.number}
                    </div>
                    <h2 className="mt-2 font-semibold">
                      {data.resume.target_role}
                    </h2>
                    <p className="text-xs text-amber-300 mt-2">
                      {version?.submission_ready
                        ? "Evidence audit passed. Review before submitting."
                        : "Draft · Unverified claims require your review."}
                    </p>
                  </div>
                  <div className="flex gap-2 flex-wrap">
                    <select
                      aria-label="Resume version"
                      className="!w-auto"
                      value={version?.id || ""}
                      onChange={(e) => setSelected(e.target.value)}
                    >
                      {versions.map((v) => (
                        <option key={v.id} value={v.id}>
                          Version {v.number}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="outline"
                      disabled={!!locked}
                      onClick={() => {
                        setEdit(version?.text || "");
                        setEditing(!editing);
                      }}
                    >
                      Edit
                    </Button>
                    {["md", "pdf", "docx"].map((fmt) => (
                      <Button
                        key={fmt}
                        variant="outline"
                        onClick={() => download(fmt)}
                      >
                        <Download size={14} />
                        {fmt.toUpperCase()}
                      </Button>
                    ))}
                  </div>
                </div>
                {editing ? (
                  <div className="space-y-3">
                    <textarea
                      aria-label="Resume Markdown"
                      rows={22}
                      value={edit}
                      onChange={(e) => setEdit(e.target.value)}
                    />
                    <Button
                      disabled={busy}
                      onClick={() =>
                        act(async () => {
                          await api(`/resumes/${rid}/versions`, {
                            method: "PUT",
                            body: JSON.stringify({
                              text: edit,
                              reason: "Candidate manual correction",
                            }),
                          });
                          setEditing(false);
                          setSelected("");
                        })
                      }
                    >
                      Save as new draft version
                    </Button>
                    <p className="text-xs text-slate-400">
                      Manual edits do not count as verified evidence.
                    </p>
                  </div>
                ) : (
                  <article className="prose bg-slate-50 text-slate-800 rounded-lg p-6 md:p-12 max-w-4xl mx-auto">
                    <Markdown>{version?.text || ""}</Markdown>
                  </article>
                )}
              </section>
            )}
            {tab === "compare" && (
              <section className="panel">
                <h2 className="font-semibold mb-4">Version comparison</h2>
                <div className="flex gap-3 mb-4">
                  <select
                    aria-label="Compare from"
                    value={previous?.id || ""}
                    onChange={(e) => setCompare(e.target.value)}
                  >
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        From v{v.number}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="Compare to"
                    value={version?.id || ""}
                    onChange={(e) => setSelected(e.target.value)}
                  >
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        To v{v.number}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid md:grid-cols-2 gap-4">
                  <pre className="p-4 bg-slate-900 rounded-lg">
                    {previous?.text || "No previous version"}
                  </pre>
                  <pre className="p-4 bg-slate-900 rounded-lg">
                    {previous &&
                      diffLines(previous.text, version?.text || "").map(
                        (p, i) => (
                          <span
                            key={i}
                            className={
                              p.added
                                ? "bg-teal-950 text-teal-200"
                                : p.removed
                                  ? "bg-rose-950 text-rose-200 line-through"
                                  : ""
                            }
                          >
                            {p.value}
                          </span>
                        ),
                      )}
                  </pre>
                </div>
                <h3 className="mt-6 mb-3 font-semibold">Revision history</h3>
                {data.revisions.map((r: Row) => (
                  <details
                    key={r.id}
                    className="border-t border-slate-700 py-3"
                  >
                    <summary>
                      {r.reason} · {r.agent}
                    </summary>
                    <pre>{JSON.stringify(r, null, 2)}</pre>
                  </details>
                ))}
              </section>
            )}
            {tab === "evidence" && (
              <section className="panel space-y-5">
                <h2 className="text-xl font-semibold">
                  Evidence & candidate confirmations
                </h2>
                <p className="text-sm text-slate-400">
                  Research and simulated interview answers never establish
                  personal accomplishments. Stop the iteration before adding
                  evidence.
                </p>
                <form
                  action={(form) =>
                    act(() =>
                      post(`/resumes/${rid}/confirm`, {
                        response: form.get("response"),
                      }),
                    )
                  }
                  className="space-y-3"
                >
                  <label>
                    Explicitly confirm a factual contribution
                    <textarea
                      name="response"
                      required
                      placeholder="Describe exactly what you personally did. Do not guess measurements."
                    />
                  </label>
                  <Button disabled={!!locked || busy}>
                    Save candidate confirmation
                  </Button>
                </form>
                <form
                  action={(form) =>
                    act(() =>
                      post(`/resumes/${rid}/evidence`, {
                        text: form.get("text"),
                        source: form.get("source"),
                        kind: "direct_artifact",
                      }),
                    )
                  }
                  className="space-y-3"
                >
                  <label>
                    Supporting artifact excerpt
                    <textarea name="text" required />
                  </label>
                  <label>
                    Source reference
                    <input
                      name="source"
                      required
                      placeholder="Document, commit, or measurement report reference"
                    />
                  </label>
                  <Button variant="outline" disabled={!!locked || busy}>
                    Record unverified artifact
                  </Button>
                </form>
                {data.confirmations
                  .filter((c: Row) => !c.response)
                  .map((c: Row) => (
                    <form
                      key={c.id}
                      action={(form) =>
                        act(() =>
                          post(`/confirmations/${c.id}`, {
                            response: form.get("response"),
                          }),
                        )
                      }
                      className="rounded-lg border border-amber-900 p-4 space-y-3"
                    >
                      <p className="text-sm text-amber-200 whitespace-pre-wrap">
                        {c.question}
                      </p>
                      <textarea
                        name="response"
                        aria-label="Confirmation response"
                        required
                      />
                      <Button variant="outline" disabled={!!locked || busy}>
                        Confirm or correct
                      </Button>
                    </form>
                  ))}
                <h3 className="font-semibold">Claim register</h3>
                {data.claims.map((c: Row) => (
                  <div key={c.id} className="border-t border-slate-700 py-3">
                    <span className="text-xs text-amber-300">{c.status}</span>
                    <p className="text-sm mt-1">{c.text}</p>
                    <p className="text-xs text-slate-500">{c.warning}</p>
                  </div>
                ))}
                <MetricEvidence
                  rid={rid}
                  metrics={data.metrics || []}
                  disabled={!!locked || busy}
                  act={act}
                />
                <h3 className="font-semibold">Stored evidence</h3>
                {data.evidence.map((e: Row) => (
                  <div key={e.id} className="border-t border-slate-700 py-3">
                    <span className="text-xs text-teal-200">{e.status}</span>
                    <p className="text-sm mt-1 whitespace-pre-wrap">{e.text}</p>
                    <p className="text-xs text-slate-500">{e.source}</p>
                  </div>
                ))}
              </section>
            )}
            {tab === "interview" && (
              <section className="panel">
                <div className="flex gap-3 justify-between mb-5">
                  <h2 className="font-semibold">Interview replay</h2>
                  <select
                    aria-label="Interview iteration"
                    className="!w-auto"
                    value={iterationId}
                    onChange={(e) => setIid(e.target.value)}
                  >
                    {data.iterations.map((i: Row) => (
                      <option key={i.id} value={i.id}>
                        Iteration {i.number}
                      </option>
                    ))}
                  </select>
                </div>
                {!run.data?.transcript.length && (
                  <p className="text-slate-400">
                    Your interview transcript will appear here.
                  </p>
                )}
                {run.data?.transcript.map((t: Row) => (
                  <div
                    key={t.question.id}
                    className="border-t border-slate-700 py-5"
                  >
                    <div className="eyebrow">
                      {t.question.followup ? "Follow-up" : "Question"}{" "}
                      {t.question.number} · {t.question.difficulty}
                    </div>
                    <h3 className="mt-2 font-semibold">{t.question.text}</h3>
                    <p className="mt-3 text-sm text-slate-300 whitespace-pre-wrap">
                      {t.answer?.text || "Awaiting answer…"}
                    </p>
                    <p className="text-xs text-amber-300 mt-2">
                      Simulated answer · {t.answer?.limitations.join(" · ")}
                    </p>
                    <div className="grid md:grid-cols-2 gap-2 mt-4">
                      {Object.entries(t.evaluation?.scores || {}).map(
                        ([name, score]) => (
                          <div
                            className="bg-slate-900 rounded-lg p-3 text-xs"
                            key={name}
                          >
                            <div className="text-teal-200">
                              {name.replaceAll("_", " ")}:{" "}
                              {(score as Row).value}/10
                            </div>
                            <p className="text-slate-400 mt-1">
                              {(score as Row).reason}
                            </p>
                          </div>
                        ),
                      )}
                    </div>
                  </div>
                ))}
                {it?.checkpoint.feedback && (
                  <details className="mt-4">
                    <summary>Post-interview feedback</summary>
                    <pre>{JSON.stringify(it.checkpoint.feedback, null, 2)}</pre>
                  </details>
                )}
              </section>
            )}
            {tab === "research" && (
              <section className="panel space-y-4">
                <h2 className="text-xl font-semibold">
                  Research & preparation
                </h2>
                <p className="text-sm text-slate-400">
                  Public context informs preparation. It does not prove personal
                  ownership.
                </p>
                {!run.data?.sources.length && (
                  <p className="text-slate-500">
                    No sources yet. Research requires explicit consent and
                    topics from interview feedback.
                  </p>
                )}
                {run.data?.sources.map((src: Row) => (
                  <div key={src.id} className="border-t border-slate-700 pt-4">
                    <a
                      className="text-teal-200 underline"
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {src.title}
                    </a>
                    <p className="text-xs text-slate-500 mt-2">
                      Accessed {src.access_date} · Publication date{" "}
                      {src.publication_date || "not established"}
                    </p>
                    {run.data?.findings
                      .filter((f: Row) => f.source_id === src.id)
                      .map((f: Row) => (
                        <dl key={f.id} className="text-sm space-y-2 mt-4">
                          {Object.entries(f.details)
                            .filter(([k]) => k !== "source_url")
                            .map(([k, v]) => (
                              <div key={k}>
                                <dt className="text-slate-500">
                                  {k.replaceAll("_", " ")}
                                </dt>
                                <dd className="text-slate-300">{String(v)}</dd>
                              </div>
                            ))}
                        </dl>
                      ))}
                  </div>
                ))}
                <pre>
                  {JSON.stringify(
                    it?.checkpoint.revision?.proposal.study_recommendations ||
                      [],
                    null,
                    2,
                  )}
                </pre>
              </section>
            )}
            {mode === "monitor" && (
              <section className="mt-6">
                <h2 className="text-xl font-semibold mb-4">
                  Agent activity{" "}
                  <span className="text-xs font-normal text-slate-500">
                    Observable messages & tool results
                  </span>
                </h2>
                <div className="grid xl:grid-cols-3 gap-4">
                  {[
                    ["resume", "Resume Update Agent"],
                    ["interviewee", "Interviewee Agent"],
                    ["interviewer", "Adversarial Interviewer"],
                  ].map(([agent, name]) => (
                    <div className="panel !p-5" key={agent}>
                      <div className="flex items-center gap-2 mb-4">
                        <span className="w-2 h-2 bg-teal-300 rounded-full" />
                        <h3 className="font-semibold text-sm">{name}</h3>
                      </div>
                      {agent === "interviewee" &&
                        events.some((e) => e.kind === "answer_snapshot") && (
                          <div className="mb-4 border border-teal-900 bg-teal-950/30 rounded-lg p-3">
                            <div className="eyebrow">
                              Latest answer · simulated
                            </div>
                            <p className="text-sm whitespace-pre-wrap mt-2">
                              {
                                events
                                  .filter((e) => e.kind === "answer_snapshot")
                                  .at(-1)?.data.text
                              }
                            </p>
                          </div>
                        )}
                      <div className="max-h-[560px] overflow-auto space-y-3">
                        {events
                          .filter((e) => e.agent === agent)
                          .map((e) => (
                            <details
                              key={e.id}
                              className="bg-slate-900 p-3 rounded-lg"
                            >
                              <summary className="text-xs text-teal-100">
                                {e.kind.replaceAll("_", " ")}
                                <span className="block text-slate-400 mt-1">
                                  {e.data.task ||
                                    e.data.reason ||
                                    e.data.message}
                                </span>
                              </summary>
                              <pre className="mt-3 text-slate-400">
                                {JSON.stringify(e.data, null, 2)}
                              </pre>
                            </details>
                          ))}
                        {!events.some((e) => e.agent === agent) && (
                          <p className="text-xs text-slate-500">
                            Waiting for activity
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                <details className="panel mt-4">
                  <summary>
                    Complete persisted timeline · {events.length} events
                  </summary>
                  {events.map((e) => (
                    <div
                      key={e.id}
                      className="text-xs border-t border-slate-700 py-2"
                    >
                      {e.created_at} · {e.agent} · {e.kind}
                    </div>
                  ))}
                </details>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
