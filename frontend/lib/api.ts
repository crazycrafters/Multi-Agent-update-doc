export type Row = Record<string, any>; // API audit payloads vary by structured agent message type.
export async function api<T = Row>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const token =
    typeof window !== "undefined" ? sessionStorage.getItem("apiToken") : null;
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      body.error?.message ||
        JSON.stringify(body.detail) ||
        `Request failed (${response.status})`,
    );
  }
  return response.json();
}
export function post(path: string, body: unknown = {}) {
  return api(path, { method: "POST", body: JSON.stringify(body) });
}
export type StreamEvent = {
  id: number;
  agent: string;
  kind: string;
  data: Row;
  created_at: string;
};
export async function streamEvents(
  id: string,
  after: number,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
) {
  const headers: HeadersInit = {};
  const token = sessionStorage.getItem("apiToken");
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`/api/iterations/${id}/events?after=${after}`, {
    headers,
    signal,
  });
  if (!res.ok || !res.body)
    throw new Error("Unable to connect to activity stream");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = block.split("\n").find((x) => x.startsWith("data: "));
      if (data && !block.includes("event: idle"))
        onEvent(JSON.parse(data.slice(6)));
    }
  }
}
