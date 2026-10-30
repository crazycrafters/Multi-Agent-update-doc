import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  cleanup,
} from "@testing-library/react";
import Page from "./page";
const resume = {
  id: "r",
  title: "seed.md",
  target_role: "Operations Coordinator",
  job_description: "Coordinate logistics",
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
  claims: [
    {
      id: "c",
      text: "Coordinated schedules",
      status: "UNVERIFIED",
      warning: "Needs evidence",
    },
  ],
  confirmations: [],
  evidence: [],
  revisions: [],
};
beforeEach(() => {
  vi.stubGlobal("React", React);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return new Response(
          JSON.stringify({ error: { message: "Provider is not configured" } }),
          { status: 503 },
        );
      return new Response(
        JSON.stringify(input === "/api/resumes" ? [resume] : detail),
        { status: 200 },
      );
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("loads an arbitrary target role, requires sharing consent, and shows evidence warnings", async () => {
  render(<Page />);
  await screen.findByRole("heading", { name: "Operations Coordinator" });
  const start = screen.getByRole("button", { name: /Start iteration/ });
  expect(start).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/I authorize sending/));
  expect(start).toBeEnabled();
  fireEvent.click(start);
  await screen.findByRole("alert");
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Provider is not configured",
  );
  fireEvent.click(screen.getByRole("button", { name: /Evidence$/ }));
  expect(await screen.findByText("UNVERIFIED")).toBeVisible();
  expect(screen.getByText("Needs evidence")).toBeVisible();
});
it("switches monitoring mode without starting an iteration and supports new role input", async () => {
  render(<Page />);
  await screen.findByRole("heading", { name: "Operations Coordinator" });
  fireEvent.click(screen.getByRole("button", { name: "Agent monitoring" }));
  expect(
    screen.getByRole("heading", { name: "Resume Update Agent" }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Interviewee Agent" }),
  ).toBeVisible();
  expect(
    screen.getByRole("heading", { name: "Adversarial Interviewer" }),
  ).toBeVisible();
  expect(
    vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "POST"),
  ).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "New target role" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Target role")).toBeVisible(),
  );
  expect(screen.getByLabelText("Job description")).toBeVisible();
  expect(screen.getByLabelText("Seed resume")).toBeRequired();
});
