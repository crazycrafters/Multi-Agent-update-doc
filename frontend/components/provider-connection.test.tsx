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
