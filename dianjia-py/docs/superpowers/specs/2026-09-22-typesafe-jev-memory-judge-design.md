# TypeSafe Jev Memory Judge Design

## Context

Dianjia currently uses a general-purpose AI client to produce JSON memory decisions in `MemoryService._judge_candidate`. This is a bounded semantic decision over a candidate and at most five retrieved memories, so it matches TypeSafe Jev's structured System One interface better than the text-generating daily summary, candidate extraction, and RAG answer stages.

The established environment must remain unchanged: the web service stays on `127.0.0.1:8765`, the knowledge root remains `/Users/zhangshichao/Documents/Workspace/dianjia`, and the real SQLite index remains `/Users/zhangshichao/Documents/Workspace/dianjia/dianjia-py/data/dianjia.db`. Jev is opt-in and must not alter the existing Codex/LLM or local fallback behavior unless explicitly enabled.

## Architecture

Install the official TypeSafe skill project-locally at `.agents/skills/typesafe-ai` so coding agents can read current TypeSafe guidance without duplicating vendor documentation.

Add two application boundaries:

- `app/ai/typesafe.py` implements the generic TypeSafe HTTP transport, authentication, retry policy, and response validation with the Python standard library.
- `app/memory_judge.py` translates Dianjia candidates and retrieved memories into Jev state/questions and maps the structured response into `MemoryDecision`.

`MemoryService` retains ownership of retrieval, persistence, source processing, audit records, and the existing local rules. It selects the memory judge from configuration and uses this fallback chain when TypeSafe is selected:

1. TypeSafe Jev judge.
2. Existing general-purpose AI judge.
3. Existing local rules.

The default remains the existing general-purpose AI judge followed by local rules.

## Configuration

The opt-in selector is `DIANJIA_MEMORY_JUDGE=typesafe`; the default value is `llm`. TypeSafe uses `TYPESAFE_API_KEY`, `TYPESAFE_MODEL` (default `jev-latest`), and `TYPESAFE_BASE_URL` (default `https://api.typesafe.ai/v1`). The real `.env` is not edited. Commented examples and behavior documentation are added to `.env.example` and `README.md`.

Credentials are read from the environment or the existing ignored `.env` file. They are never accepted as CLI arguments or written to logs, audit payloads, tests, or tracked files.

## Request And Decision Mapping

One System One request sends the candidate and at most five retrieved memories as state. Candidate content and retrieved content are bounded before transmission. The request asks independent questions over the same state:

- `action` is a Choice over `create`, `update`, `merge`, `candidate`, `discard`, and `conflict`.
- `target` is a Choice over `none` and the retrieved memory IDs.
- One Noul per retrieved memory asks whether that memory belongs in a merge.

Each question includes its own complete premise because System One questions are evaluated independently. The question IDs are deterministic local identifiers; memory IDs remain in the Choice criteria and state.

The adapter enforces existing invariants after inference:

- A create decision with a candidate total below 12 becomes `candidate`.
- Update requires a retrieved target; otherwise it becomes `candidate`.
- Merge requires a retrieved primary target and at least one additional confirmed merge memory; otherwise it becomes `candidate`.
- Candidate, discard, and conflict never retain a target.
- Candidate scores remain the source of truth; Jev does not rescore them.
- Jev does not generate replacement memory content. Existing update behavior appends the candidate content.

The adapter creates a deterministic reason containing the selected action, confidence, target, and any downgrade. The audit payload additionally preserves the TypeSafe model ID, action probabilities, and confidence without storing credentials.

## Failures And Retries

Authentication, permission, and validation responses (`401`, `403`, `422`) are not retried. Rate-limit and overload responses (`429`, `529`) receive bounded exponential backoff and honor `Retry-After` when it is a valid short delay. Network errors, timeouts, malformed JSON, missing answers, and invalid answer shapes raise a sanitized application error and enter the fallback chain.

No error path writes to the real database during tests. Service-level behavior continues to use the existing transaction and candidate safeguards.

## Observability

Judge modes become `typesafe`, `ai`, and `local`. CLI output, `ProcessOutcome.cli_text`, `pipeline_report`, and the Web console identify Jev decisions separately. The pipeline report keeps individual counts for all three modes.

## Testing

All automated tests use mocked HTTP, temporary knowledge roots, and temporary SQLite databases. Coverage includes:

- HTTP endpoint, headers, request body, model selection, and credential redaction.
- Retry and non-retry status handling.
- Structured action, target, and merge mapping.
- Low-score create, missing target, and incomplete merge downgrades.
- TypeSafe to general AI to local fallback order.
- Audit metadata and three-mode CLI/Web reporting.
- The full existing `unittest` suite.

No automated test calls TypeSafe, starts the web server, or opens the established `data/dianjia.db`.

## Deferred Work

An MCP server, cross-project Jev tool, live threshold calibration, and replacing text-generating stages are outside this change. A live Jev acceptance query requires a separately configured API key and representative user-approved data after the offline implementation passes.
