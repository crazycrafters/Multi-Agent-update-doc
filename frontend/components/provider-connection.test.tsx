import React from "react";
import { expect, it, vi, afterEach } from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ProviderConnection } from "./provider-connection";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("sends key only in the request body, clears the input, and disconnects without browser persistence", async () => {
  vi.stubGlobal("React", React);
  let source = "none";
  const requests: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        requests.push({ url, body: JSON.parse(init.body as string) });
        source = url.endsWith("disconnect") ? "none" : "session";
      }
      return new Response(
        JSON.stringify({
          configured: source === "session",
          source,
          verified: false,
        }),
        { status: 200 },
      );
    }),
  );
  const save = vi.spyOn(Storage.prototype, "setItem");
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProviderConnection />
    </QueryClientProvider>,
  );
  const input = screen.getByLabelText("OpenAI API key");
  fireEvent.change(input, { target: { value: "sk-test-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Connect key" }));
  await screen.findByRole("button", { name: "Disconnect key" });
  expect(requests[0]).toEqual({
    url: "/api/provider/connection",
    body: { api_key: "sk-test-secret" },
  });
  expect(input).toHaveValue("");
  expect(save).not.toHaveBeenCalled();
  expect(screen.queryByText("sk-test-secret")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect key" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Disconnect key" }),
    ).not.toBeInTheDocument(),
  );
  expect(requests[1].url).toBe("/api/provider/disconnect");
  save.mockRestore();
});

it("shows Codex device authorization and requires explicit provider selection", async () => {
  vi.stubGlobal("React", React);
  let signed = false;
  let provider = "openai";
  let pending: unknown = null;
  const paths: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        paths.push(url);
        if (url.endsWith("/login"))
          pending = {
            loginId: "login-test",
            userCode: "TEST-CODE",
            verificationUrl: "https://auth.openai.com/codex/device",
          };
        if (url.endsWith("/select")) {
          signed = true;
          pending = null;
          provider = "codex";
        }
        if (url.endsWith("/logout")) signed = false;
      }
      return new Response(
        JSON.stringify({
          provider,
          configured: provider === "codex" && signed,
          source: provider === "codex" ? "codex" : "none",
          codex: { available: true, signed_in: signed, pending_login: pending },
        }),
        { status: 200 },
      );
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ProviderConnection />
    </QueryClientProvider>,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Codex / ChatGPT login" }),
  );
  expect(screen.queryByLabelText("OpenAI API key")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sign in with ChatGPT" }));
  await screen.findByText("TEST-CODE");
  expect(
    screen.getByRole("link", { name: "Open OpenAI device sign-in" }),
  ).toHaveAttribute("href", "https://auth.openai.com/codex/device");
  expect(paths).toEqual(["/api/provider/codex/login"]);
  fireEvent.click(screen.getByRole("button", { name: "Use Codex" }));
  await screen.findByText(/Active provider: Codex/);
  expect(paths[1]).toBe("/api/provider/select");
  expect(screen.queryByText("TEST-CODE")).not.toBeInTheDocument();
});
