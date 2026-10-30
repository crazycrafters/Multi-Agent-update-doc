"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post, type Row } from "@/lib/api";
import { Button } from "./ui/button";
const blank = {
  title: "",
  project: "",
  kind: "personal",
  status: "UNVERIFIED",
  source: "",
  content: "",
};
export function KnowledgeManager({ profile }: { profile: Row }) {
  const qc = useQueryClient();
  const pid = profile.id;
  const [draft, setDraft] = useState<Row>(blank),
    [editId, setEditId] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [embeddingConsent, setConsent] = useState(false),
    [results, setResults] = useState<Row[]>([]),
    [query, setQuery] = useState("");
  const { data: docs = [] } = useQuery({
    queryKey: ["knowledge", pid],
    queryFn: () => api<Row[]>(`/profiles/${pid}/knowledge`),
  });
  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["knowledge", pid] });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    await act(async () => {
      await api(`/profiles/${pid}/knowledge${editId ? "/" + editId : ""}`, {
        method: editId ? "PUT" : "POST",
        body: JSON.stringify(draft),
      });
      setDraft(blank);
      setEditId("");
    });
  }
  async function download(format: string) {
    await act(async () => {
      const token = sessionStorage.getItem("apiToken");
      const r = await fetch(
        `/api/profiles/${pid}/knowledge/export?format=${format}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      if (!r.ok) throw new Error("Export failed");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `knowledge.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }
  return (
    <div className="space-y-5">
      <section className="panel">
        <div className="flex justify-between gap-3 flex-wrap">
          <div>
            <div className="eyebrow">Profile-isolated database</div>
            <h2 className="text-xl font-semibold mt-2">
              {profile.name} · Knowledge Manager
            </h2>
            <p className="text-sm text-slate-400 mt-2">
              Personal project dossiers, references and open questions. Changes
              preserve prior versions. Simulated answers never become evidence.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => download("md")}>
              Export Markdown
            </Button>
            <Button variant="outline" onClick={() => download("json")}>
              Export JSON
            </Button>
          </div>
        </div>
      </section>
      <details className="panel">
        <summary className="text-sm font-semibold">Edit profile target</summary>
        <form
          className="space-y-3 mt-4"
          action={(form) =>
            act(async () => {
              await api(`/profiles/${pid}`, {
                method: "PUT",
                body: JSON.stringify({
                  name: form.get("name"),
                  target_role: form.get("target_role"),
                  job_description: form.get("job_description"),
                }),
              });
              await qc.invalidateQueries({ queryKey: ["profiles"] });
            })
          }
        >
          <label>
            Profile name
            <input name="name" required defaultValue={profile.name} />
          </label>
          <label>
            Target role
            <input
              name="target_role"
              required
              defaultValue={profile.target_role}
            />
          </label>
          <label>
            Job description
            <textarea
              name="job_description"
              rows={4}
              defaultValue={profile.job_description}
            />
          </label>
          <Button disabled={busy}>Save profile target</Button>
          <p className="text-xs text-slate-500">
            New runs use the changed target. Existing iterations preserve their
            target snapshot.
          </p>
        </form>
      </details>
      {error && (
        <p role="alert" className="rounded-lg bg-rose-950 text-rose-200 p-4">
          {error}
        </p>
      )}
      <section className="panel">
        <h3 className="font-semibold">
          {editId
            ? "Revise record (keeps previous version)"
            : "Add project knowledge"}
        </h3>
        <form
          className="grid md:grid-cols-2 gap-4 mt-4"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          {[
            ["title", "Title"],
            ["project", "Project"],
            ["source", "Source / artifact reference"],
          ].map(([k, t]) => (
            <label key={k}>
              {t}
              <input
                required={k !== "project"}
                value={draft[k]}
                onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              />
            </label>
          ))}
          <label>
            Knowledge type
            <select
              value={draft.kind}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  kind: e.target.value,
                  status:
                    e.target.value === "reference"
                      ? "PUBLIC_CONTEXT"
                      : "UNVERIFIED",
                })
              }
            >
              <option value="personal">Personal project evidence</option>
              <option value="reference">Public technical reference</option>
              <option value="open_question">Open question / gap</option>
            </select>
          </label>
          <label>
            Evidence status
            <select
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value })}
            >
              {(draft.kind === "reference"
                ? ["PUBLIC_CONTEXT"]
                : draft.kind === "open_question"
                  ? ["UNVERIFIED"]
                  : [
                      "UNVERIFIED",
                      "CANDIDATE_CONFIRMED",
                      "PROPOSED",
                      "CONTRADICTED",
                    ]
              ).map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <p className="text-xs text-amber-200 self-end">
            Choosing CANDIDATE_CONFIRMED explicitly confirms only the facts you
            supply. It does not verify numerical achievements.
          </p>
          <label className="md:col-span-2">
            Project dossier / knowledge
            <textarea
              rows={9}
              required
              value={draft.content}
              onChange={(e) => setDraft({ ...draft, content: e.target.value })}
              placeholder="Your responsibility, request/data flow, implementation, decisions, alternatives, failures, tests, observed outcomes and limitations…"
            />
          </label>
          <div className="flex gap-2">
            <Button disabled={busy}>Save knowledge</Button>
            {editId && (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setEditId("");
                  setDraft(blank);
                }}
              >
                Cancel edit
              </Button>
            )}
          </div>
        </form>
        <details className="mt-5">
          <summary className="text-sm text-teal-200">
            Or upload a source document
          </summary>
          <form
            className="flex gap-3 mt-3"
            action={(form) =>
              act(async () => {
                await api(`/profiles/${pid}/knowledge/upload`, {
                  method: "POST",
                  body: form,
                });
              })
            }
          >
            <input
              type="file"
              name="file"
              accept=".md,.txt,.pdf,.docx"
              required
            />
            <input type="hidden" name="kind" value="personal" />
            <Button disabled={busy}>Upload</Button>
          </form>
          <p className="text-xs text-slate-500 mt-2">
            Uploads start unverified. Readable PDF/DOCX/Markdown/text, up to 2
            MB.
          </p>
        </details>
      </section>
      <section className="panel">
        <h3 className="font-semibold">Test retrieval</h3>
        <form
          className="flex gap-3 mt-4"
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              const r = await post(`/profiles/${pid}/knowledge/search`, {
                query,
                semantic: embeddingConsent,
                embedding_consent: embeddingConsent,
              });
              setResults(r.results);
            });
          }}
        >
          <input
            aria-label="Knowledge search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="How did I handle retries in the evaluation pipeline?"
            required
          />
          <Button disabled={busy}>Search</Button>
        </form>
        <label className="flex gap-2 mt-4">
          <input
            type="checkbox"
            checked={embeddingConsent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          I authorize sending search queries and documents I index to OpenAI
          embeddings (API usage applies).
        </label>
        <p className="text-xs text-slate-500 mt-2">
          Without this consent, retrieval uses PostgreSQL full-text search.
          Codex login alone does not provide an embeddings API.
        </p>
        {results.map((r) => (
          <article key={r.id} className="mt-4 rounded-lg bg-slate-900 p-4">
            <div className="text-xs text-teal-200">
              {r.title} · {r.kind} · {r.status}
            </div>
            <p className="text-sm whitespace-pre-wrap mt-2">{r.text}</p>
            <p className="text-xs text-slate-500 mt-2">
              Chunk {r.id} · {r.source}
            </p>
          </article>
        ))}
      </section>
      <section className="panel">
        <h3 className="font-semibold mb-4">Database records · {docs.length}</h3>
        {!docs.length && (
          <p className="text-slate-400 text-sm">
            Add your first project dossier to enrich the interviewee’s answers.
          </p>
        )}
        {docs.map((doc) => (
          <details
            key={doc.id}
            className={`border-t border-slate-700 py-4 ${doc.active ? "" : "opacity-50"}`}
          >
            <summary>
              <span className="font-medium">{doc.title}</span>
              <span className="text-xs text-slate-400 ml-3">
                v{doc.version} · {doc.kind} · {doc.status} ·{" "}
                {doc.active ? "Active" : "Archived"} · {doc.embedded_chunks}/
                {doc.chunks} embedded
              </span>
            </summary>
            <p className="text-xs text-slate-500 mt-3">
              {doc.id} · {doc.source} · {doc.project}
            </p>
            <pre className="my-4 text-slate-300">{doc.content}</pre>
            <div className="flex gap-2 flex-wrap">
              <Button
                variant="outline"
                onClick={() => {
                  setEditId(doc.active ? doc.id : "");
                  setDraft(
                    Object.fromEntries(
                      Object.keys(blank).map((k) => [k, doc[k]]),
                    ),
                  );
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
              >
                {doc.active ? "Edit as new version" : "Copy as new record"}
              </Button>
              {doc.active && (
                <>
                  <Button
                    variant="outline"
                    disabled={busy || !embeddingConsent}
                    onClick={() =>
                      act(() =>
                        post(`/profiles/${pid}/knowledge/${doc.id}/embed`, {
                          consent: true,
                        }),
                      )
                    }
                  >
                    Index embeddings
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={busy}
                    onClick={() =>
                      act(() =>
                        post(`/profiles/${pid}/knowledge/${doc.id}/archive`),
                      )
                    }
                  >
                    Archive
                  </Button>
                </>
              )}
            </div>
          </details>
        ))}
      </section>
    </div>
  );
}
