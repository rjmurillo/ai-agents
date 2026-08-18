# Governance Bureaucracy Critical Review (2026-08-17)

## Statement

87 of 92 open issues (94%) were the repo's own governance/CI/validation machinery breaking itself, not product-facing work. Ten root-cause clusters explained 40 of the 92 numbers. Six issues were genuinely urgent, verified by reading bodies directly: #5111 (P0, `/tmp` worktrees filled a 16G tmpfs, already halted work once), #5090 (`core.hooksPath` pointed at a nonexistent directory, silently disabling all 24 pre-push jobs, a *repeat* of a 2026-07-19 fix), #5099 (CVSS 8.8: the `/ship` gate verifies its config's byte-identity but not the verifier scripts it dispatches), #4607 (CI shares one rate-limit budget with every agent session), plus #5102 and #2993 which block pushes directly per their own titles.

## Evidence

Full findings, methodology, and citations: `.agents/retrospective/2026-08-17-governance-bureaucracy-critical-review.md`. Session log: `.agents/sessions/2026-08-17-session-99917-b41b3bf39-critical-review-open-issues-backlog.json`.

Two live gate bugs were found while shipping the review's own first fix (a 3-file rule-file dedup, `.claude/rules/generated-artifacts.md`):

1. `retrospective-policy`'s lefthook `{push_files}` template resolves empty on a branch's first push, which defeats its own documentation-only bypass and forces retrospective evidence for a pure docs change. Not yet filed as its own issue.
2. `validate_session_json.py`'s `serenaMemoryUpdated` MUST-item has no accommodation for Serena MCP being unavailable in a session (this one): `validate_must_item` requires literal `Complete: true` with no tool-unavailable exception, unlike `qaValidation`'s `SKIPPED: docs-only` / `SKIPPED: investigation-only` precedent. Worked around by writing this memory file directly per the `AGENTS.md` documented fallback (`.serena/memories/<name>.md`) instead of the MCP tool, which makes the Complete:true claim actually true rather than fabricated. Also not yet filed as its own issue.

## Decision

Closed 9 confirmed-safe-to-deprioritize issues (#5117, #5118, #5115, #5121, #5070, #5043, #4962, #5068, #5014). Flagged (not closed) PR #4846 (close_and_restart recommendation) and #4954 (needs_human_call) since both predate this session. Handed PR #5036 an exact fix. Flagged PR #5122 as already solving #5090, currently conflicted against main. Delegated issue #5060 to GitHub Copilot's coding agent (PR #5126) as a live throughput/quality test. Shipped the smallest, lowest-risk rule-file consolidation first; deferred the `SESSION-PROTOCOL.md` trim and always-on rule-file consolidation to a dedicated pass since both touch enforcement code or a byte-pinned test.
