# Evidence policy

Claims use VERIFIED, CANDIDATE_CONFIRMED, PUBLIC_CONTEXT, PROPOSED, UNVERIFIED or CONTRADICTED. Uploads and manual edits create UNVERIFIED claims. A candidate may explicitly confirm a specific contribution; that action creates a separate record and does not independently verify measurements.

Only personal VERIFIED/CANDIDATE_CONFIRMED evidence may support automatic revisions. A separate structured model audit must PASS. A deterministic gate then checks source-version identity, evidence membership, exact supported wording, numerical measurements, conflicts and ambiguous replacements. Rejected edits become confirmation tasks. The system can correctly produce no changes.

For conservative automatic acceptance, the new wording must appear verbatim in eligible evidence. This intentionally rejects some defensible paraphrases. A human can confirm the exact wording and run another iteration. This policy does not establish semantic truth of candidate assertions; review is required before submission. Original unverified claims are preserved and visibly marked, never silently promoted to submission-ready.

Metric evidence stores definition, numerator/denominator, baseline/final, sample/window, workload/hardware/concurrency/model, method, source, status and limitations. The API distinguishes absolute, relative percentage and percentage-point changes (the latter only has meaning for proportions). Correlation and causal evidence remain distinct. Uploaded measurement records stay UNVERIFIED. There is intentionally no automatic promotion of user-supplied artifacts to VERIFIED.

Research is PUBLIC_CONTEXT in meaning and stored in separate source/finding tables, not personal evidence. Simulated answers are explicitly tagged and never imported into evidence. Candidate confirmations are immutable responses; corrections become new evidence. PDF/DOCX/Markdown exports may contain drafts and preserve visible source wording; always review the dashboard warnings first.
