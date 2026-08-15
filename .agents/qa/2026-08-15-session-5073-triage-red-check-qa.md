---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5073-triage-main-first.json
qaCommit: 3f25c791819a046abd2a65033b8716dcb06fb74f
---

# QA report: triage_red_check.py (issue #5073)

PASS for commit 3f25c791819a046abd2a65033b8716dcb06fb74f on branch
claude/issue-5073-triage-main-first.

## What was validated

New script `.claude/skills/github/scripts/pr/triage_red_check.py` (mirrored to
`src/copilot-cli/skills/github/scripts/pr/`), its test suite
`tests/skills/github/test_triage_red_check.py`, and the doc wiring in
`.claude/commands/pr-autofix.md`, `.claude/skills/github/SKILL.md`, and
`.claude/skills/pr-comment-responder/references/gates.md` plus generated
Copilot mirrors.

## Evidence

- Targeted suite: `uv run pytest tests/skills/github/test_triage_red_check.py`
  passed 25/25. Coverage includes all three verdicts with exit codes asserted
  from `main()` (GREEN_ON_MAIN 0, RED_ON_MAIN 1, UNKNOWN 3), config failures
  (branch not found, history depth out of range: exit 2), API failure (exit 3),
  auth failure propagation (exit 4), and the recorded traps: SKIPPED sibling
  not masking SUCCESS, rerun attempt superseding a first-attempt FAILURE,
  job-name collision across workflows (red run wins, AmbiguousDefinitions
  true), red sibling winning within one run (issue #4499 shape),
  concurrency-cancelled runs treated as non-evidence, incomplete pagination
  reported UNKNOWN even with a green row visible, and StatusContext rows in
  both red and green directions.
- Full neighborhood: `uv run pytest tests/skills/github/` passed 510/510.
- Offline import guard: `uv run pytest tests/test_pr_scripts_offline.py`
  passed 5/5.
- Lint: `uv run ruff check` clean on the new script and test; mypy changed-file
  ratchet passed inside pre_pr.
- Taste ratchet: `taste count ratchet: OK (count == baseline 583)` after the
  reasoned file-size suppression (same pattern as the sibling
  `why_pr_blocked.py`).
- Live probe: running the script in this sandbox exercised the auth-failure
  path end to end (`gh` unauthenticated, exit 4 with the remediation
  message). A fully authenticated live run against origin/main was not
  possible in this environment; the GitHub API boundary is covered by the
  mocked GraphQL suite above, which drives the real `main()` entry point.

## Gaps and follow-ups

- The GraphQL boundary is mocked in tests; the query strings themselves follow
  the shape of the sibling `why_pr_blocked.py` queries, which run in
  production. First authenticated invocation should be observed on a real
  failing check.
