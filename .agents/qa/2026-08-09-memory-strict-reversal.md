---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-09-session-10022-memory-strict-reversal.json
qaCommit: ca9de6e2f555cfc9254543595b2c21b80a8c870b
---

# Memory strict reversal QA

## Scope

Validated the memory correction for the 2026-08-09 strict policy reversal.

## Evidence

- `gh api repos/rjmurillo/ai-agents/rules/branches/main --jq '[.[] | select(.type=="required_status_checks") | .parameters.strict_required_status_checks_policy]'` returned `[false]`.
- `grep -rn "strict_required_status_checks_policy" --include=*.md . | grep -v "^./.git"` was reviewed. Current-value carriers were updated. Dated historical measurements were left intact.
- Workflow scan found 63 workflow files, 0 draft guard hits, and 18 required checks in the branch ruleset.
- `uv run --frozen python scripts/update_memory_index_tokens.py` updated generated token counts.
- `uv run --frozen python scripts/validation/memory_index.py --path .serena/memories --ci --orphan-policy ratchet` exited 0.
- `uv run --frozen python scripts/ci/memory_index_count_ratchet.py --base-ref origin/main` exited 0.
- `uv run --frozen python scripts/ci/memory_index_token_ratchet.py` exited 0.

## Result

PASS. The live strict policy value is recorded as false, and the memory keeps the 2026-08-05 true interval as dated history.
