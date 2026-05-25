---
type: requirement
id: REQ-012
title: Retro fixes from PR #1965 (rework + contract drift)
status: draft
priority: P1
category: non-functional
related:
  - DESIGN-012
  - TASK-012
issues: []
retrospective: .agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md
author: Richard Murillo
created: 2026-05-10
updated: 2026-05-10
---

# REQ-012: Retro fixes from PR #1965 (rework + contract drift)

## Step 0 First Principles

### Q1 Demand Reality

Three requesters:

1. Richard Murillo (explicit ask 2026-05-10: "why did it take 58 commits and dozens of turns to land PR 1965?")
2. `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md` (lists three highest-leverage interventions)
3. `.serena/memories/pr-review/pr-review-observations.md` Session 15 entries (encoded the same gaps as HIGH-confidence learnings on 2026-05-10)

### Q2 Status Quo

1. Run `get_unresolved_review_threads.py` -- returns 0 at call time, but bots open new threads between calls so subsequent reads show 12 (mechanism corrected during /plan code-mapping; pagination itself is correct)
2. Declare PR done prematurely -- user reports "merging blocked"
3. Cross-check with `get_pr_review_threads.py` -- discovers true count
4. Add a verdict token to `verdict.py` -- bots find missing site in `action.yml` validity case -- fix -- bots find missing site in `$blockingVerdicts` -- fix -- bots find missing site in `exit_code` case -- fix (3 commits per token)
5. Edit axis prompt body -- bots find regex doc out of sync with `_EXTRACT_VERDICT_PATTERN` -- fix all 6 axes + 6 CI mirrors + 3 lib copies = 15-file cascade

### Q3 Desperate Specificity

Single blocked component: the `/pr-review` workflow on PR #1965 and any future PR using the same toolchain. Blocked on three concrete files plus the session-end skill:

- `.claude/skills/github/scripts/pr/get_unresolved_review_threads.py` (correct, but no stable-zero wrapper exists; bot-settle latency lets a momentarily-true zero mislead the next agent step)
- `.claude/rules/canonical-source-mirror.md` (`applyTo` glob excludes `.claude/review-axes/`)
- `.claude/commands/spec.md` (no `co-change-checklist` section template)
- `.claude/skills/session-end/` (no rework-warning surface)

### Q4 Narrowest Wedge

Four small fixes, approximately 5.5 hours total:

- Approximately 2h: stable-zero wrapper `wait_for_unresolved_zero.py` requiring two consecutive zeros >=60s apart (bot-settle latency)
- Approximately 30min: extend `applyTo` glob in `.claude/rules/canonical-source-mirror.md` to cover `.claude/review-axes/` and `.github/prompts/`
- Approximately 1h: add `co-change-checklist` section template to `.claude/commands/spec.md` for verdict-token-style atomic changes
- Approximately 2h: rework warning in session-end skill (detects files edited 6+ times in branch history)

### Q5 Observation

- 58 commits on PR #1965
- Retro at `.agents/retrospective/2026-05-10-pr-1965-review-axes-convergence.md` Five-Why root causes RCA-1, RCA-2, RCA-3
- Cursor Bugbot threads PRRT_kwDOQoWRls6A6hZB, 6yn7, 6s_k
- Copilot threads PRRT_kwDOQoWRls6A6zXW through 6zXm (6 axis files)
- Context-mode plugin signals: scan.py touched 56 times; 859 unresolved errors; 77 rejected Agent calls; P95 latency 109s; Productivity 6/100

### Q6 Future-fit

All four fixes scale linearly with PR volume; none becomes a liability at 10x growth.

---

## Prior Art / Constraints

### Direct prior art from memory

