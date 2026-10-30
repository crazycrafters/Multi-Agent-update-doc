# AI Resume Evolution

A local-first resume workspace for **any target role**. Supply a role name, a job description, or both, plus a seed resume. Three separate agents analyze fit, simulate a ten-question adaptive interview, research gaps and propose evidence-grounded changes. Every cycle stops for explicit approval.

## Local quick start

Requirements: Docker with Compose and an OpenAI API key with access to the selected models and Responses web search. You can enter the key in the dashboard after startup; no environment file is required for this option.

```sh
cp .env.example .env
# Set RESUME_OPENAI_KEY (or OPENAI_API_KEY) in .env. Never commit the file.
docker compose up --build
```

Open the dashboard on port 3000. Under **AI connection**, enter your OpenAI API key and click **Connect key**. The single-user backend holds it in memory only, clears it on restart, and never returns it through status APIs. **Disconnect key** removes the session override (restoring an environment-provided key if configured). Cancel active work before changing the connection. Remote access requires HTTPS and authenticated private access. Connecting a key makes no provider call and does not verify account access. Upload a text PDF, DOCX, Markdown or UTF-8 text resume (2 MB maximum). Add a target role/job description. Explicitly authorize provider sharing before starting. External research is separately optional. A seed upload alone never sends information externally.

The original resume is immutable. Initial and manually edited claims are unverified. Candidate confirmations support specific nonnumerical personal claims. Public research and simulated answers never become personal evidence. Unsupported edits are held as confirmation tasks. No supported edit means no artificial new version.

See [architecture](docs/architecture.md), [agent contracts](docs/agents.md), [evidence policy](docs/evidence-model.md), [deployment](docs/deployment.md) and [verified progress](docs/progress.md).

## Without Docker

```sh
cd backend
uv sync --frozen --extra test
# SQLite is the default for lightweight local development; Compose uses PostgreSQL.
uv run alembic upgrade head
# Export OPENAI_API_KEY securely, or place it in backend/.env.
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

Tests inject deterministic provider responses. Production always uses the OpenAI SDK and fails clearly without credentials. Passing mocked integration tests is not evidence that a live provider run succeeded.

Resume revisions deliberately use a conservative evidence gate: auto-accepted new wording must match a confirmed evidence span and pass a separate model audit. Measurement artifacts remain unverified until reviewed; adding a metric record alone never licenses a numerical achievement. Exports include drafts, so review claim warnings before submitting.

## MCP and cloud skills

The cloud-environment runtime and onboarding skills are used by the development assistant to inspect networking, validate services and save reusable environment configuration. They are not runtime dependencies of the application. The application agents currently use OpenAI Responses (including web search) and LangGraph directly; an MCP client and a runtime skill registry are not implemented.

The managed cloud uses the non-reserved secret name `RESUME_OPENAI_KEY` with destination `api.openai.com`. Standard local `OPENAI_API_KEY` is also accepted. Configure values securely in environment settings, review/save the draft, and publish it. Saving a draft alone does not apply credentials or publish a snapshot.

ChatGPT login is not implemented in the dashboard. A future Codex provider can use the supported Codex ChatGPT authentication and separate persisted threads for the three agents. That is different from reusing ChatGPT browser cookies or passing a ChatGPT login token to the Responses API. See the [official Codex app-server source](https://github.com/openai/codex/tree/main/codex-rs/app-server) and [TypeScript SDK](https://github.com/openai/codex/tree/main/sdk/typescript).
