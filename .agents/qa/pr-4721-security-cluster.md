---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-06-session-4654-security-cluster.json
qaCommit: d634d728acac084e9223977a6dd307df419aa5f2
---

# PR 4721 QA Report

## Verdict

PASS. Targeted validation passed on commit `d634d728acac084e9223977a6dd307df419aa5f2` before adding this QA evidence refresh.

## Evidence

- `uv run --frozen pytest tests/test_new_pr_cli.py tests/test_new_pr_validator_contracts.py -q`
- Result: 50 collected, 50 passed.
- `uv run --frozen python scripts/ci/subprocess_encoding_count_ratchet.py --base-ref 24e67c6796b69b4c65497f31d3d5146fe2597efb`
- Result: `subprocess encoding count ratchet: OK (count == baseline 253).`

## Scope

Covers the `new_pr.py` decode-policy fix in the Claude and Copilot copies plus the subprocess encoding regression guard that blocked CI.