- ADR PR #1887 retrospective (`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`): coined "confident incorrectness" anti-pattern motivating canonical-source-mirror.md. Decision: extend rule, not amend.
- `.serena/memories/pr-review/pr-review-observations.md` Session 15 (2026-05-10): persists three failure modes as HIGH-confidence learnings. Decision: honor.
- `.serena/memories/github/github-observations.md`: prior GraphQL pagination guidance (Session 7 PR #908). Decision: honor; pagination contract test inherits this constraint.
- `.serena/memories/tools/github-skill-scripts-reference.md`: documents `get_unresolved_review_threads.py` as public skill script. Decision: honor; do not rename, do extend test contract.
- chestertons-fence recommendation: PRESERVE rule semantics; MODIFY applyTo glob only.

### Connected context from exploring-knowledge-graph

- ADR-035 exit codes (in-scope): pagination contract test must keep ADR-035 codes (0=ok, 1=logic, 2=config).
- PR #1887 retrospective (in-scope): same anti-pattern; wedge extends rule retro proposed.
- `.claude/rules/universal.md` (out-of-scope): only canonical-source-mirror rule's glob changes.
- Forgetful MCP (out-of-scope): fixes are local file edits + tests.
- Linked project: /spec pipeline; co-change-checklist plugs into Step 6 spec-generator handoff.
- Traversal depth: medium (Phases 1-4), Tier 3 ProvisionalTier.

### Coverage notes

- Topic `get-unresolved-review-threads.py`: 3 variants searched, 4 memory files matched. Confidence: high.
- Topic `canonical-source-mirror.md`: 3 variants, 1 hit. Confidence: low (rule is 4 days old).
- Topic `spec.md`: 3 variants, 1 hit. Confidence: low (recency).
- Topic `claude/review-axes/`: 1 implicit query. Confidence: low. Axis files are only canonical record.
- chestertons-fence skill: substituted with manual git archaeology. Acceptable degradation.
- exploring-knowledge-graph skill: substituted with grep traversal. Acceptable for Tier 3.

---

## REQ-012-01: Stable-Zero Check Wrapper

### Requirement Statement

WHEN `wait_for_unresolved_zero.py` is invoked with `--pull-request <N>`,
THE SYSTEM SHALL poll `get_unresolved_review_threads.py` and exit 0 only after observing THREE consecutive readings of `unresolved_count == 0 AND fetched_pages_complete == true` separated by at least 180 seconds,
SO THAT bots opening new threads between checks cannot produce a false-positive "done" verdict.

### Acceptance Criteria

- [ ] A new wrapper script exists at `.claude/skills/github/scripts/pr/wait_for_unresolved_zero.py`.
- [ ] The wrapper accepts `--pull-request`, `--owner`, `--repo`, `--interval-seconds` (default 180), `--max-wait-seconds` (default 1200), `--strict-pagination` (default True; disable with `--no-strict-pagination` per BooleanOptionalAction).
- [ ] The wrapper exits 0 only when THREE consecutive observations satisfy `unresolved_count == 0 AND fetched_pages_complete == true` AND the interval between them is at least `--interval-seconds`.
- [ ] The wrapper exits 1 when `--max-wait-seconds` elapses before three zero-readings are observed.
- [ ] Exit codes follow ADR-035 (0 ok, 1 logic, 2 config, 4 auth) AND propagate from the underlying script (auth 4 from underlying maps to main returning 4; config 2 maps to 2).
- [ ] Output is JSON with `{success, pull_request, observations: [{timestamp, unresolved_count, fetched_pages_complete, underlying_exit_code}, ...], settled: bool, reason: str|null}`.

### Revision History

PR #1989 critic NEEDS-REVISION raised default interval from 60s to 180s and required readings from 2 to 3. Pre-mortem found Copilot/Devin webhook latency commonly exceeds 60s; two consecutive zeros 60s apart could miss a slow bot scan and re-introduce the PR #1965 lie.

### Rationale

Pagination already works in the underlying script (commit `00151b78` added `fetched_pages_complete` and the completion gate already requires it). The PR #1965 "0 unresolved" lie was caused by bots opening new threads between agent queries, NOT by undercount. A stable-zero wrapper closes the bot-settle latency gap by requiring two consistent readings across a settled interval.

### Dependencies

`get_unresolved_review_threads.py` (already paginates correctly).

---

## REQ-012-02: Stable-Zero Check Test (Bot-Settle Detection)

### Requirement Statement

WHEN `tests/skills/github/test_wait_for_unresolved_zero.py` runs against a stubbed sequence where reading 1 returns `unresolved_count=0` and reading 2 (180s later) returns `unresolved_count=3` (bots opened threads between calls),
THE SYSTEM SHALL assert the wrapper does NOT exit 0 prematurely; it must observe THREE consecutive zeros before settling.

### Acceptance Criteria

- [ ] A test file exists at `tests/skills/github/test_wait_for_unresolved_zero.py`.
- [ ] The test stubs `get_unresolved_review_threads.py` invocations via `subprocess.run` patching.
- [ ] The test stubs a sequence `[0, 3, 0, 0, 0]`: reading 1 returns 0, reading 2 returns 3 (bots opened threads), readings 3-5 return 0; the wrapper must NOT exit 0 until reading 5.
- [ ] A second test stubs `fetched_pages_complete=false` on the first zero reading; the wrapper must NOT count that as a valid zero observation.
- [ ] A third test verifies max-wait-seconds timeout exits 1 with `settled=false` in JSON output.
- [ ] Tests cover the `--strict-pagination` / `--no-strict-pagination` BooleanOptionalAction flag with default-True, explicit-True, and explicit-False positive cases.
- [ ] Tests cover exit-code propagation: underlying exit 4 -> main returns 4; exit 2 -> main returns 2; exit 0 with no-settle -> main returns 1.
- [ ] Tests cover `_invoke_underlying` error degradation: FileNotFoundError, TimeoutExpired, OSError, malformed JSON, malformed payload shape.
- [ ] All HTTP interactions are stubbed (no live network).

### Rationale

A test that only verifies "two zeros pass" misses the failure mode: bots opening threads between checks. Pinning the bot-settle scenario explicitly guards against re-introducing the PR #1965 lie. Pinning the `fetched_pages_complete=false` rejection guards against accepting incomplete pagination as a valid zero.

### Dependencies

REQ-012-01 (wrapper script must exist).

---

## REQ-012-03: canonical-source-mirror.md applyTo Glob Coverage

### Requirement Statement

WHEN `tests/build_scripts/test_canonical_source_mirror.py` parses `.claude/rules/canonical-source-mirror.md` frontmatter,
THE SYSTEM SHALL assert the `applyTo` glob matches both `.claude/review-axes/analyst.md` and `.github/prompts/pr-quality-gate-analyst.md`,
SO THAT prompt files embedding contracts fall under the rule.

### Acceptance Criteria

- [ ] `.claude/rules/canonical-source-mirror.md` frontmatter contains an `applyTo` field.
- [ ] The `applyTo` glob (or list of globs) matches the path `.claude/review-axes/analyst.md` when evaluated with Python's `fnmatch` or `pathlib.Path.match`.
- [ ] The `applyTo` glob also matches `.github/prompts/pr-quality-gate-analyst.md`.
- [ ] The rule's prose (sections, rationale, anti-patterns) is unchanged; only the `applyTo` field is modified.
- [ ] A test at `tests/build_scripts/test_canonical_source_mirror.py` parses the frontmatter and asserts both paths match; the test fails if the glob is removed or narrowed.

### Rationale

The existing `applyTo` glob excluded `.claude/review-axes/` and `.github/prompts/`, meaning PR #1965's axis file edits were not flagged for canonical-source-mirror compliance. Extending the glob closes the coverage gap without touching rule semantics (chestertons-fence: PRESERVE semantics, MODIFY scope only).

### Dependencies

None.

---

## REQ-012-04: co-change-checklist Section Template in /spec

### Requirement Statement

WHEN a contributor runs `/spec` and answers "yes" to a Step 6 prompt "is this a multi-site contract change?",
THE SYSTEM SHALL emit a `## Co-change checklist` section in the generated `REQ-NNN-{slug}.md` listing every site the contract appears (file path + line reference if known),
SO THAT the implementer addresses all sites in one commit.

### Acceptance Criteria

- [ ] `.claude/commands/spec.md` contains a Step 6 section with a conditional prompt: "Is this a multi-site contract change? (y/n)".
- [ ] When the answer is "yes", the generated requirement file includes a `## Co-change checklist` section.
- [ ] The section header is exactly `## Co-change checklist` (case-sensitive, level-2 heading).
- [ ] The section appears after the last `### Acceptance Criteria` subsection and before `### Rationale`.
- [ ] The user is prompted to list each site before the template is rendered.

### Rationale

Every verdict-token addition during PR #1965 required 3 commits because the implementer discovered missing sites one at a time through bot review. A pre-flight checklist in the spec forces discovery at spec time, not review time.

### Dependencies

None. `.claude/commands/spec.md` is a standalone file.

---

## REQ-012-05: co-change-checklist Placeholder Format

### Requirement Statement

WHEN `co-change-checklist` is emitted,
THE SYSTEM SHALL include a placeholder line `- [ ] {file_path}:{line_or_section} -- {what changes}` for each site,
SO THAT the section is mechanically reviewable as a checklist.

### Acceptance Criteria

- [ ] Each checklist entry follows the exact format: `- [ ] {file_path}:{line_or_section} -- {what changes}`.
- [ ] `{file_path}` is a repo-relative path (no leading `/`).
- [ ] `{line_or_section}` is either a line number (integer) or a section name (string) when a precise line is unknown.
- [ ] `{what changes}` is a single phrase describing the required edit, not a full sentence.
- [ ] The section renders as a GitHub-flavored markdown checklist (task list).

### Rationale

The format is machine-parseable for future linting and human-reviewable as a completion checklist. The `-- ` separator is distinct from existing markdown list conventions in this repo.

### Dependencies

REQ-012-04 (same template).

---

## REQ-012-06: CI Gate Enforcement

### Requirement Statement

WHEN any of REQ-012-01 through REQ-012-09 fails,
THE SYSTEM SHALL block PR merge via the existing "Run Python Tests" required check,
SO THAT the fixes do not silently regress.

### Acceptance Criteria

- [ ] All new test files live under `tests/` per AGENTS.md placement rules.
- [ ] New tests are discoverable by `pytest` without additional configuration flags.
- [ ] The "Run Python Tests" CI job is already a required check; no workflow changes are needed.
- [ ] Running `python3 scripts/validation/pre_pr.py` locally surfaces test failures before push.

### Rationale

The existing required check provides the enforcement gate. No new CI infrastructure is required; placement under `tests/` is sufficient.

### Dependencies

REQ-012-01, REQ-012-02, REQ-012-03, REQ-012-09 (test files must exist and be pytest-discoverable).

---

## REQ-012-07: Rework Warning in session-end (Positive Case)

### Requirement Statement

WHEN the session-end skill runs against a branch with at least one file edited 6+ times in the branch's commit history,
THE SYSTEM SHALL emit a warning line listing each such file with its edit count,
SO THAT rework loops surface before PR submission.

### Acceptance Criteria

- [ ] The session-end skill invokes a rework-warning check as part of its standard execution.
- [ ] The check queries `git log --name-only` or equivalent for the current branch vs. the base branch.
- [ ] Any file appearing in 6 or more commits is included in the warning output.
- [ ] The warning output format per file is: `rework-warning: {file_path} edited {n} times`.
- [ ] The warning is emitted to stdout and also appended to the session log under a `## Rework Warning` section.
- [ ] The check does not error if the working tree has no commits ahead of the base branch; it emits `rework-warning: none` in that case.

### Rationale

PR #1965 had scan.py touched 56 times. No tooling surfaced this rework signal before submission. A per-file edit-count warning at session-end would have prompted the engineer to investigate the root cause before filing the PR.

### Dependencies

session-end skill must exist at `.claude/skills/session-end/`.

---

## REQ-012-08: Rework Warning in session-end (Negative Case)

### Requirement Statement

WHEN the session-end skill runs against a branch where no file was edited 6+ times,
THE SYSTEM SHALL emit a single line `rework-warning: none` (not silence),
SO THAT the absence of a warning is evidence the check ran rather than ambiguous.

### Acceptance Criteria

- [ ] When no file exceeds the threshold, the output is exactly `rework-warning: none` (no other rework-warning lines).
- [ ] The session log `## Rework Warning` section contains `rework-warning: none` in this case.
- [ ] The check does not suppress output when threshold is not reached; silence is never acceptable.

### Rationale

A check that produces no output on the happy path is indistinguishable from a check that did not run. Explicit `none` output provides positive confirmation the check executed.

### Dependencies

REQ-012-07 (same implementation).

---

## REQ-012-09: Rework Warning Contract Test

### Requirement Statement

WHEN `tests/skills/session-end/test_rework_warning.py` runs against a stubbed git log with one file at 6 commits and one at 3 commits,
THE SYSTEM SHALL assert the 6-edit file appears in the warning and the 3-edit file does not,
SO THAT the threshold is pinned.

### Acceptance Criteria

- [ ] A test file exists at `tests/skills/session-end/test_rework_warning.py`.
- [ ] The test stubs `git log` output with two files: one at 6 commits, one at 3 commits.
- [ ] The test asserts the 6-commit file appears in the warning output.
- [ ] The test asserts the 3-commit file does not appear in the warning output.
- [ ] The test asserts that output format matches `rework-warning: {file_path} edited {n} times`.
- [ ] The test passes without live git access; all git calls are stubbed or use a temp repository fixture.

### Rationale

Without a pinned threshold test, a future edit could silently lower the threshold to 5 or raise it to 10. The contract test prevents silent drift.

### Dependencies

REQ-012-07 (implementation must exist before the test can be written).

---

## REQ-012-10: Bot-Cascade Pre-Push Warning

### Requirement Statement

WHEN `.githooks/pre-push` Phase 5c runs for a branch with an open PR that has unresolved bot review threads,
THE SYSTEM SHALL emit a warning (but NOT block the push) referencing the batch-fix pattern,
SO THAT the developer can choose to wait for threads to resolve before triggering another bot scan.

### Acceptance Criteria

- [ ] Phase 5c exists in `.githooks/pre-push` and runs after the existing review-axes drift check.
- [ ] When the current branch has a PR with `unresolved_count > 0`, the hook emits `record_warn` with the count.
- [ ] The hook NEVER calls `record_fail` for bot-cascade conditions (warn-only).
- [ ] When `gh` is not available, the hook records skip and exits cleanly.
- [ ] When the current branch has no PR, the hook records skip and exits cleanly.

### Rationale

PR #1965 retrospective names bot-cascade as the highest-leverage gap (~20 commits saved). Pushing with open bot threads triggers a new bot scan, which often opens more threads. A warn-only signal at push time gives the developer a clear choice before that cycle starts.

### Dependencies

`get_unresolved_review_threads.py` (already paginates correctly). `gh` CLI authenticated against the repo.

---

## REQ-012-11: Bot-Cascade Recent-Review Warning

### Requirement Statement

WHEN `.githooks/pre-push` Phase 5c runs for a branch with an open PR that has zero unresolved threads BUT the last bot review was submitted less than 120 seconds ago,
THE SYSTEM SHALL emit a warning (but NOT block the push) indicating a bot scan is likely still in flight,
SO THAT the developer waits for the in-flight scan to complete instead of triggering a new one on top.

### Acceptance Criteria

- [ ] When `unresolved_count == 0` AND last bot review timestamp is < 120s old, Phase 5c emits `record_warn`.
- [ ] When `unresolved_count == 0` AND last bot review timestamp is >= 120s old, Phase 5c emits `record_pass` with the observed age.
- [ ] When `unresolved_count == 0` AND no bot reviews exist for the PR, Phase 5c emits `record_pass`.
- [ ] The 120-second threshold is documented inline in the hook with citation to PR #1989 coderabbit finding.
- [ ] Timestamp parsing degrades to 99999 (treated as old) on malformed input.

### Rationale

PR #1989 coderabbit finding: a developer who pushes immediately after a bot has STARTED but not finished its review will see zero current threads, but the in-flight scan will add threads moments later. The 120s window covers Copilot/Devin webhook latency observed during PR #1965 (30-120s).

### Dependencies

REQ-012-10 (the Phase 5c block must already exist). `gh api` access to the `/pulls/{n}/reviews` endpoint.

---

## User Stories

1. As a reviewer, I want `get_unresolved_review_threads.py` to return all open threads regardless of PR size, so that I do not declare a PR resolved while threads remain open.
2. As a maintainer, I want the canonical-source-mirror rule to cover `.claude/review-axes/` and `.github/prompts/`, so that prompt files embedding contracts are governed by the same citation discipline.
3. As a spec author, I want `/spec` to prompt me for a co-change checklist when I indicate a multi-site contract change, so that all affected sites are listed in the requirement before implementation begins.
4. As an engineer closing a session, I want the session-end skill to warn me when any file was edited 6+ times on the branch, so that I can investigate the rework loop before filing a PR.

---

## Data Model

File-level only. No persistent state beyond session log appends and rule file edits.

---

## Integrations

- pytest 8+ (test runner for contract tests)
- GitHub GraphQL API stub (pagination test)
- `/spec` skill (co-change-checklist template)
- session-end skill (rework warning)

---

## Failure Modes

- Pagination test stubs API; no live network required.
- `applyTo` glob test parses YAML frontmatter; fails with a clear assertion error if glob is missing or wrong.
- co-change-checklist absent when user answers "no" -- template is not emitted (backward compatible).
- Rework warning check errors on missing git binary; check must degrade gracefully with `rework-warning: git unavailable`.

---

## Security

No shell construction from user input. No path resolution change. No secrets involved.

---

## Observability

pytest output (existing CI gate). No new metrics, logs, or traces.

---

## Out of Scope

- Refactoring `get_unresolved_review_threads.py` itself (test only)
- Auto-detecting multi-site contract changes without user input
- Migrating existing axis files to new glob coverage
- Agent tool call rejection logging
- Error budget gating in CI
- P95 latency profiling

---

## Deferred

- Pagination contract tests for sibling scripts
- co-change-checklist linter (post-generation validation)
- Rework threshold tuning (currently hardcoded at 6)
- Per-extension thresholds
- **Class 3 spec (tool/schema hallucination):** separate /spec invocation owns this failure class. Examples observed 2026-05-10: agent invoked `get_unresolved_threads.py` (script does not exist; correct name `get_unresolved_review_threads.py`) AND assumed `Data` JSON wrapper (only `get_pr_context.py` emits that shape). Same root cause class as context-mode "77 rejected Agent calls" and "56 edits to scan.py". Likely M6-style fix is a pre-tool-use script-name fuzzy-match guard plus a JSON-shape registry. Tracked here so REQ-009 does not accidentally absorb it.

---

## Open Questions

None blocking.

---

## CVA Summary

N/A (single-use-case Tier 2).

---

## Complexity Tier

Tier 2 (Mid). 5.5h total.
