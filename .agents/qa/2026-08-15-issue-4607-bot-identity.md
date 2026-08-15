---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-4607-bot-pat-identity.json
qaCommit: f6ec064112fb172e9d873c98b3680be6989cedd7
---

# QA Report: Bot identity diagnostic (Issue #4607)

Note: this report will be renamed to carry the PR number once the PR exists.

## Scope

Repo-side fix for issue #4607: CI and agent sessions share one GitHub API
budget because `BOT_PAT` resolves to the human account (id 6811113) instead of
`rjmurillo-bot` (id 250269933). The secret rotation is operator-only; this
change makes the identity visible and checkable from run logs.

## What changed

1. `scripts/ci/check_bot_identity.py`: stdlib-only diagnostic module. Probes
   `GET /user` with the supplied credential and reports one of four verdicts:
   MATCH, MISMATCH, MISSING, UNKNOWN. A failed probe is reported as UNKNOWN,
   never as a pass. `IDENTITY_STRICT` turns MISMATCH/MISSING/UNKNOWN into
   nonzero exits (4/2/3 per the repo exit-code contract).
2. `.github/actions/ai-review/action.yml`: unconditional `Report bot-pat
   identity` step. All 22 caller sites inherit it, so every AI review run log
   now names the resolved login and id.
3. `.github/workflows/pr-maintenance.yml`: same diagnostic in the
   `discover-prs` job (ADR-026 is the PR maintenance automation ADR).

## Test evidence

Command: `uv run --frozen pytest tests/ci/test_check_bot_identity.py tests/ci/test_bot_identity_wiring.py -q`

Result: 21 passed.

Coverage against the required cases:

| Required case | Test | Result |
|---|---|---|
| Identity matches expected id | `TestMatch::test_expected_bot_id_exits_zero_and_names_the_identity` | pass, exit 0 |
| Identity mismatch reported | `TestMismatch::test_wrong_account_warns_but_does_not_block_by_default` | pass, warning emitted |
| Mismatch blocking exits nonzero from main() | `TestMismatch::test_wrong_account_in_strict_mode_exits_nonzero_from_main` | pass, exit 4 |
| API probe failure is UNKNOWN, not a pass | `TestProbeFailure::test_failed_probe_is_unknown_never_a_match` (4 parametrized failures) | pass |
| Probe failure blocking exits nonzero from main() | `TestProbeFailure::test_failed_probe_in_strict_mode_exits_external` | pass, exit 3 |
| Missing token never probes, strict exit nonzero | `TestMissingToken` (2 tests) | pass, exit 2 strict |
| Token never printed | `TestMatch::test_match_never_prints_the_token` | pass |
| Wiring: step unconditional, non-strict, bound to bot-pat | `tests/ci/test_bot_identity_wiring.py` (3 tests, parsed YAML) | pass |

Static checks: `ruff check` clean, `ruff format` clean, `mypy` clean on the
module. `python3 -c "import scripts.ci.check_bot_identity"` succeeds with the
bare interpreter (the action step runs it with bare `python3`, so imports must
be stdlib-only).

## Acceptance criterion status

The issue's acceptance criterion is: inside CI, `gh api user --jq .id` under
`BOT_PAT` returns 250269933. This does NOT pass yet and cannot pass from the
repository side: the secret's value belongs to the human account and only the
repository owner can mint and store a replacement. What this change delivers
is that every ai-review and pr-maintenance run log now prints the resolved
identity, so the criterion is checkable from any run log: the new step reports
MISMATCH today and will report MATCH once the owner rotates the secret.

## Residual risk

- The diagnostic adds one `GET /user` request per ai-review invocation against
  the probed token's budget. Under exhaustion the probe itself returns 403 and
  is reported as UNKNOWN, non-blocking.
- Strict mode is deliberately off. Enabling `IDENTITY_STRICT` before the
  secret rotation would turn every AI review red. The wiring test pins the
  non-strict state with a comment explaining when to flip it.
