import React from "react";
import { it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { LiveWorkflow } from "./live-workflow";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("shows active agent spark, streamed output, and retrieved profile context", () => {
  vi.stubGlobal("React", React);
  const events = [
    {
      id: 1,
      agent: "interviewee",
      kind: "task_started",
      created_at: "2026-01-01",
      data: { task: "Question 1 answer" },
    },
    {
      id: 2,
      agent: "interviewee",
      kind: "knowledge_retrieved",
      created_at: "2026-01-01",
      data: {
        passages: [
          {
            id: "k1",
            title: "Pipeline",
            kind: "personal",
            status: "CANDIDATE_CONFIRMED",
            text: "Owned bounded retry logic.",
          },
        ],
      },
    },
    {
      id: 3,
      agent: "interviewee",
      kind: "answer_snapshot",
      created_at: "2026-01-01",
      data: {
        task: "Question 1 answer",
        text: "I implemented the confirmed retry mechanism.",
      },
    },
  ];
  const { container } = render(
    <LiveWorkflow
      run={{
        iteration: {
          state: "INTERVIEWING",
          run_step: 2,
          planned_iterations: 3,
        },
        executions: [
          {
            agent: "interviewee",
            task: "Question 1 answer",
            status: "running",
          },
        ],
        transcript: [],
      }}
      events={events}
    />,
  );
  expect(
    screen.getByText("I implemented the confirmed retry mechanism."),
  ).toBeVisible();
  expect(container.querySelectorAll(".agent-spark").length).toBeGreaterThan(0);
  expect(screen.getByText(/Retrieved context/)).toBeInTheDocument();
  expect(screen.getByText(/Iteration 2 \/ 3/)).toBeVisible();
});
