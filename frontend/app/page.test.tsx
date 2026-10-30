import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import Page from "./page";
const profile = {
  id: "p",
  name: "Operations application",
  target_role: "Operations Coordinator",
  job_description: "Coordinate logistics",
};
const resume = {
  id: "r",
  profile_id: "p",
  title: "seed.md",
  target_role: "Operations Coordinator",
  current_version_id: "v",
};
const detail = {
  resume,
  versions: [
    {
      id: "v",
      number: 1,
      text: "# Candidate\nCoordinated schedules",
      submission_ready: false,
    },
  ],
  iterations: [],
  claims: [{ id: "c", text: "Coordinated schedules", status: "UNVERIFIED" }],
  confirmations: [],
  evidence: [],
  revisions: [],
  metrics: [],
};
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return new Response(
          JSON.stringify({ error: { message: "Provider is not configured" } }),
          { status: 503 },
        );
      const data =
        url === "/api/profiles"
          ? [profile]
          : url === "/api/resumes"
            ? [resume]
            : url === "/api/usage"
              ? {
                  provider: "openai",
                  tokens: 0,
                  api: {
                    budget_usd: null,
                    estimated_spent_usd: 0,
                    remaining_budget_usd: null,
                    unpriced_calls: 0,
                  },
                  codex: { tokens: 0, limits: null },
                }
              : url.includes("/knowledge")
                ? []
                : detail;
      return new Response(JSON.stringify(data), { status: 200 });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("defaults to monitoring, keeps AI connection on Settings, and requires run consent", async () => {
  render(<Page />);
  await screen.findByRole("heading", { name: "Operations Coordinator" });
  expect(screen.queryByLabelText("OpenAI API key")).not.toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "AI connection & settings" }),
  ).toHaveAttribute("href", "/settings");
  expect(
    await screen.findByRole("heading", { name: "Resume builder" }),
  ).toBeVisible();
  expect(screen.getByRole("heading", { name: "Interviewee" })).toBeVisible();
  const start = screen.getByRole("button", { name: "Start iteration" });
  expect(start).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I authorize sending/));
  expect(start).toBeEnabled();
  fireEvent.click(start);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Provider is not configured",
  );
});
it("opens profile-scoped knowledge management and preserves resume history", async () => {
  render(<Page />);
  await screen.findByRole("heading", { name: "Operations Coordinator" });
  fireEvent.click(
    screen.getAllByRole("button", { name: "Knowledge database" })[0],
  );
  expect(
    await screen.findByRole("heading", { name: /Knowledge Manager/ }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Export Markdown" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Interviewee" })).toBeVisible();
  fireEvent.click(screen.getAllByRole("button", { name: "Resume history" })[0]);
  expect(
    await screen.findByRole("heading", { name: "Resume update history" }),
  ).toBeVisible();
  expect(screen.getByText(/Draft: unverified claims/)).toBeVisible();
});
