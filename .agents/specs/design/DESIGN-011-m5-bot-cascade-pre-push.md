---
type: design
id: DESIGN-011
title: M5 bot-cascade pre-push warning
status: draft
priority: P1
related:
  - REQ-011
  - TASK-011
author: Richard Murillo
created: 2026-05-10
updated: 2026-05-10
---

# DESIGN-011: M5 Bot-Cascade Pre-Push Warning

## Requirements Addressed

REQ-011 (all six acceptance criteria REQ-011-01 through REQ-011-06).

## Architecture

`.githooks/pre-push` Phase 5c. Single hook phase added after Phase 5b. Calls two subprocess commands serially, parses JSON, emits one of `record_warn`, `record_skip`, or `record_pass`. Warn-only; never invokes `record_fail`.

### Call sequence

```
Phase 5c entry
  -> if gh unavailable: record_skip "gh not available"; return
  -> gh pr view --json number  (or skill equivalent)
     -> if no PR: record_skip "no PR for branch"; return
  -> python3 .claude/skills/github/scripts/pr/get_unresolved_review_threads.py --pull-request <N>
     -> parse JSON
     -> if fetched_pages_complete == false: record_skip "snapshot incomplete"; return
     -> if JSON parse fails: record_skip "JSON parse failed"; return
     -> if unresolved_count > 0:
          record_warn "PR #N has K unresolved thread(s)"   # not bot-filtered; see Issue #2012
          return
  -> gh api /repos/{owner}/{repo}/pulls/<N>/reviews
     -> if exit != 0: record_skip "gh api reviews failed (exit code)"; return
     -> filter user.type == "Bot", compute max(submitted_at age)
     -> if age < 120s: record_warn "bot scan likely in flight (Ks)"
     -> else: record_pass
```

## Component Map

| AC | Code Location | Behavior |
|----|---------------|----------|
| REQ-011-01 | Phase 5c block in `.githooks/pre-push` | `record_warn` on `unresolved_count > 0` |
| REQ-011-02 | Phase 5c JSON parser | `record_skip` on `fetched_pages_complete == false` or parse fail |
| REQ-011-03 | Phase 5c `gh api ... reviews` parser | `record_warn` on bot review age < 120s |
| REQ-011-04 | Phase 5c reviews call | `record_skip` on non-zero exit from `gh api`; no `|| true` |
| REQ-011-05 | `tests/hooks/test_bot_cascade_warning.py` | one test per AC |
| REQ-011-06 | Implementer runs hook against own branch before TASK-011-04 commit | output in PR description |

## Test Strategy

### Approach: structural verification (revised)

Phase 5c is a thin bash delegate: it parses two subprocess outputs and emits one of three recorder calls (`record_skip`, `record_warn`, `record_pass`). PATH-stubbing `gh` and `python3` to drive a runtime fixture suite was the original plan but proved unsuitable for a pre-push hook: invoking the hook end-to-end runs the full repository test suite (Phase 4) and takes about 3 minutes per test case, which is unacceptable for unit-test latency, and stubbing `gh` reliably across CI and developer machines (where PATH ordering and uv-venv `python3` differ) is fragile.

The implemented suite uses the same structural verification pattern that already covers Phase 5b drift detection (`tests/hooks/test_drift_check.py`): grep the hook text inside the Phase 5c block, plus `bash -n` for syntax. One additional test asserts that each REQ-011 outcome path has at least one call site (`record_skip`, `record_warn`, `record_pass` all appear). Combined, these pin the AC contract without paying the runtime cost.

Runtime evidence for the actual outcome lines is captured by exercising the hook against the current branch as part of the TASK-011-04 self-apply gate (REQ-011-06). Each of the four documented runtime paths has been exercised against a real PR; the captured output is in the PR description rather than in the test suite.

### Test cases per AC (implemented)

The tests in `tests/hooks/test_bot_cascade_warning.py` pin the Phase 5c contract by scoping every assertion to the regex `# Phase 5c.*?(?=# Phase \d|\Z)` so Phase 5b assertions cannot pollute Phase 5c assertions. The exact test count is intentionally not pinned here; it grows as the contract evolves.

