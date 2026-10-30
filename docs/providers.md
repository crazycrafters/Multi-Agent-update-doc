# Provider options

The dashboard supports two independent authentication paths. It never asks for ChatGPT browser cookies or bearer tokens.

| Provider | Dashboard action | Credential storage | Usage |
| --- | --- | --- | --- |
| OpenAI Responses API | Paste key, Connect key | Backend memory until restart/disconnect; optional environment fallback | Separate API billing |
| Codex with ChatGPT | Sign in with ChatGPT, complete device authorization, Use Codex | Official Codex-managed files in dedicated backend volume | Account's Codex models and limits |

The selected provider initially defaults to OpenAI after a backend restart. Select Codex to restore its saved account. Switching is blocked while any workflow task is active, including paused tasks. Cancel first. Recovered iterations are pinned to their provider and cannot silently continue on the other provider. Changing providers never starts an iteration automatically. Both paths require explicit provider-sharing consent in the dashboard and separate consent for research.

## Codex protocol and isolation

CLI version 0.163.0 is pinned in Docker. For local Python development install it with `npm install -g @openai/codex@0.163.0`; the backend starts it automatically. No frontend package or browser extension is required. Python communicates over stdio JSON-RPC using the generated protocol schemas inspected from this version. Unsupported CLI versions may fail and should not be substituted without testing.

Device login uses `account/login/start` with `chatgptDeviceCode`. The dashboard displays only the one-time code and an HTTPS auth.openai.com URL. Polling reads sign-in status; authentication tokens never pass through the dashboard or application database. Cancel/logout invokes the official account operations. A dashboard login attempt can fail if device authorization is disabled by the account/workspace.

The runtime uses an application-specific Codex home, not the host's existing login. It inherits proxy/CA settings and the minimum runtime environment, excluding application API keys, database credentials and GitHub tokens. Its isolated working directory contains no application repository. Shell/patch/code-mode tools, delegation, plugins, connectors, memories and MCP servers are disabled; read-only sandbox policy and rejection of unsolicited server tool requests provide additional controls. This is still a trusted local executable with sensitive authentication state, so run the backend privately.

Each iteration stores separate role thread IDs in `provider_threads`, plus isolated audit and research channels. Research never resumes a role thread containing personal resume context. Generated sources are filtered against observed web-search results/open-page actions. Unattributed URLs are discarded, and no sources may still yield a no-change, awaiting-approval iteration. The same claim audit and numerical-evidence gate apply to both providers.

Only observable assistant message deltas, final structured outputs and web-tool metadata are processed. Hidden reasoning is ignored. Token usage comes from Codex usage notifications; dollar costs are deliberately unknown. Failed/expired sessions and model errors stop with a resumable workflow error. Timeout/cancellation sends `turn/interrupt`; no automatic repeated inference is attempted. A crash after external completion can still repeat a billed/limited turn on retry.

## Configuration

- `RESUME_CODEX_HOME`: dedicated credential/transcript directory (default `.codex-runtime`, ignored by Git). Compose mounts `/app/.codex-runtime` to `codex_data`.
- `RESUME_CODEX_BINARY`: executable path (default `codex`).
- `CODEX_MODEL`: optional common model override; unset uses the account default.
- `CODEX_RESUME_MODEL`, `CODEX_INTERVIEWEE_MODEL`, `CODEX_INTERVIEWER_MODEL`: optional per-agent overrides. Model access is checked by Codex when the turn starts.
- `CODEX_TIMEOUT_SECONDS`: per-turn timeout (default 180 seconds).

For a managed network, allow auth.openai.com and chatgpt.com for Codex, and api.openai.com for the API path. Use the supported environment policy workflow; never bypass a blocked destination. No model turn is run by login or provider selection.

Deterministic tests simulate the Codex protocol and cover the entire three-agent loop, isolated channels, sources, reconnect/resume, auth/origin protection and rejected tool requests. An isolated real app-server initialization was also tested without authentication. These checks do not establish a successful real ChatGPT login or live inference run.

For environments created during the earlier API-only setup, environment settings may still list a required `RESUME_OPENAI_KEY`. Remove that legacy requirement when using Codex only or entering keys in the dashboard. This affects cloud configuration publication, not the application's no-environment-file support. The draft API cannot remove existing requirements.
