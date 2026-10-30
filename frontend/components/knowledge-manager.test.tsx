import React from "react";
import { it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { KnowledgeManager } from "./knowledge-manager";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("creates knowledge under the selected profile without enabling embeddings silently", async () => {
  vi.stubGlobal("React", React);
  let records: Record<string, unknown>[] = [];
  const writes: { url: string; body: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        const body = JSON.parse(init.body as string);
        writes.push({ url, body });
        records = [
          {
            id: "d1",
            profile_id: "alpha",
            ...body,
            active: true,
            version: 1,
            chunks: 1,
            embedded_chunks: 0,
          },
        ];
        return new Response(JSON.stringify(records[0]), { status: 201 });
      }
      return new Response(JSON.stringify(records), { status: 200 });
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <KnowledgeManager
        profile={{ id: "alpha", name: "Alpha", target_role: "Engineer" }}
      />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("Title"), {
    target: { value: "Retry implementation" },
  });
  fireEvent.change(screen.getByLabelText("Source / artifact reference"), {
    target: { value: "Project notes" },
  });
  fireEvent.change(screen.getByLabelText("Project dossier / knowledge"), {
    target: { value: "I implemented bounded retry backoff." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save knowledge" }));
  await screen.findByText("Retry implementation");
  expect(writes[0].url).toBe("/api/profiles/alpha/knowledge");
  expect(writes[0].body.status).toBe("UNVERIFIED");
  const index = screen.getByRole("button", { name: "Index embeddings" });
  expect(index).toBeDisabled();
  expect(writes.some((w) => w.url.endsWith("/embed"))).toBe(false);
});
