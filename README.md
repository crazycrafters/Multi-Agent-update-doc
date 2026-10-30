# AI Resume Evolution

A local-first resume workspace for **any target role**. Supply a role name, a job description, or both, plus a seed resume. Three separate agents analyze fit, simulate a ten-question adaptive interview, research gaps and propose evidence-grounded changes. Every cycle stops for explicit approval.

## Local quick start

Requirements: Docker with Compose and either an OpenAI API key **or a ChatGPT account with Codex access**. No `.env` file is needed to connect from the dashboard.

```sh
docker compose up --build
```

Open the dashboard on port 3000. Under **AI connection**, choose:

- **OpenAI API key**: enter a key and click **Connect key**. The backend keeps it in process memory only. API billing applies. Disconnect removes the session override; restart clears it. An environment-provided key is an optional fallback.
- **Codex / ChatGPT login**: click **Sign in with ChatGPT**, follow the OpenAI device-sign-in link and enter the displayed one-time code. After authorization, click **Use Codex**. To restore an already saved login after a restart, click **Use Codex**. Codex model availability and subscription limits apply; this is not a general-purpose Responses API key.

Codex CLI 0.163.0 is included in the backend image. Its managed authentication and agent transcripts live in the private `codex_data` Docker volume. Logout removes the managed login; transcripts remain. Ordinary ChatGPT browser conversations and cookies are never reused. This is a single-user workspace: only connect accounts on a backend you trust. Use HTTPS and authentication for remote access. Cancel active work before changing providers. Iterations are pinned to their original provider for recovery.

Upload a readable PDF, DOCX, Markdown or UTF-8 text resume (2 MB maximum), and add a target role/job description. Explicitly authorize provider sharing before starting. External research is separately optional. Uploading alone never shares the resume externally. Connecting or selecting a provider does not initiate a model turn.

The original resume is immutable. Initial and manually edited claims are unverified. Candidate confirmations support specific nonnumerical personal claims. Public research and simulated answers never become personal evidence. Unsupported edits are held as confirmation tasks. No supported edit means no artificial new version.

See [architecture](docs/architecture.md), [agent contracts](docs/agents.md), [evidence policy](docs/evidence-model.md), [deployment](docs/deployment.md) and [verified progress](docs/progress.md).

## Without Docker

```sh
cd backend
uv sync --frozen --extra test
# SQLite is the default for lightweight local development; Compose uses PostgreSQL.
uv run alembic upgrade head
# Optional for Codex outside Docker: npm install -g @openai/codex@0.163.0
# Select/connect either provider in the dashboard.
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

`BACKEND_URL` configures the server-side Next.js proxy (default http://127.0.0.1:8000). API credentials are never bundled into the frontend. Configure `API_ACCESS_TOKEN` to protect the API beyond a private workstation; the dashboard accepts it under API access and stores it in session storage. This is a single-user local application, not a multi-tenant authentication system.

## Tests

```sh
cd backend
uv run pytest -q
cd ../frontend
npm test
npm run typecheck
npm run build
```

Tests inject deterministic provider responses. Production uses either OpenAI Responses or the pinned Codex app-server protocol and fails clearly without the selected provider credentials. Passing mocked integration tests is not evidence that a live provider run succeeded.

Resume revisions deliberately use a conservative evidence gate: auto-accepted new wording must match a confirmed evidence span and pass a separate model audit. Measurement artifacts remain unverified until reviewed; adding a metric record alone never licenses a numerical achievement. Exports include drafts, so review claim warnings before submitting.

## MCP and cloud skills

The cloud-environment runtime and onboarding skills are used by the development assistant to inspect networking, validate services and save reusable environment configuration. They are not runtime dependencies of the application. The application agents use OpenAI Responses or a Codex provider through LangGraph; an MCP client and a runtime skill registry are not implemented.

The managed cloud uses the non-reserved secret name `RESUME_OPENAI_KEY` with destination `api.openai.com`. Standard local `OPENAI_API_KEY` is also accepted. Configure values securely in environment settings, review/save the draft, and publish it. Saving a draft alone does not apply credentials or publish a snapshot.

See [provider setup and security](docs/providers.md) for authentication, configuration, thread persistence and deployment details. The Codex implementation follows the [official app-server protocol](https://github.com/openai/codex/tree/main/codex-rs/app-server); it never extracts OAuth tokens or forwards them to the Responses API.
