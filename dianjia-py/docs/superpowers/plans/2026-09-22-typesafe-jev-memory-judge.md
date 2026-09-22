# TypeSafe Jev Memory Judge Implementation Plan

**Goal:** Add an opt-in TypeSafe Jev judge for candidate memory actions without changing Dianjia's established service, database, or default AI behavior.

**Architecture:** A standard-library `SystemOneClient` owns the remote HTTP contract. A `JevMemoryJudge` owns Dianjia-specific state, questions, and `MemoryDecision` mapping. `MemoryService` selects the optional judge and preserves the existing AI and local fallbacks.

**Environment invariants:** Do not edit the real `.env`, call the live TypeSafe API, start or restart the web service, or open `data/dianjia.db` in tests. Use temporary databases and mocked network calls only.

## Task 1: Install The Official Project Skill

- Install `typesafe-ai/skills`, path `skills/typesafe-ai`, into `dianjia/.agents/skills` with the Codex skill installer helper.
- Verify `SKILL.md` and `LICENSE` are present and no unrelated repository files were copied.

## Task 2: Define The TypeSafe HTTP Contract

- Add failing unit tests for endpoint construction, authorization header, default model, response parsing, retryable statuses, non-retryable statuses, invalid JSON, and sanitized errors.
- Implement `app/ai/typesafe.py` with no third-party dependencies.
- Keep retry timing injectable so tests never sleep.

## Task 3: Define Jev Memory Decisions

- Add failing unit tests for action/target/merge question construction and response mapping.
- Implement `app/memory_judge.py` with bounded state content and deterministic question definitions.
- Preserve candidate total score, clear targets for non-mutating actions, and downgrade unsafe create/update/merge outcomes to `candidate`.
- Return separate audit metadata containing the actual model, action probabilities, and confidence.

## Task 4: Integrate The Fallback Chain

- Add failing service tests for the default unchanged path and `typesafe -> ai -> local` fallback order.
- Select TypeSafe only when `DIANJIA_MEMORY_JUDGE=typesafe`.
- Extend judge modes and counts to `typesafe`, `ai`, and `local`.
- Add the TypeSafe metadata to the existing audit payload without storing secrets.

## Task 5: Update CLI, Web, And Configuration Documentation

- Extend `ProcessOutcome.cli_text` and the Web console labels for Jev Judge.
- Add commented TypeSafe variables to `.env.example`; do not edit `.env`.
- Document setup, opt-in behavior, fallback order, and the distinction between Jev decisions and text generation in `README.md`.

## Task 6: Verify Offline

- Run focused TypeSafe client and judge tests.
- Run `python3 -m unittest discover -s tests -v` against temporary test data.
- Run syntax compilation and `git diff --check`.
- Confirm no process, port, database, or `.env` changes occurred.
- Review the final diff for credentials, accidental generated files, and unrelated edits.