- `test_phase_5c_header_present` (REQ-011-01): Phase 5c block exists and follows Phase 5b (asserts both positions are non-negative).
- `test_phase_5c_calls_unresolved_threads_script` (REQ-011-01): hook invokes `get_unresolved_review_threads.py`.
- `test_phase_5c_parses_fetched_pages_complete` (REQ-011-02): hook checks `fetched_pages_complete`.
- `test_phase_5c_emits_warn_on_unresolved` (REQ-011-01): hook contains `record_warn` and references `unresolved`.
- `test_phase_5c_emits_skip_on_incomplete` (REQ-011-02): hook contains `record_skip` for incomplete snapshot.
- `test_phase_5c_queries_reviews_endpoint` (REQ-011-03): hook queries `/reviews`.
- `test_phase_5c_filters_bot_reviews` (REQ-011-03): hook filters `user.type == "Bot"`.
- `test_phase_5c_120_second_threshold` (REQ-011-03): hook references the 120-second threshold.
- `test_phase_5c_no_fail_open_on_reviews` (REQ-011-04): no `|| true` on the reviews query.
- `test_phase_5c_warn_only_never_fails` (REQ-011-01..04): no `record_fail` call site (comments stripped before matching).
- `test_pre_push_hook_bash_syntax_valid`: `bash -n` on the whole hook.
- `test_phase_5c_emits_recorded_outcome_token` (REQ-011-05): each of `record_skip`, `record_warn`, `record_pass` has at least one call site in Phase 5c.

### Runtime evidence captured outside the test suite

The full self-apply gate (TASK-011-04) exercises the hook end-to-end against the live PR. Four paths captured to date:

1. `SKIP: Bot-cascade check (no PR open for branch)` (pre-PR push).
2. `PASS: Bot-cascade check (PR #2011, 0 unresolved, no bot reviews)` (post-PR-open, pre-bot-scan).
3. `WARNING: PR #2011 has 16 unresolved thread(s)` (post-bot-scan).
4. `WARNING: PR #N last bot review is Ks old (< 120s)` (next push after a bot review lands within the threshold).

## Trade-offs Considered

### Trade-off 1: warn-only versus block

- Block: stronger signal. But: pre-push hooks should never block on transient conditions (network failures, auth, etc.). The user can always bypass with `--no-verify`. Phase 5c follows the same phase-integration pattern as Phase 5b (a numbered `echo_phase` block calling `record_pass`/`record_skip`), but is intentionally non-blocking: unlike Phase 5b (which calls `record_fail` and sets `EXIT_STATUS=1` on drift), Phase 5c never calls `record_fail`. The bot-cascade signal is informational, not a gate.
- Decision: warn-only.

### Trade-off 2: 120-second threshold

- Empirical observation: Copilot/Devin webhook latencies during PR #1965 and PR #2004 were 30 to 120 seconds.
- Tighter threshold (60s): could miss slow bot starts.
- Looser threshold (300s): false positives on normal pushes.
- Decision: 120s. Document inline. Tracked as deferred-tunable.

### Trade-off 3: per-bot tracking versus single max

- Per-bot: detect specific bots not yet scanned.
- Max (current): one timestamp suffices.
- Decision: max. Simpler. Defer per-bot.

## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `gh api` rate limit hits during hook execution | LOW | Single call per push; well under rate limit |
| 120s threshold wrong empirically | MED | Deferred tunable; revisit after 30 invocations |
| Hook adds noticeable latency to push | LOW | Two subprocess calls, no polling; typical 200-500ms |
| Self-application gate (REQ-011-06) fails | MED | TASK-011-04 runs `.githooks/pre-push` against the milestone branch before commit; each runtime outcome path (skip/warn/pass) is captured in the PR description. The structural tests pin the contract; the self-apply gate exercises the live runtime. |

## References

- REQ-011 (full acceptance criteria with rationale)
- PR #1989 M5 implementation (parked draft, never merged)
- PR #1965 retrospective (bot-cascade documented as highest-leverage)
- `.serena/memories/implementation/implementation-007-pr1989-recursive-failure-learnings.md`
