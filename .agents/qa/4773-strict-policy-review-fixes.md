---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10021-pr-4773-strict-policy-threads.json
qaCommit: d443ec4d8d11ce09f4af5a644ad734800fd688bf
---

# PR 4773 strict policy review fixes QA

## Scope

Validated the PR 4773 review-thread fixes for strict status check policy guidance.

## Evidence

- `gh api repos/rjmurillo/ai-agents/rules/branches/main --jq '[.[] | select(.type=="required_status_checks") | .parameters.strict_required_status_checks_policy]'` returned `[true]`.
- `grep -rln merge_group .github/workflows/` returned no matches.
- `grep -rn "strict_required_status_checks_policy" --include=*.md . | grep -v "^./.git"` showed the six live guidance carriers corrected or explicitly historical.
- `uv run --frozen python scripts/update_memory_index_tokens.py` updated memory token counts.
- `uv run --frozen python scripts/validation/memory_index.py --path .serena/memories --ci --orphan-policy ratchet` exited 0.
- `uv run --frozen python scripts/ci/memory_index_count_ratchet.py --base-ref origin/main` exited 0.
- `uv run --frozen python scripts/ci/memory_index_token_ratchet.py` exited 0.
- `uv run --frozen python scripts/validate_session_json.py .agents/sessions/2026-08-08-session-10021-pr-4773-strict-policy-threads.json --creation-mode` exited 0.
- `gh issue view 3755 --json state,closedAt` returned `CLOSED`, closed `2026-08-05T04:55:46Z`. Its body names `strict_required_status_checks_policy = False` on ruleset 11104075 as the structural cause, so the strict flip is that issue's shipped remedy rather than unrelated drift.
- `grep -rln merge_group .github/workflows/` returned no matches, confirming the merge_queue half of the GOTCHAS claim still holds.
- `uv run --frozen python scripts/validate_session_json.py .agents/sessions/2026-08-08-session-10021-pr-4773-strict-policy-threads.json` exited 0 after the appended work log entries.

## Follow-up correction

The first pass at the GOTCHAS edit left the sentence "neither remedy proposed
there has shipped, so `strict_required_status_checks_policy` is true", which
asserts a cause that does not hold and, once #3755 was checked, was also
factually wrong: the remedy did ship and the issue is closed. Corrected to
state that strict `true` closes the merge race for a behind-main branch, and
that what remains uncovered is the absent `merge_queue` rule, which is why the
exact-equality baseline assertion is still the gate that catches a count and a
baseline arriving out of step.

## Result

PASS. The changed guidance matches the live ruleset and the memory index validates.
