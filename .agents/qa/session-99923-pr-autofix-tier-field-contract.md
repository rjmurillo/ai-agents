---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json
qaCommit: ee7db91b1a5f5c9d40a6f4235af9f0d1f173b108
---

# QA Report: session 99923, pr-autofix tier field contract

- Issue: #5094
- Session log: `.agents/sessions/2026-08-20-session-99923-f79e70c01-review-pr-5175-pr-autofix-tier-field-contract.json`
- QA commit: `ee7db91b1a5f5c9d40a6f4235af9f0d1f173b108`
- Branch: `claude/pr-5175-review-v21yk2`

## Verdict

PASS.

## Scope under test

One-line behavior change in `.claude/commands/pr-autofix.md` (tier read moved
from `.Data.Tier` to `.Tier`), its generated mirror in
`src/copilot-cli/skills/pr-autofix/SKILL.md`, and the new static gate at
`tests/commands/test_pr_autofix_field_contract.py`.

## Evidence

### Defect reproduced before the fix

`test_pr_merge_ready.py` declares no `--output-format` argument and emits its
payload with `print(json.dumps(result, indent=2))` at line 1226, building
`result` as a flat dict literal with `result["Tier"]` assigned at line 1091.
There is no `Data` envelope, so `jq -r '.Data.Tier // "UNKNOWN"'` resolved to
null on every call and `TIER` was unconditionally `UNKNOWN`. That disabled the
T3/T4 branch of the round-cap circuit breaker and the non-T1 branch of the
auto-merge disarm gate.

### Negative control

Reverted the fix in both the source command and the generated mirror, then
re-ran the suite. Three tests failed, naming the source contract, the mirror
contract, and the pinned tier regression:

```
FAILED test_source_command_has_no_contract_violations
FAILED test_copilot_mirror_has_no_contract_violations
FAILED test_tier_read_targets_the_authoritative_flat_producer
3 failed, 19 passed
```

Restored the fix; 22 passed. The gate therefore discriminates the fixed tree
from the unfixed one rather than passing unconditionally.

### Test results

| Command | Result |
|---|---|
| `uv run pytest tests/commands/test_pr_autofix_field_contract.py` | 22 passed |
| `uv run pytest tests/test_pr_autofix_late_live_state_gate.py tests/test_pr_autofix_force_push_lease.py tests/test_pr_autofix_worktree_identity.py tests/skills/pr-autofix/ tests/commands/` | 459 passed, 1 skipped |
| `uv run ruff check tests/commands/test_pr_autofix_field_contract.py` | All checks passed |
| `uv run python build/scripts/generate_commands.py` | 14 commands, 14 skills written; only the intended mirror changed |

### Coverage shape

Positive, negative, and edge cases are all present, per
`.agents/governance/TESTING-RIGOR.md`:

- Positive: source and mirror both clean; mirror reads equal source reads; the
  tier read is pinned to the authoritative producer and the envelope-free path.
- Negative controls: a `Data.` prefix on a flat producer, an unknown field on a
  flat producer, a missing `Data.` prefix on a wrapped producer, and the same
  defect reached through a captured shell variable. A fifth asserts that
  correct reads yield no findings, so a check that failed everything would not
  read as strict.
- Edge: backslash-continuation joining, first-physical-line reporting, comment
  lines excluded, and a read with no producer in scope reported as unbound.
- Coverage guard: `test_every_read_binds_to_a_producer` fails if the extractor
  stops binding a read, so the gate cannot silently go blind and pass.

### Audit of the remaining reads

All 16 jq reads in the command body bind to a producer, zero unbound. The other
15 were already correct: 13 `Data`-wrapped reads against `check_pr_live_state.py`,
`pr_autofix_lease.py`, `check_pr_round_cap.py`, and `get_pr_context.py`, plus a
flat `.merged` read against `test_pr_merged.py`.

## Gates not cleared here

`scripts/validation/pre_pr.py` reported two failures on the prior commit, both
addressed before this report: the taste-count ratchet regression (test file was
511 lines against the 500-line rule, now 490) and this session's own session-log
validation. Both are re-run at push time.
