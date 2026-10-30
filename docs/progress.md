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

- Live OpenAI agent/research execution requires a securely configured `RESUME_OPENAI_KEY` (or `OPENAI_API_KEY` locally), runtime access to api.openai.com, and approval for paid validation. Deterministic E2E success is not live-provider success. Do not declare the complete production definition of done satisfied until that validation passes.
- Cloud draft persistence is confirmed; publication and fresh-task snapshot restoration are not verified.
- Single-user, one-backend-worker deployment only. Authentication is an optional shared API token, not multi-tenant identity/authorization. No distributed leases or queue.
- No runtime MCP client/skill registry; cloud onboarding/runtime skills are used by the development assistant only.
- Automatic paraphrases are deliberately restricted to exact eligible evidence spans. Human review is required for broader rewrites. Human-reviewed measurements are explicit human attestations, not independent machine verification.
- Basic PDF typography has limited non-Latin font support; no OCR. Document parsing is bounded by input/expanded-document size but not isolated in an OS sandbox. Monaco and human interview mode are optional and not implemented.
- A crash between a billed provider response and database persistence can repeat that call. The token budget is a pre-call gate, not a strict dollar cap.

Use the existing isolated checkout; do not create Git worktrees unless requested. Continue from these verified results and preserve all original resumes and evidence provenance.
