---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-10022-pr-4643-postmerge-qa.json
qaCommit: c654d22c57a37ef9c4ea1c55d0ff73cba7b36f55
---

# QA Report: PR #4643 post-merge validation

## Scope

Validate the resolved PR #4643 tree after conflict-resolution cleared DIRTY.

- PR: #4643
- Branch: `audit/merged-campaign-behavior-20260805012235`
- Code commit under test: `c654d22c57a37ef9c4ea1c55d0ff73cba7b36f55`
- Base commit observed before QA: `2120a3298fae14c61af00673473590e77056a756`
- Failure being addressed: required `Validate PR` failed because no QA report existed.

## Diff inspected

The resolved diff changes CI audit and binding scripts: `_main_binding`, CLI exit contract coverage, drift summary output, subprocess encoding validation, unreachable-after-terminator validation, and their regression tests.

## Evidence

| Command | Result |
|---------|--------|
| `uv run --frozen pytest -q -p no:randomly tests/ci/test_agent_drift_scripts.py tests/ci/test_cli_exit_contract_ratchet.py tests/ci/test_main_binding_shapes.py tests/test_merged_audit_regressions.py` | 96 passed in 11.08s |

## Result

PASS. The smallest relevant suite for the changed code passed on the current resolved tree at `c654d22c57a37ef9c4ea1c55d0ff73cba7b36f55`.
