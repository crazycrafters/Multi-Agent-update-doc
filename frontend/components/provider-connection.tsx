"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post } from "@/lib/api";
import { Button } from "@/components/ui/button";
export function ProviderConnection() {
  const qc = useQueryClient();
  const [key, setKey] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const status = useQuery({
    queryKey: ["provider"],
    queryFn: () => api("/provider"),
  });
  async function connect(disconnect = false) {
    setBusy(true);
    setError("");
    try {
      const connection = await post(
        disconnect ? "/provider/disconnect" : "/provider/connection",
        disconnect ? {} : { api_key: key },
      );
      setKey("");
      await qc.cancelQueries({ queryKey: ["provider"] });
      qc.setQueryData(["provider"], connection);
    } catch {
      setError(
        "Connection could not be updated. Check API access and cancel active iterations before changing the key.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel mb-6">
      <div className="eyebrow">AI connection</div>
      <h2 className="font-semibold mt-2">Connect your OpenAI API key</h2>
      <p className="text-sm text-slate-400 mt-2">
        No environment file needed. The backend keeps this key in memory until
        disconnect or restart. This is a shared connection for this single-user
        workspace. ChatGPT subscriptions do not include API usage.
      </p>
      <form
        className="flex flex-wrap items-end gap-3 mt-4"
        onSubmit={(e) => {
          e.preventDefault();
          void connect();
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
        {status.data?.source === "session" && (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => connect(true)}
          >
            Disconnect key
          </Button>
        )}
      </form>
      <p role="status" className="text-xs text-teal-200 mt-3">
        {status.data?.configured
          ? `Key configured (${status.data.source}). Not yet validated with OpenAI.`
          : "No OpenAI key connected."}
      </p>
      <p className="text-xs text-slate-500 mt-2">
        The key is sent to your backend, never saved in browser storage or the
        database. Use HTTPS when accessing remotely. Connecting does not make a
        paid API call.
      </p>
      {(error || status.error) && (
        <p role="alert" className="text-sm text-rose-300 mt-3">
          {error || "Unable to read connection status."}
        </p>
      )}
    </section>
  );
}
