"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Activity,
  FileText,
  Database,
  Settings,
  Plus,
  ArrowRight,
  Pause,
  Play,
  Square,
  Download,
} from "lucide-react";
import Markdown from "react-markdown";
import { diffLines } from "diff";
import { Button } from "@/components/ui/button";
import { api, post, streamEvents, type Row, type StreamEvent } from "@/lib/api";
import { UsageBar } from "@/components/usage-bar";
import { LiveWorkflow } from "@/components/live-workflow";
import { KnowledgeManager } from "@/components/knowledge-manager";
import { MetricEvidence } from "@/components/metric-evidence";
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
  const [pid, setPid] = useState(""),
    [rid, setRid] = useState(""),
    [historyId, setHistoryId] = useState(""),
    [tab, setTab] = useState("monitor"),
    [creating, setCreating] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [providerConsent, setProviderConsent] = useState(false),
    [researchConsent, setResearchConsent] = useState(false),
    [embeddingConsent, setEmbeddingConsent] = useState(false),
    [count, setCount] = useState(1),
    [events, setEvents] = useState<StreamEvent[]>([]),
    [versionId, setVersion] = useState(""),
    [compareId, setCompare] = useState(""),
    [editing, setEditing] = useState(false),
    [editText, setEditText] = useState("");
  const cursor = useRef(0);
  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api<Row[]>("/profiles"),
  });
  const resumes = useQuery({
    queryKey: ["resumes"],
    queryFn: () => api<Row[]>("/resumes"),
  });
  const profile = profiles.data?.find((p) => p.id === pid);
  const choices = resumes.data?.filter((r) => r.profile_id === pid) || [];
  const detail = useQuery({
    queryKey: ["resume", rid],
    queryFn: () => api(`/resumes/${rid}`),
    enabled: !!rid,
    refetchInterval: 2000,
  });
  const data = detail.data?.resume.profile_id === pid ? detail.data : undefined;
  const latest = data?.iterations.at(-1),
    iid = historyId || latest?.id || "";
  const run = useQuery({
    queryKey: ["iteration", iid],
    queryFn: () => api(`/iterations/${iid}`),
    enabled: !!iid,
    refetchInterval: 1500,
  });
  const iteration = run.data?.iteration;
  const versions: Row[] = data?.versions || [];
  const version = versions.find(
    (v) => v.id === (versionId || data?.resume.current_version_id),
  );
  const previous = versions.find(
    (v) => v.id === (compareId || versions.at(-2)?.id),
  );
  const active =
    iteration &&
    !["AWAITING_APPROVAL", "COMPLETED", "FAILED", "CANCELLED"].includes(
      iteration.state,
    );
  const locked = latest && !["COMPLETED", "CANCELLED"].includes(latest.state);
  useEffect(() => {
    if (!pid && profiles.data?.length) setPid(profiles.data[0].id);
  }, [profiles.data, pid]);
  useEffect(() => {
    const scoped = resumes.data?.filter((r) => r.profile_id === pid) || [];
    if (!scoped.some((r) => r.id === rid)) setRid(scoped.at(-1)?.id || "");
  }, [pid, resumes.data, rid]);
  useEffect(() => {
    setHistoryId("");
    setVersion("");
    setCompare("");
    setEditing(false);
  }, [rid]);
  useEffect(() => {
    setEvents([]);
    cursor.current = 0;
    if (!iid) return;
    const control = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const connect = async () => {
      try {
        await streamEvents(iid, cursor.current, control.signal, (e) => {
          cursor.current = e.id;
          setEvents((old) => [...old, e].slice(-1000));
        });
      } catch (e) {
        if (!control.signal.aborted) setError(String(e));
      }
      if (!control.signal.aborted) timer = setTimeout(connect, 2000);
    };
    void connect();
    return () => {
      control.abort();
      clearTimeout(timer);
    };
  }, [iid]);
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
  async function start(next = false) {
    await act(async () => {
      await post(
        next ? `/iterations/${iid}/next` : `/resumes/${rid}/iterations`,
        {
          provider_consent: providerConsent,
          research_consent: researchConsent,
          embedding_consent: embeddingConsent,
          iteration_count: count,
        },
      );
      setHistoryId("");
      setTab("monitor");
    });
  }
  async function control(action: string) {
    await act(() => post(`/iterations/${iid}/${action}`));
  }
  async function download(format: string) {
    await act(async () => {
      const token = sessionStorage.getItem("apiToken");
      const r = await fetch(`/api/versions/${version?.id}/export/${format}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!r.ok) throw new Error("Export failed");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `resume-v${version?.number}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-r border-slate-800 p-6 flex flex-col gap-7">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-teal-300 text-slate-950 p-2">
            <FileText size={22} />
          </div>
          <div className="font-bold">
            Resume
            <br />
            <span className="text-teal-300">Evolution</span>
          </div>
        </div>
        <div>
          <div className="eyebrow mb-3">Target profiles</div>
          <Button variant="outline" onClick={() => setCreating(!creating)}>
            <Plus size={15} />
            New profile
          </Button>
          <div className="space-y-2 mt-4">
            {profiles.data?.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  setPid(p.id);
                  setCreating(false);
                  setTab("monitor");
                }}
                className={`rounded-lg text-left p-3 w-full ${pid === p.id ? "bg-teal-950 text-teal-100" : "text-slate-400 hover:bg-slate-800"}`}
              >
                <span className="text-sm font-semibold">{p.name}</span>
                <span className="block text-xs mt-1 text-slate-500">
                  {p.target_role}
                </span>
              </button>
            ))}
          </div>
        </div>
        <nav className="flex flex-col gap-3 text-sm">
          <button
            className="flex gap-2 text-left text-slate-300"
            onClick={() => setTab("monitor")}
          >
            <Activity size={17} />
            Live workflow
          </button>
          <button
            className="flex gap-2 text-left text-slate-300"
            onClick={() => setTab("knowledge")}
          >
            <Database size={17} />
            Knowledge database
          </button>
          <button
            className="flex gap-2 text-left text-slate-300"
            onClick={() => setTab("resume")}
          >
            <FileText size={17} />
            Resume history
          </button>
          <Link href="/settings" className="flex gap-2 text-teal-200">
            <Settings size={17} />
            Settings
          </Link>
        </nav>
        <details className="mt-auto text-xs text-slate-500">
          <summary>API access</summary>
          <input
            aria-label="API access token"
            type="password"
            placeholder="Optional backend access token"
            onChange={(e) => sessionStorage.setItem("apiToken", e.target.value)}
          />
          <p>
            After entering the access token, refresh the page. Stored for this
            browser session only.
          </p>
        </details>
      </aside>
      <main className="p-5 md:p-9 max-w-[1700px] w-full mx-auto">
        <header className="flex flex-wrap justify-between gap-4 mb-6">
          <div>
            <div className="eyebrow mb-2">
              Career workspace / {profile?.name || "Get started"}
            </div>
            <h1 className="text-3xl font-semibold">
              {profile?.target_role || "Build a resume you can defend."}
            </h1>
            <p className="text-slate-400 text-sm mt-2">
              Separate knowledge. Evidence-grounded answers. Always-visible
              agent activity.
            </p>
          </div>
          <Link
            href="/settings"
            className="flex items-center gap-2 text-sm text-teal-200 h-fit"
          >
            <Settings size={16} />
            AI connection & settings
          </Link>
        </header>
        <UsageBar />
        {(error || profiles.error || detail.error) && (
          <p
            role="alert"
            className="mb-5 p-4 rounded-lg bg-rose-950 text-rose-200"
          >
            {error || String(profiles.error || detail.error)}
          </p>
        )}
        {(creating || (!profiles.isLoading && profiles.data?.length === 0)) && (
          <form
            className="panel mb-6 space-y-4"
            action={(form) =>
              act(async () => {
                const p = await post("/profiles", {
                  name: form.get("name"),
                  target_role: form.get("target_role"),
                  job_description: form.get("job_description"),
                });
                setPid(p.id);
                setCreating(false);
              })
            }
          >
            <h2 className="text-xl font-semibold">Create a target profile</h2>
            <div className="grid md:grid-cols-2 gap-4">
              <label>
                Profile name
                <input
                  name="name"
                  required
                  maxLength={120}
                  placeholder="My product leadership application"
                />
              </label>
              <label>
                Target role
                <input
                  name="target_role"
                  required
                  maxLength={500}
                  placeholder="Any role and seniority"
                />
              </label>
            </div>
            <label>
              Job description
              <textarea name="job_description" rows={4} maxLength={30000} />
            </label>
            <p className="text-xs text-slate-500">
              This profile gets its own knowledge, resumes and interview
              history. No cross-profile retrieval.
            </p>
            <Button disabled={busy}>Create profile</Button>
          </form>
        )}
        {profile && !creating && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
              <div className="flex gap-2">
                {[
                  ["monitor", "Agent monitoring"],
                  ["knowledge", "Knowledge database"],
                  ["resume", "Resume history"],
                ].map(([k, t]) => (
                  <Button
                    key={k}
                    variant={tab === k ? "default" : "outline"}
                    onClick={() => setTab(k)}
                  >
                    {t}
                  </Button>
                ))}
              </div>
              {choices.length > 0 && (
                <select
                  aria-label="Seed resume"
                  className="!w-auto max-w-xs"
                  value={rid}
                  onChange={(e) => setRid(e.target.value)}
                >
                  {choices.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {rid && data && (
              <div className="mb-5">
                <LiveWorkflow run={run.data} events={events} />
              </div>
            )}
            {tab === "knowledge" ? (
              <KnowledgeManager key={pid} profile={profile} />
            ) : (
              <>
                {(!rid || tab === "resume") && (
                  <details className="panel mb-5" open={!rid}>
                    <summary className="font-semibold">
                      {rid
                        ? "Upload another seed resume"
                        : "Upload a seed resume for this profile"}
                    </summary>
                    <form
                      className="flex gap-3 mt-4"
                      action={(form) =>
                        act(async () => {
                          form.set("profile_id", pid);
                          const r = await api("/resumes", {
                            method: "POST",
                            body: form,
                          });
                          setRid(r.id);
                        })
                      }
                    >
                      <label className="flex-1">
                        Seed resume file
                        <input
                          name="file"
                          type="file"
                          accept=".md,.txt,.pdf,.docx"
                          required
                        />
                      </label>
                      <Button disabled={busy}>Upload resume</Button>
                    </form>
                    <p className="text-xs text-slate-500 mt-2">
                      Readable text/PDF/DOCX · 2 MB maximum · Uploading does not
                      share externally.
                    </p>
                  </details>
                )}
                {rid && data && (
                  <>
                    <section className="panel mb-5">
                      <div className="flex flex-wrap justify-between gap-3">
                        <div>
                          <div className="eyebrow">Run control</div>
                          <h2 className="font-semibold mt-2">
                            {iteration?.state === "AWAITING_APPROVAL"
                              ? "Your strategy choice is ready"
                              : "Run your improvement workflow"}
                          </h2>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                          {!locked && (
                            <Button
                              disabled={busy || !providerConsent}
                              onClick={() => start()}
                            >
                              <Play size={14} />
                              Start iteration
                            </Button>
                          )}
                          {active && (
                            <>
                              <Button
                                variant="outline"
                                disabled={busy}
                                onClick={() =>
                                  control(iteration.paused ? "resume" : "pause")
                                }
                              >
                                <Pause size={14} />
                                {iteration.paused ? "Resume" : "Pause"}
                              </Button>
                              <Button
                                variant="destructive"
                                onClick={() => control("cancel")}
                              >
                                Cancel
                              </Button>
                            </>
                          )}
                          {iteration?.state === "FAILED" && (
                            <>
                              <Button onClick={() => control("retry")}>
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
                          {iteration?.state === "AWAITING_APPROVAL" && (
                            <>
                              <Button
                                disabled={
                                  busy ||
                                  !providerConsent ||
                                  !iteration.checkpoint.selected_strategy
                                }
                                onClick={() => start(true)}
                              >
                                Approve & next run
                                <ArrowRight size={14} />
                              </Button>
                              <Button
                                variant="outline"
                                onClick={() => control("stop")}
                              >
                                <Square size={14} />
                                Stop
                              </Button>
                            </>
                          )}
                        </div>
                      </div>
                      <div className="grid md:grid-cols-[180px_1fr] gap-5 mt-4">
                        <label>
                          Iterations in this run
                          <input
                            type="number"
                            min={1}
                            max={100}
                            value={count}
                            onChange={(e) => setCount(Number(e.target.value))}
                          />
                        </label>
                        <div className="space-y-2">
                          <label className="flex gap-2">
                            <input
                              type="checkbox"
                              checked={providerConsent}
                              onChange={(e) =>
                                setProviderConsent(e.target.checked)
                              }
                            />
                            I authorize sending this profile’s resume, evidence
                            and retrieved knowledge to the selected provider for
                            the planned iterations.
                          </label>
                          <label className="flex gap-2">
                            <input
                              type="checkbox"
                              checked={researchConsent}
                              onChange={(e) =>
                                setResearchConsent(e.target.checked)
                              }
                            />
                            Allow public web research with generated topic
                            queries.
                          </label>
                          <label className="flex gap-2">
                            <input
                              type="checkbox"
                              checked={embeddingConsent}
                              onChange={(e) =>
                                setEmbeddingConsent(e.target.checked)
                              }
                            />
                            Allow OpenAI query embeddings when semantic RAG is
                            enabled in Settings.
                          </label>
                        </div>
                      </div>
                      <p className="text-xs text-slate-500 mt-3">
                        A planned run may execute multiple iterations. It stops
                        for your strategy selection at the end. Audit and
                        evidence rules remain required.
                      </p>
                      {iteration?.error && (
                        <p className="text-rose-300 text-sm mt-3">
                          {iteration.error}
                        </p>
                      )}
                    </section>
                    {iteration?.state === "AWAITING_APPROVAL" &&
                      iteration.checkpoint.strategies &&
                      !iteration.checkpoint.selected_strategy && (
                        <section className="panel mb-5 border-teal-700">
                          <div className="eyebrow">
                            Resume builder’s recommendation
                          </div>
                          <h2 className="font-semibold text-xl mt-2">
                            How should we update your resume?
                          </h2>
                          <p className="text-sm text-slate-400 mt-2">
                            Choose one short strategy. The builder will apply it
                            only where evidence supports the wording.
                          </p>
                          <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-3 mt-5">
                            {iteration.checkpoint.strategies.map((s: Row) => (
                              <button
                                key={s.id}
                                disabled={busy}
                                onClick={() =>
                                  act(() =>
                                    post(
                                      `/iterations/${iid}/strategies/select`,
                                      {
                                        strategy_id: s.id,
                                      },
                                    ),
                                  )
                                }
                                className="text-left rounded-xl border border-teal-900 bg-teal-950/40 p-5 hover:border-teal-300 transition"
                              >
                                <div className="text-teal-100 font-semibold">
                                  {s.title}
                                </div>
                                <p className="text-sm text-slate-400 mt-2">
                                  {s.summary}
                                </p>
                                <span className="block text-xs text-teal-300 mt-4">
                                  Choose strategy →
                                </span>
                              </button>
                            ))}
                          </div>
                        </section>
                      )}
                    {tab === "monitor" && (
                      <>
                        <section className="panel mt-5">
                          <div className="flex justify-between gap-3 mb-4">
                            <h2 className="font-semibold">
                              Interview & iteration replay
                            </h2>
                            <select
                              className="!w-auto"
                              aria-label="Iteration replay"
                              value={historyId || latest?.id || ""}
                              onChange={(e) => setHistoryId(e.target.value)}
                            >
                              {data.iterations.map((it: Row) => (
                                <option value={it.id} key={it.id}>
                                  Iteration {it.number} · {it.state}
                                </option>
                              ))}
                            </select>
                          </div>
                          {run.data?.transcript.map((t: Row) => (
                            <details
                              key={t.question.id}
                              className="border-t border-slate-700 py-3"
                            >
                              <summary className="text-sm">
                                {t.question.followup ? "Follow-up" : "Question"}{" "}
                                {t.question.number}: {t.question.text}
                              </summary>
                              <p className="text-sm text-slate-300 whitespace-pre-wrap mt-3">
                                {t.answer?.text || "Awaiting answer"}
                              </p>
                              <p className="text-xs text-amber-300 mt-2">
                                Simulated answer ·{" "}
                                {t.answer?.limitations.join(" · ")}
                              </p>
                              <div className="grid md:grid-cols-2 gap-2 mt-3">
                                {Object.entries(t.evaluation?.scores || {}).map(
                                  ([k, v]) => (
                                    <p
                                      key={k}
                                      className="bg-slate-900 p-3 rounded text-xs"
                                    >
                                      {k.replaceAll("_", " ")} ·{" "}
                                      {(v as Row).value}/10
                                      <br />
                                      <span className="text-slate-400">
                                        {(v as Row).reason}
                                      </span>
                                    </p>
                                  ),
                                )}
                              </div>
                            </details>
                          ))}
                          <details className="mt-4">
                            <summary className="text-sm text-teal-200">
                              Research & weakness feedback
                            </summary>
                            <pre className="text-slate-400 mt-3">
                              {JSON.stringify(
                                iteration?.checkpoint.feedback || {},
                                null,
                                2,
                              )}
                            </pre>
                            {run.data?.sources.map((s: Row) => (
                              <p
                                key={s.id}
                                className="text-sm text-teal-200 mt-2"
                              >
                                <a
                                  href={s.url}
                                  rel="noopener noreferrer"
                                  target="_blank"
                                >
                                  {s.title}
                                </a>
                              </p>
                            ))}
                          </details>
                        </section>
                      </>
                    )}
                    {tab === "resume" && (
                      <section className="panel">
                        <div className="flex flex-wrap justify-between gap-3 mb-5">
                          <div>
                            <h2 className="text-xl font-semibold">
                              Resume update history
                            </h2>
                            <p className="text-xs text-amber-200 mt-2">
                              {version?.submission_ready
                                ? "Evidence audit passed; review before submission."
                                : "Draft: unverified claims still require review."}
                            </p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <select
                              aria-label="Resume version"
                              className="!w-auto"
                              value={version?.id || ""}
                              onChange={(e) => setVersion(e.target.value)}
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
                                setEditing(!editing);
                                setEditText(version?.text || "");
                              }}
                            >
                              Edit manually
                            </Button>
                            {["md", "pdf", "docx"].map((fmt) => (
                              <Button
                                variant="outline"
                                key={fmt}
                                onClick={() => download(fmt)}
                              >
                                <Download size={13} />
                                {fmt.toUpperCase()}
                              </Button>
                            ))}
                          </div>
                        </div>
                        {editing ? (
                          <div className="space-y-3">
                            <textarea
                              aria-label="Resume Markdown"
                              rows={20}
                              value={editText}
                              onChange={(e) => setEditText(e.target.value)}
                            />
                            <Button
                              disabled={busy}
                              onClick={() =>
                                act(async () => {
                                  await api(`/resumes/${rid}/versions`, {
                                    method: "PUT",
                                    body: JSON.stringify({
                                      text: editText,
                                      reason: "Manual correction",
                                    }),
                                  });
                                  setVersion("");
                                  setEditing(false);
                                })
                              }
                            >
                              Save new draft version
                            </Button>
                          </div>
                        ) : (
                          <article className="prose bg-slate-50 rounded-lg p-6 md:p-10 text-slate-800">
                            <Markdown>{version?.text || ""}</Markdown>
                          </article>
                        )}
                        <details className="mt-5">
                          <summary className="font-semibold">
                            Compare versions
                          </summary>
                          <select
                            className="mt-3"
                            value={previous?.id || ""}
                            onChange={(e) => setCompare(e.target.value)}
                            aria-label="Compare from"
                          >
                            {versions.map((v) => (
                              <option value={v.id} key={v.id}>
                                Compare from v{v.number}
                              </option>
                            ))}
                          </select>
                          <div className="grid md:grid-cols-2 gap-3 mt-3">
                            <pre className="bg-slate-900 p-4 rounded-lg">
                              {previous?.text || "No previous version"}
                            </pre>
                            <pre className="bg-slate-900 p-4 rounded-lg">
                              {previous &&
                                diffLines(
                                  previous.text,
                                  version?.text || "",
                                ).map((p, i) => (
                                  <span
                                    key={i}
                                    className={
                                      p.added
                                        ? "text-teal-200 bg-teal-950"
                                        : p.removed
                                          ? "text-rose-200 bg-rose-950 line-through"
                                          : ""
                                    }
                                  >
                                    {p.value}
                                  </span>
                                ))}
                            </pre>
                          </div>
                        </details>
                        <h3 className="font-semibold mt-6">Change log</h3>
                        {data.revisions.map((r: Row) => (
                          <details
                            key={r.id}
                            className="py-3 border-t border-slate-700"
                          >
                            <summary className="text-sm">
                              {r.reason} · {r.agent} ·{" "}
                              {new Date(r.created_at).toLocaleString()}
                            </summary>
                            <p className="text-xs text-rose-200 mt-2">
                              Before: {r.previous_text}
                            </p>
                            <p className="text-xs text-teal-200 mt-2">
                              After: {r.new_text}
                            </p>
                            <pre className="text-slate-500 mt-2">
                              {JSON.stringify(r.audit, null, 2)}
                            </pre>
                          </details>
                        ))}
                        <details className="mt-5">
                          <summary className="font-semibold">
                            Evidence warnings & confirmations
                          </summary>
                          {data.claims.map((c: Row) => (
                            <p
                              key={c.id}
                              className="text-sm border-t border-slate-700 py-2"
                            >
                              <span className="text-xs text-amber-200">
                                {c.status}
                              </span>{" "}
                              · {c.text}
                            </p>
                          ))}
                          {data.confirmations
                            .filter((c: Row) => !c.response)
                            .map((c: Row) => (
                              <form
                                key={c.id}
                                className="space-y-2 mt-4"
                                action={(form) =>
                                  act(() =>
                                    post(`/confirmations/${c.id}`, {
                                      response: form.get("response"),
                                    }),
                                  )
                                }
                              >
                                <p className="text-sm text-slate-300">
                                  {c.question}
                                </p>
                                <textarea
                                  name="response"
                                  required
                                  aria-label="Confirmation response"
                                />
                                <Button disabled={!!locked || busy}>
                                  Confirm or correct
                                </Button>
                              </form>
                            ))}
                        </details>
                        <MetricEvidence
                          rid={rid}
                          metrics={data.metrics || []}
                          disabled={!!locked || busy}
                          act={act}
                        />
                      </section>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
