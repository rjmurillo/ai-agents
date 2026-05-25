---
type: requirement
id: REQ-013
title: M5 bot-cascade pre-push warning
status: draft
priority: P1
category: non-functional
related:
  - DESIGN-013
  - TASK-013
issues:
  - 1991
predecessor: REQ-012
retrospective: .agents/retrospective/2026-05-10-pr-1989-recursive-failure.md
author: Richard Murillo
created: 2026-05-10
updated: 2026-05-10
---

# REQ-013: M5 Bot-Cascade Pre-Push Warning

## Step 0 First Principles

### Q1 Demand Reality

Three requesters:

1. Richard Murillo (issue #1991 author and "separate /spec invocations for M1/M4/M5" directive, 2026-05-10).
2. `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md` (named M5 bot-cascade as the highest-leverage retro intervention, estimated 20 commits saved).
3. `.serena/memories/implementation/implementation-007-pr1989-recursive-failure-learnings.md` HIGH constraint: "Guards and warning tools must self-apply during development".

### Q2 Status Quo

Developer pushes commit. 4 bots (Copilot, Cursor, Devin, CodeRabbit) each scan independently. 5 to 15 new threads open within minutes. Developer fixes. Re-push triggers more bot scans. Cycle continues until convergence or PR is parked draft. PR #1989 hit 58 commits and 120 threads. PR #2004 hit 12 threads on first push despite TDD-first methodology. The hook to warn before re-push does not exist on main yet (PR #1989's M5 implementation was parked draft and never merged).

### Q3 Desperate Specificity

`.githooks/pre-push` Phase 5c (or new equivalent). Three specific implementation defects observed in PR #1989's M5 must be avoided:

- `gh api ... || true` swallowed auth failures and treated them as "no bot reviews"; produced false PASS.
- Missing "recent bot review under 120 seconds" branch (REQ-009-11 was added retroactively after coderabbit caught the gap).
- Trusted `unresolved_count` without first verifying `fetched_pages_complete == true`.

The PR that shipped M5 in PR #1989 triggered bot cascade on its own first push (5 bot threads), failing the self-application gate.

### Q4 Narrowest Wedge

Approximately 3.5 hours. Tier 1-2.

1. 30 minutes: contract test asserting `fetched_pages_complete == true` is required before trusting count (REQ-011-02).
2. 45 minutes: contract test asserting recent bot review under 120 seconds produces warning (REQ-011-03).
3. 45 minutes: contract test asserting auth failure does NOT swallow (REQ-011-04).
4. 1 hour: extend `.githooks/pre-push` with all three contracts (REQ-011-01..04).
5. 30 minutes: self-apply gate (run hook against this very branch before commit) (REQ-011-06).

### Q5 Observation

- PR #1989 M5 had 5 bot threads on first push (copilot, coderabbit, devin, cursor, gemini). Concrete count in retro.
- PR #1965 had 58 commits without M5. Concrete metric.
- PR #2004 had 12 threads on first push despite TDD-first methodology. Concrete count from session 2026-05-10.
- PR #1989 commit `cb1bdf19` retroactively added the `fetched_pages_complete` parse to address a related issue.
- `.serena/memories/implementation/implementation-007-pr1989-recursive-failure-learnings.md` documents the failure class.

### Q6 Future-fit

Hook scales linearly with PR volume. At 10x PR throughput, the bot-cascade cost compounds: more bot scans mean more cross-PR thread storms. Hook value increases. The only future-liability vector is per-bot threshold tuning, tracked as deferred.

## Prior Art and Constraints

### Direct prior art from memory

- `implementation-007-pr1989-recursive-failure-learnings`: HIGH "Guards must self-apply during development". HIGH "Verify CLI flag/argparse semantics against live output". Decision: honor both.
- `implementation-008-spec-schema-validation`: HIGH "Read spec-schemas.md before writing spec." Applied: this REQ uses validated enums (priority P1, category non-functional).
- `tools/github-skill-scripts-reference`: documents `get_unresolved_review_threads.py` as the canonical thread query. Decision: hook calls it via subprocess argv-vector.
- `quality/quality-shift-left-gate`: pre-push timing for quality gates. Decision: Phase 5c sits in pre-push.
- chestertons-fence: `.githooks/pre-push` on main has NO Phase 5c (M5 never landed via PR #1989). Clean test bed. PRESERVE existing Phases 1-5b; ADD Phase 5c.

### Connected context

- Connected entity: `get_unresolved_review_threads.py` (in-scope; query source for unresolved count).
- Connected entity: `gh api /pulls/{n}/reviews` endpoint (in-scope; bot review timestamp source).
- Connected entity: `fetched_pages_complete` flag (in-scope; trust gate per PR #1965 commit cb1bdf19).
- Connected entity: ADR-035 exit codes (in-scope; auth failures must propagate exit 4).
- Out-of-scope: rework_warning module (REQ-010, separate concern).
- Out-of-scope: Validate Generated Files job (CI, not pre-push).

### Coverage notes

- Pre-push memory: 5 hits across observations and quality indices. Confidence high.
- bot-cascade memory: 0 hits (new terminology); failure class is documented under `pr-review/` and retro paths.
- chestertons-fence: substituted with direct git archaeology on `.githooks/pre-push`.

## Acceptance Criteria

## REQ-011-01: Unresolved Threads Trigger Warning

### Requirement Statement

WHEN `.githooks/pre-push` runs on a branch with an open PR and `get_unresolved_review_threads.py` returns `unresolved_count > 0 AND fetched_pages_complete == true`, THE SYSTEM SHALL emit a warning line (NOT block) referencing the batch-fix pattern, SO THAT the developer can choose to wait before another scan triggers.

### Acceptance Criteria

- [ ] Phase 5c exists in `.githooks/pre-push` after Phase 5b.
- [ ] On `unresolved_count > 0`, the hook emits `record_warn` with the count.
- [ ] The hook NEVER calls `record_fail` for bot-cascade conditions (warn-only).
- [ ] Message references the batch-fix pattern from Session 14 of `pr-review-observations.md`.

### Rationale

Warns the developer before another bot scan triggers, reducing the chance of cascade.

---

## REQ-011-02: Untrustworthy Snapshot is SKIP, Not PASS

### Requirement Statement

WHEN the query returns `success == false` OR `fetched_pages_complete == false` OR the JSON parse fails OR `unresolved_count` is not a non-negative integer, THE SYSTEM SHALL record SKIP with an explicit reason naming the failed condition, SO THAT an untrustworthy snapshot does not produce a false PASS.

### Acceptance Criteria

- [x] Hook parses `success` and `fetched_pages_complete` from JSON output before reading `unresolved_count`; trust requires BOTH `true`.
- [x] On `success == false`, the hook emits `record_skip "Bot-cascade check (PR #N thread query returned success=false)"`.
- [x] On `fetched_pages_complete == false`, the hook emits `record_skip "Bot-cascade check (PR #N snapshot incomplete: fetched_pages_complete=false)"`.
- [x] On JSON parse failure or a non-int/bool/negative `unresolved_count`, the hook emits `record_skip "Bot-cascade check (PR #N JSON parse failed)"`.
- [x] No condition produces a false PASS or a warn.

### Rationale

PR #1989 commit `cb1bdf19` retroactively patched the related "trust without flag" issue. REQ-011 builds it in from the start. PR #2011 review extended the trust gate to require `success == true` in addition to `fetched_pages_complete == true`, and to reject `bool` (which subclasses `int` in Python) and negative values for `unresolved_count`.

---

## REQ-011-03: Recent Bot Review Produces Warning

### Requirement Statement

WHEN the query returns `unresolved_count == 0 AND fetched_pages_complete == true` AND `gh api /repos/{o}/{r}/pulls/{n}/reviews` returns a bot review submitted within the last 120 seconds, THE SYSTEM SHALL emit a warning line stating a bot scan is likely in flight, SO THAT the developer waits for settling.

### Acceptance Criteria

- [ ] Hook queries `gh api /repos/{o}/{r}/pulls/{n}/reviews` only when `unresolved_count == 0`.
- [ ] Hook filters reviews where `user.type == "Bot"` and computes age from `submitted_at`.
- [ ] On any age under 120 seconds, the hook emits `record_warn` with the age.
- [ ] On age 120 or older (or no bot reviews), the hook emits `record_pass`.
- [ ] 120-second threshold is documented inline with citation to PR #2004 session.

### Rationale

A developer who pushes immediately after a bot has STARTED but not finished its review will see zero current threads, but the in-flight scan will add threads moments later. The 120s window covers Copilot/Devin webhook latency observed during PR #1965 and PR #2004 (30 to 120 seconds).

---

## REQ-011-04: Auth Failures Do Not Swallow

### Requirement Statement

WHEN `gh api ... reviews` fails (auth error, network error, missing scope), THE SYSTEM SHALL record SKIP with explicit reason and exit code propagated, NOT a fall-through to PASS, SO THAT auth failures cannot mask in-flight reviews.

### Acceptance Criteria

- [x] Hook captures `gh api` exit code; non-zero produces SKIP, not PASS.
- [x] Hook does NOT use `|| true` or other fail-open patterns on the reviews query. (Phase 5c uses `|| echo '<sentinel>'` and routes the sentinel to `record_skip`; `test_phase_5c_no_fail_open_on_reviews` asserts `|| true` appears nowhere in the block.)
- [x] SKIP message names the failure mode. The hook greps captured stderr and classifies as "gh api auth failed" / "gh api rate-limited" / "gh api network error", falling back to "exit N".
- [x] If auth error, hook records SKIP with reason "gh api auth failed" (matched from stderr containing auth/unauthorized/401/403/bad credentials) but does NOT exit non-zero (hook is warn-only).

### Rationale

PR #1989 M5 had this exact bug with `gh api ... || true`. The corrected design rejects all fail-open patterns on this code path.

---

## REQ-011-05: Test Contract per AC

### Requirement Statement

WHEN `tests/hooks/test_bot_cascade_warning.py` runs, THE SYSTEM SHALL pin each of REQ-011-01..04 to one test case with AC traceability in the docstring, using structural verification of the Phase 5c block (string-presence plus `bash -n`).

### Acceptance Criteria

- [x] Test file exists at `tests/hooks/test_bot_cascade_warning.py`.
- [x] One test per AC: REQ-011-01 (unresolved warn), REQ-011-02 (incomplete skip), REQ-011-03 (recent review warn), REQ-011-04 (auth skip not swallow).
- [x] Each test docstring cites the AC identifier.
- [x] Tests use structural verification (grep on the Phase 5c block plus `bash -n`), the same pattern that covers Phase 5b drift detection.
- [x] One test asserts each of `record_skip`, `record_warn`, `record_pass` has at least one call site in Phase 5c.
- [x] Runtime evidence for each branch is captured outside the test suite as part of the TASK-011-04 self-apply gate (REQ-011-06).

### Rationale

TDD-first per updated `/build` command. Tests are written before code.

The original draft specified PATH-stubbed `gh` and python interpreters driving runtime assertions on `record_warn` / `record_skip` / `record_pass` lines. That approach is infeasible for a pre-push hook: invoking the hook end-to-end runs the full repo test suite (Phase 4) and takes ~3 minutes per case, and PATH-stubbing the gh and python binaries reliably across uv venvs and CI environments is fragile. The implemented suite uses the same structural pattern that already covers Phase 5b drift detection; runtime evidence for each outcome path is captured by the TASK-011-04 self-apply gate against the live PR.

---

## REQ-011-06: Self-Apply Gate

### Requirement Statement

WHEN the milestone PR's pre-push hook executes against its own branch before commit, THE SYSTEM SHALL emit at least one warning line if the branch has any unresolved threads (self-apply gate per `/build` step 6).

### Acceptance Criteria

- [ ] Before committing TASK-011-04, the implementer runs `.githooks/pre-push` against the current branch.
- [ ] Output captured in PR description.
- [ ] If unresolved threads exist on the PR, the hook MUST emit `record_warn` for them.

### Rationale

PR #1989's M5 implementation triggered the bot cascade on its own first push without firing the warning it was supposed to provide. REQ-011-06 prevents recurrence.

## User Stories

1. As a developer about to push to a PR branch, the pre-push hook warns me if my PR has unresolved bot threads, so I batch-fix before triggering another scan.
2. As a developer about to push within 120s of a bot review, the hook warns me a scan is likely in flight, so I wait instead of re-triggering.
3. As a developer pushing where `gh` auth has expired, the hook reports SKIP with reason, NOT a false PASS.

## Data Model

File-level only. No persistent state. Hook reads JSON from `get_unresolved_review_threads.py` stdout and timestamps from `gh api`.

## Integrations

- `.githooks/pre-push` (canonical hook surface).
- `get_unresolved_review_threads.py` (subprocess argv-vector call).
- `gh api /repos/{o}/{r}/pulls/{n}/reviews` (subprocess argv-vector call).
- pytest 8+ (test harness).

## Failure Modes

- Hook silently skips if no PR exists for the branch.
- Hook silently skips if `gh` is unavailable.
- Hook records SKIP if `fetched_pages_complete == false`.
- Hook records SKIP if `gh api ... reviews` fails (any non-zero exit).
- Hook NEVER calls `record_fail` (warn-only).

## Security

- argv-vector subprocess only (CWE-78).
- No shell concatenation of PR number or branch name.
- Auth failure does NOT fail-open (REQ-011-04).

## Observability

- All bot-cascade events emit single-line `record_*` to stderr.
- No new logging infrastructure.

## Out of Scope

- Per-bot timestamp tracking (track only last bot review across all bots). Deferred.
- Blocking behavior (warn-only by design).
- Cross-PR bot cascade detection (single PR only).
- Threshold tuning UI / configurability.

## Deferred

- Configurable `--bot-settle-seconds` flag. Future PR if 120s proves wrong empirically.
- Multi-bot timestamp aggregation. Future PR.

## Open Questions

None blocking.

## CVA Summary

N/A. Single use case (warn before push triggers another scan). Three conditions in series, not parallel abstractions.

## Complexity Tier

Tier 1-2. Approximately 3.5 hours total per Q4 wedge.
