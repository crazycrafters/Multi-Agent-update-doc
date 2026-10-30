# Implementation progress

The repository started empty. The application now accepts **any target role name and/or job description plus a seed resume**. No candidate, employer, profession or seniority is hardcoded.

## Implemented

1. Foundation: FastAPI, Pydantic, SQLAlchemy normalized records, PostgreSQL Compose service, Alembic migration, safe format/size validation, immutable original and version history. SQLite is supported for lightweight local development.
2. Agents: three separate OpenAI Responses prompts and permissions, typed structured outputs, per-agent models, SDK timeout/retries, persisted execution logs, token usage and configurable cost estimates. Production has no mock fallback.
3. Interview: LangGraph phase dispatch over database checkpoints; ten adaptive primary questions and at most one follow-up each; separately persisted simulated answers, streaming observable answer snapshots, seven-dimension scores and weakness feedback. Pause, cancel, resume, failure retry and crash recovery are supported.
4. Research: consented real OpenAI web search, generic topic queries, source URL attribution, research findings and study recommendations. Public research remains separate from personal evidence. No attributable result can still reach approval without inventing findings.
5. Revision: initial and post-interview proposals, independent model audit, conservative deterministic personal-evidence gate, unsupported numerical rejection, candidate confirmation tasks, human measurement-artifact review, transactional version activation, no artificial versions when edits are unsupported, explicit approval for unlimited subsequent cycles.
6. Dashboard: Next.js / TypeScript / Tailwind / shadcn-style components / TanStack Query, runtime same-origin API proxy, resume-only and monitoring modes, three agent panels, replayable SSE, interview and research views, evidence and measurement entry/review, manual draft editing, side-by-side line diff, Markdown/PDF/DOCX exports.
7. Delivery: Dockerfiles and persistent PostgreSQL volume, cloud CA/proxy override, GitHub Actions, architecture/agent/evidence/deployment docs and reusable cloud setup/start instructions saved to the environment draft.

## Verified

- Backend: **15 tests passed against PostgreSQL** in the isolated `resume_test` database. Tests cover the full upload → interview → research → revise → approval loop, ten primary plus ten follow-up questions, source persistence, unsupported claim/metric rejection, no-change cycles, no-source research, pause/resume/cancel, crash recovery, failure retry, approval, SSE replay and exports.
- Real installed OpenAI SDK exercised with mocked HTTP transports for strict structured outputs, web-search citations and streamed answer snapshots. No fabricated response provider is reachable from the production configuration.
- Alembic upgrade/check/downgrade/upgrade round trip passed on a fresh SQLite database. Compose applied the initial migration successfully on PostgreSQL.
- Frontend: **2 component integration tests passed**, TypeScript passed and Next.js production build passed.
- Both Docker images built with TLS verification enabled and the managed CA supplied as a BuildKit secret.
- Running frontend → API → PostgreSQL stack: rendered dashboard, health request, synthetic resume upload/parse, arbitrary role/job-description context, Markdown/PDF/DOCX exports, missing-consent rejection and missing-credential error all passed.
- No paid AI calls or live web-search calls were made.

## Remaining validation and limits

- Live execution requires either dashboard/API-key configuration or a user-authorized Codex ChatGPT login, the selected provider network destinations, and authorization to consume account usage. Deterministic E2E success is not live-provider success. Do not declare the complete production definition of done satisfied until that validation passes.
- Cloud draft persistence is confirmed; publication and fresh-task snapshot restoration are not verified.
- Single-user, one-backend-worker deployment only. Authentication is an optional shared API token, not multi-tenant identity/authorization. No distributed leases or queue.
- No runtime MCP client/skill registry; cloud onboarding/runtime skills are used by the development assistant only.
- Automatic paraphrases are deliberately restricted to exact eligible evidence spans. Human review is required for broader rewrites. Human-reviewed measurements are explicit human attestations, not independent machine verification.
- Basic PDF typography has limited non-Latin font support; no OCR. Document parsing is bounded by input/expanded-document size but not isolated in an OS sandbox. Monaco and human interview mode are optional and not implemented.
- A crash between a billed provider response and database persistence can repeat that call. The token budget is a pre-call gate, not a strict dollar cap.

Use the existing isolated checkout; do not create Git worktrees unless requested. Continue from these verified results and preserve all original resumes and evidence provenance.

## Dashboard credential connection update

- Added a password input and connect/disconnect controls. Keys travel in a POST body to the backend and stay in process memory only; they are absent from browser storage, database records and status responses. Environment keys remain an optional fallback. Restarting loses the session override.
- Connection status explicitly says configured, not validated. Connecting does not make a paid API request. Active tasks block credential changes; existing API-token protection and an origin check protect connection mutations.
- Verified: 17 backend tests passed, including session connection/disconnect, status redaction, auth/origin rejection and active-work protection. Three frontend tests passed, including input clearing and no browser-storage persistence. Production build passed.
- ChatGPT-authenticated Codex threads are a possible future provider integration; this update does not implement that adapter or reuse browser cookies.

## Two-provider update (current)

- Added OpenAI API-key and Codex/ChatGPT options in the dashboard. API keys stay in process memory; Codex uses official device authorization with managed credential/transcript files in a dedicated Docker volume. No browser cookies, extracted tokens or existing host account credentials are used.
- Implemented a pinned Codex 0.163.0 app-server JSON-RPC adapter with strict output schemas, streamed public messages, usage notifications, timeout interruption, isolated per-iteration role threads and persisted resume IDs. Independent audits and generic-topic research use separate channels. Research sources must be observed in real web-tool actions/results. Shell/patch/code-mode/delegation/MCP/plugin tools are disabled and unexpected requests denied.
- Iterations persist their original provider. Active tasks prevent provider switching; recovered Codex iterations need Codex selected before resume. Provider selection never automatically starts an iteration. Codex dollar-cost estimates remain unknown rather than using API pricing.
- Added a migration for provider pinning and thread records. CLI is included in the backend image. `.codex-runtime` is excluded from Git and Docker build context. Optional per-agent Codex models default to the account catalog.
- Verified: **22 backend tests passed against PostgreSQL**, including both full mocked provider workflows, Codex thread isolation/resumption, research privacy and attribution, transport secret isolation/tool denial, login origin guards, timeout interruption and wrong-provider recovery rejection. **4 frontend tests passed**, TypeScript passed, production build passed. Migration round-trip/check passed on SQLite and the migration applied to the running PostgreSQL app.
- Both Docker images built successfully. The pinned CLI and actual isolated app-server initialization were verified inside the backend container. Dashboard health/provider endpoints return successfully through the runtime proxy. These checks use no authenticated model turns.
- Live ChatGPT device authorization and authenticated inference remain unverified because they require the user's account and usage authorization. Model/account/workspace availability can still reject turns.
- Saved updated cloud startup guidance and added auth.openai.com/chatgpt.com to the network draft while retaining api.openai.com. Review/save and publication remain user actions. The legacy required RESUME_OPENAI_KEY draft entry should be removed in environment settings for Codex-only/dashboard-key use; the configuration tool cannot delete existing requirements.

Earlier notes describing Codex as a future adapter are superseded by this update. Runtime MCP/skill registry integration remains outside the application.
