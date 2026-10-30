"use client";
import Link from "next/link";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceSettings } from "@/components/workspace-settings";
const client = new QueryClient();
export default function SettingsPage() {
  return (
    <QueryClientProvider client={client}>
      <main className="max-w-7xl mx-auto p-6 md:p-10">
        <Link href="/" className="text-teal-200 text-sm">
          ← Dashboard
        </Link>
        <h1 className="text-3xl font-semibold my-6">Settings</h1>
        <details className="panel mb-5">
          <summary className="text-sm">Backend access token</summary>
          <input
            aria-label="Backend access token"
            className="mt-3"
            type="password"
            autoComplete="off"
            onChange={(e) => sessionStorage.setItem("apiToken", e.target.value)}
          />
          <button
            className="text-teal-200 text-sm mt-3"
            onClick={() => client.invalidateQueries()}
          >
            Apply access token
          </button>
        </details>
        <WorkspaceSettings />
      </main>
    </QueryClientProvider>
  );
}
