# Profile knowledge and RAG

Each profile defines a target role and job description. Its seed resumes, knowledge documents, chunks and citations remain separated from other profiles. This is logical workspace separation for one user, not a multi-tenant authorization system. Provider credentials and usage/budget settings are shared by the backend.

## Dashboard management

Create a profile, add or upload a project dossier in **Knowledge database**, then upload the seed resume and start a run. The manager supports source inspection, metadata and text editing, version-preserving revisions, archival, lexical/hybrid search, explicit embedding indexing, and Markdown/JSON export. Archived records remain in the database for audit; archival does not reclaim storage. Database administration/raw SQL access is intentionally not exposed.

Personal project evidence should state ownership, actual mechanisms, architecture/request flow, decisions and alternatives, failures, tests, measurements and limitations. Use `UNVERIFIED` until confirmed. Selecting `CANDIDATE_CONFIRMED` is an explicit candidate assertion, not independent verification. `VERIFIED` cannot be set through general knowledge ingestion. Measurements still need direct artifact review through the existing metric-evidence workflow. Public references are forced to `PUBLIC_CONTEXT`; open questions remain `UNVERIFIED`. Simulated answers are never personal evidence. Attributed research summaries are stored as clearly labeled technical references and deduplicated by source within a profile.

Editing creates a new document ID/version and archives the former version. Archived passages are excluded from retrieval. Old citations remain inspectable in stored events and records. Active contradicted personal knowledge blocks automatic resume edits conservatively; resolve/correct/archive it before applying a revision.

## Retrieval

Documents split into overlapping text chunks (approximately 1000 characters with 150-character overlap). Each chunk stores its document/profile IDs, text, position and optional embedding/model metadata. PostgreSQL full-text search covers passage text and title/project metadata. Query terms and related resume claims supply retrieval context. Optional exact cosine search over pgvector combines with lexical ranks through reciprocal-rank fusion. No HNSW/IVFFlat index is needed initially. Retrieved chunks include source, kind, evidence status and version, so the agent must distinguish facts, references and unknowns. Citation IDs are validated against the passages actually retrieved for that call.

Lexical retrieval needs no model calls. Semantic indexing/querying uses the separate OpenAI embeddings endpoint, `text-embedding-3-small`, 1536 dimensions. Codex login does not supply that endpoint. Explicit consent is required for indexing and for semantic queries during a run. Without a key/consent, use full-text RAG. Partial indexing is visible; existing matching embeddings are reused on retry. Different embedding models/dimensions are not mixed. Reindex after a future model migration. Indexing progress and token/cost estimates are persisted; cost estimates are not invoices and an interrupted remote request may be billed without a recorded result.

## API and portability

- `GET/POST /profiles`, `PUT /profiles/{id}`: target profile management.
- `GET/POST /profiles/{id}/knowledge`: inspect/add records.
- `POST /profiles/{id}/knowledge/upload`: readable text/Markdown/PDF/DOCX, maximum 2 MB.
- `PUT /profiles/{id}/knowledge/{document}`: version-preserving revision.
- `POST /profiles/{id}/knowledge/{document}/archive`: exclude from retrieval.
- `POST /profiles/{id}/knowledge/{document}/embed`: explicitly consented indexing.
- `POST /profiles/{id}/knowledge/search`: scoped lexical or consented hybrid retrieval.
- `GET /profiles/{id}/knowledge/export?format=md|json`: profile-scoped export.
- `GET/PUT /settings`: strategies, optional workflow steps, budget and prices.
- `GET /usage`: recorded usage and available Codex rate-limit windows.
- `POST /iterations/{id}/strategies/select`: select one of the generated short strategies.

Markdown exports active documents and directly supplied personal evidence, with sources/status labels and a separate unresolved-question section, suitable for custom GPT Knowledge uploads. JSON exports schema version 1, profile metadata, document/chunk IDs, sources/statuses, direct evidence and confirmation records. Embedding arrays and simulated answers are omitted. It is an export format, not an implemented automatic import/migration client. Preserve sources as the authoritative data and regenerate search indexes as needed.

## Operational notes

Compose uses pgvector-enabled PostgreSQL 17 and the existing named database volume. Back up before upgrades. Migrations backfill a distinct profile for each legacy resume; originals and existing evidence/history remain intact. A hosted database must support `CREATE EXTENSION vector`. Full-text uses an English configuration; non-English search may benefit from semantic retrieval or a future locale-specific text-search configuration. SQLite development behavior is lexical fallback, not PostgreSQL full-text stemming.

API cost reporting uses configured shared rates and a user-set workspace budget; provider account balance is unavailable. Unknown/failed-call costs remain unknown, and one in-flight call can exceed a limit. Codex quota percentages/reset times are shown only if returned by the signed-in account. Neither usage counter authorizes extra spending or bypasses provider restrictions.
