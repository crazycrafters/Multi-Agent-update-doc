# Agent contracts

All agents receive the selected target role/job description as relevance criteria, never as evidence of candidate experience. No role, employer or candidate is hardcoded. The user-provided seed resume is authoritative input subject to conflict review.

- Resume Update Agent: analysis, localized editing, independent evidence audit, topic research. Web search permission exists only in the research call.
- Interviewee Agent: preparation, evidence-bounded simulated answers, structured feedback. No tools.
- Adversarial Interviewer: target-appropriate adaptive primary/follow-up questions and observable seven-dimension scoring. No tools.

Pydantic forbids extra message properties and bounds scores. Provider refusal or incomplete output fails the operation rather than substituting generated fixtures. The OpenAI SDK supplies capped retry and timeout handling. Usage is persisted; dollar estimates are unknown unless applicable pricing is configured. An iteration token budget stops future calls after the configured threshold; the final in-flight response may exceed the threshold. It is not a hard dollar cap.

Research sends generated generic topic queries only, not the full resume. Topic generation can still disclose inferred context; explicit web-research consent is required. Source URLs must come from actual web-search results/citations, and findings referencing other URLs are discarded. Source publication dates remain unknown unless independently established. Search failures are visible and resumable; research without consent is explicitly skipped.


The Codex adapter implements the same typed agent contracts through `thread/start`, `thread/resume`, `turn/start` with `outputSchema`, and filtered public notifications. Only the research thread has live web search enabled. Ordinary role threads have web search disabled and cannot inherit the research conversation. Codex usage notifications provide token counts; dollar estimates remain unknown because ChatGPT/Codex plan limits do not map to API token prices. Default model selection is left to Codex's account catalog; optional per-agent Codex model overrides are available. No hidden reasoning notification is persisted or displayed.
