"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post } from "@/lib/api";
import { Button } from "@/components/ui/button";
export function ProviderConnection() {
  const qc = useQueryClient();
  const [key, setKey] = useState(""),
    [tab, setTab] = useState<"openai" | "codex">("openai"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const status = useQuery({
    queryKey: ["provider"],
    queryFn: () => api("/provider"),
    refetchInterval: 3000,
  });
  async function update(path: string, body: unknown = {}) {
    setBusy(true);
    setError("");
    try {
      const connection = await post(path, body);
      setKey("");
      await qc.cancelQueries({ queryKey: ["provider"] });
      qc.setQueryData(["provider"], connection);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Connection could not be updated.",
      );
    } finally {
      setBusy(false);
    }
  }
  const codex = status.data?.codex;
  const pending = codex?.pending_login;
  return (
    <section className="panel mb-6">
      <div className="eyebrow">AI connection</div>
      <h2 className="font-semibold mt-2">Choose your model provider</h2>
      <div
        role="group"
        aria-label="Model provider options"
        className="flex flex-wrap gap-2 mt-4"
      >
        <Button
          variant={tab === "openai" ? "default" : "outline"}
          onClick={() => setTab("openai")}
        >
          OpenAI API key
        </Button>
        <Button
          variant={tab === "codex" ? "default" : "outline"}
          onClick={() => setTab("codex")}
        >
          Codex / ChatGPT login
        </Button>
      </div>
      {tab === "openai" ? (
        <>
          <p className="text-sm text-slate-400 mt-3">
            No environment file needed. Your API key stays in backend memory
            until disconnect or restart. OpenAI API billing applies.
          </p>
          <form
            className="flex flex-wrap items-end gap-3 mt-4"
            onSubmit={(e) => {
              e.preventDefault();
              void update("/provider/connection", { api_key: key });
            }}
          >
            <label className="flex-1 min-w-48">
              OpenAI API key
              <input
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="sk-…"
                required
                maxLength={1024}
              />
            </label>
            <Button disabled={busy || !key.trim()}>Connect key</Button>
            {status.data?.provider === "codex" && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  update("/provider/select", { provider: "openai" })
                }
              >
                Use OpenAI API
              </Button>
            )}
            {status.data?.source === "session" && (
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => update("/provider/disconnect")}
              >
                Disconnect key
              </Button>
            )}
          </form>
          <p className="text-xs text-slate-500 mt-2">
            The key is sent to your backend, never saved in browser storage or
            the database. Use HTTPS remotely. Connecting makes no paid API call.
          </p>
        </>
      ) : (
        <>
          <p className="text-sm text-slate-400 mt-3">
            Use the official Codex ChatGPT sign-in, with separate agent threads.
            Available models and usage limits depend on your account. This does
            not connect to ordinary ChatGPT browser conversations.
          </p>
          <p className="text-xs text-slate-500 mt-2">
            Codex credentials and thread transcripts are saved in a dedicated
            backend volume. Sign in only on a backend you trust. Logout removes
            the saved login; transcripts remain.
          </p>
          <div className="flex flex-wrap gap-2 mt-4">
            <Button
              disabled={busy || !!pending}
              onClick={() => update("/provider/codex/login")}
            >
              {codex?.signed_in
                ? "Check ChatGPT connection"
                : "Sign in with ChatGPT"}
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => update("/provider/select", { provider: "codex" })}
            >
              Use Codex
            </Button>
            {(codex?.signed_in || pending) && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => update("/provider/codex/logout")}
              >
                {pending ? "Cancel sign-in" : "Log out of Codex"}
              </Button>
            )}
          </div>
          {pending && (
            <div className="rounded-lg bg-slate-900 border border-teal-900 p-4 mt-4">
              <p className="text-sm">Complete sign-in on OpenAI’s website:</p>
              <a
                href={pending.verificationUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-teal-200 underline text-sm"
              >
                Open OpenAI device sign-in
              </a>
              <p className="font-mono tracking-widest text-xl mt-3">
                {pending.userCode}
              </p>
              <p className="text-xs text-slate-500 mt-2">
                Waiting for authorization. Do not share this one-time code.
              </p>
            </div>
          )}
          {codex?.available === false && (
            <p className="text-sm text-amber-300 mt-3">
              Codex CLI is missing on the backend. Use the updated Docker image
              or install the documented pinned version.
            </p>
          )}
          {codex?.error && (
            <p className="text-sm text-amber-300 mt-3">{codex.error}</p>
          )}
        </>
      )}
      <p role="status" className="text-xs text-teal-200 mt-3">
        Active provider:{" "}
        {status.data?.provider === "codex" ? "Codex" : "OpenAI API"} ·{" "}
        {status.data?.configured
          ? status.data.provider === "codex"
            ? "ChatGPT signed in; model access checked when agents run."
            : `Key configured (${status.data.source}). Not yet validated with OpenAI.`
          : "Not connected."}
      </p>
      <p className="text-xs text-slate-500 mt-2">
        This is a single-user workspace. Cancel active work before switching
        providers. Recovered iterations require their original provider.
      </p>
      {(error || status.error) && (
        <p role="alert" className="text-sm text-rose-300 mt-3">
          {error || "Unable to read connection status."}
        </p>
      )}
    </section>
  );
}
