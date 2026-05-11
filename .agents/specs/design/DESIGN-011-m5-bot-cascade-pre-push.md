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
          record_warn "PR #N has K unresolved bot threads"
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

### Test fixtures

Stub `gh` and `python3 .../get_unresolved_review_threads.py` calls via shell environment. Use a wrapper script in `tests/hooks/fixtures/` that the test invokes the hook with on its PATH. The hook executes the wrapper instead of the real `gh` binary; the wrapper emits the expected fixture output.

### Test cases per AC

- `test_unresolved_threads_emits_warn`: stub returns `{"unresolved_count": 3, "fetched_pages_complete": true}`. Hook emits `record_warn` with count 3.
- `test_incomplete_pagination_emits_skip`: stub returns `{"unresolved_count": 0, "fetched_pages_complete": false}`. Hook emits `record_skip` with reason.
- `test_json_parse_failure_emits_skip`: stub returns malformed JSON. Hook emits `record_skip` with reason.
- `test_recent_bot_review_emits_warn`: unresolved=0, complete=true; `gh api` returns one bot review at 60s ago. Hook emits `record_warn` with age.
- `test_old_bot_review_emits_pass`: unresolved=0, complete=true; `gh api` returns bot review at 300s ago. Hook emits `record_pass`.
- `test_no_bot_reviews_emits_pass`: unresolved=0, complete=true; `gh api` returns empty bot list. Hook emits `record_pass`.
- `test_gh_api_auth_failure_emits_skip`: `gh api ... reviews` exits 4. Hook emits `record_skip` with reason, NOT pass.
- `test_no_pr_emits_skip`: branch has no PR. Hook emits `record_skip` with reason.

## Trade-offs Considered

### Trade-off 1: warn-only versus block

- Block: stronger signal. But: pre-push hooks should never block on transient conditions (network failures, auth, etc.). The user can always bypass with `--no-verify`. Warn-only matches the existing Phase 5b drift check behavior.
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
| Self-application gate (REQ-011-06) fails | MED | TDD red phase ensures the warn paths are exercised before commit |

## References

- REQ-011 (full acceptance criteria with rationale)
- PR #1989 M5 implementation (parked draft, never merged)
- PR #1965 retrospective (bot-cascade documented as highest-leverage)
- `.serena/memories/implementation/implementation-007-pr1989-recursive-failure-learnings.md`
