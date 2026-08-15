---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-15072-issue-5072-completion-gate-trust.json
qaCommit: b4cb52ce788b202d30ba05d18a05b552363759ff
---

# QA Report: PR #5089 completion-gate config trust boundary (Issue #5072)

## Scope

CWE-829 fix in `.claude/skills/github/scripts/pr/run_completion_gate.py`: the dispatcher must not execute `completion_criteria.command` from a working-tree `pr-review-config.yaml` that is not byte-identical to the trusted-ref copy, unless a human explicitly approves via `--approve-untrusted-config`.

## Evidence

### Unit and integration tests

Command: `uv run pytest tests/skills/github/test_run_completion_gate.py -q`

Result: 97 passed (76 pre-existing dispatcher tests unchanged, 21 new). The new tests drive `main()` end to end against real git repositories with no subprocess stubbing.

Acceptance-criteria mapping:

| Issue #5072 criterion | Test | Result |
|---|---|---|
| Tampered config halts, command NOT executed (negative control) | `test_tampered_config_halts_without_executing_command`: marker file the malicious command would create is asserted absent after exit 2 | PASS |
| Identical config proceeds | `test_identical_config_proceeds_and_executes`: exit 0, criterion executed, `config_trust.status == "trusted"` in JSON payload | PASS |
| Missing base copy halts | `test_config_missing_from_trusted_ref_halts`: exit 2, no execution | PASS |
| Whitespace-only change halts (byte identity) | `test_whitespace_only_change_halts`: trailing newline alone halts with exit 2 | PASS |
| Explicit human approval proceeds loudly | `test_approval_flag_executes_diverged_config_with_warning`, `test_approval_flag_covers_missing_base`: WARNING on stderr, `approved: true` in payload | PASS |
| Verification impossible fails closed | `test_trusted_ref_absent_fails_closed`, `test_not_a_git_repo_fails_closed`: exit 3, no execution | PASS |
| Argument-injection guard | `test_malformed_trusted_ref_rejected_before_git_runs`: `--trusted-ref=--upload-pack=/bin/true` rejected with exit 2 before any git call | PASS |
| Custom trusted ref honored | `test_custom_trusted_ref_is_honored` | PASS |

### Coverage (security-critical 100 percent requirement)

Command: `uv run pytest tests/skills/github/test_run_completion_gate.py -q --cov=run_completion_gate --cov-report=term-missing`

Every line of the new trust code (`TrustCheck`, `_run_git`, `_verify_config_trust`, `_enforce_config_trust`, `_extract_criteria`, CLI wiring) is covered; `TestVerifyConfigTrustErrorBranches` fault-injects git timeout, missing git binary, config outside the work tree, `git show` failure, and unreadable config. The only uncovered lines in the file are pre-existing branches (installed-plugin `validate_safe_path` fallback, PyYAML-missing fallback, DSL error branches, evidence-write errors, `__main__` guard), unchanged by this PR.

### Static and security gates

- `uv run ruff check` on changed files: clean
- security-scan skill (`scan_vulnerabilities.py`) on both dispatcher copies: no findings
- Mypy changed-files ratchet: green (new code fully annotated)
- Taste count ratchet: OK, count == baseline 583 (no new complexity or size violations)
- `uv run python scripts/validation/pre_pr.py`: RESULT: All validations passed

### Full suite

Pre-push `python-tests` job (`git_hook_policy.py pytest`): 28851 passed after the three environment fixes documented in the PR body; push of `b4cb52ce788b202d30ba05d18a05b552363759ff` passed the complete pre-push hook suite.

## Verdict

VERDICT: PASS
