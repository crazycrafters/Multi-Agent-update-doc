import React from "react";
import { it, expect, vi, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceSettings } from "./workspace-settings";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("persists agent strategies and workflow choices without editing safety rules", async () => {
  vi.stubGlobal("React", React);
  const cfg = {
    strategies: { resume: "", interviewee: "", interviewer: "" },
    workflow: {
      question_count: 10,
      followups: true,
      initial_draft: true,
      research: true,
      semantic_retrieval: false,
    },
    api_budget_usd: null,
    input_usd_per_million: null,
    output_usd_per_million: null,
    search_usd_per_call: null,
    embedding_usd_per_million: null,
  };
  let saved: unknown;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") saved = JSON.parse(init.body as string);
      return new Response(
        JSON.stringify(
          url === "/api/settings"
            ? cfg
            : {
                provider: "openai",
                configured: false,
                source: "none",
                codex: { available: false, signed_in: false },
              },
        ),
        { status: 200 },
      );
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <WorkspaceSettings />
    </QueryClientProvider>,
  );
  fireEvent.change(await screen.findByLabelText("Interviewee"), {
    target: {
      value: "Acknowledge missing evidence before hypothetical designs.",
    },
  });
  fireEvent.change(screen.getByLabelText("Primary questions per iteration"), {
    target: { value: "4" },
  });
  fireEvent.click(screen.getByLabelText(/External research step/));
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() =>
    expect(saved).toMatchObject({
      strategies: {
        interviewee:
          "Acknowledge missing evidence before hypothetical designs.",
      },
      workflow: { question_count: 4, research: false },
    }),
  );
  expect(
    screen.getByText(
      /Evidence audit and your final strategy choice remain required/,
    ),
  ).toBeVisible();
});
