---
applyTo: tests/**,**/*.Tests.ps1,**/tests/**,.claude/skills/**/tests/**,.agents/security/benchmarks/**,.claude/rules/testing.md
---

# Test File Rules

Tests under `tests/`, skill `tests/` directories, and `.agents/security/benchmarks/` enforce correctness and catch regressions. They are not decoration.

## MUST

1. **Structural validation**. Quality-gate prompt tests MUST comply with ADR-023 structural requirements. Other tests follow the placement and coverage rules below.
2. **Pester version**. PowerShell tests MUST target Pester 5.7.1+. Python tests MUST target pytest 8+.
3. **Evidence for fixture changes**. MUST NOT modify baseline fixtures to make failing tests pass. A baseline change MUST cite the behavior change that justifies it.
4. **Coverage targets**. Coverage MUST meet category minimums (`AGENTS.md`): 100% security, 80% business, 60% docs.
5. **Independent tests**. Each test MUST pass in isolation. Shared mutable state is prohibited.
6. **Placement**. New tests MUST live in the canonical locations: `tests/`, `.claude/skills/<name>/tests/`, or `.agents/security/benchmarks/`.
6. **Prove the wiring, not only the guard**. A shared guard, gate, or validator that several call sites depend on SHOULD have a test per consumer that drives the consumer's real entry point and fails when that consumer stops calling the guard. Unit tests on the guard prove the guard; they cannot prove any call site reached it, so a guard can pass every one of its own tests while a consumer is not wired to it at all. Drive the consumer twice over the same input, differing only in the condition the guard rejects, so a consumer that fails for an unrelated reason fails its own control too. Exemplars: `tests/validation/test_pre_pr_model_pin_wiring.py` (#3073) and `tests/validation/test_rule_activation_coverage_wiring.py`. Evidence: the baseline-diffability guard written for issue #4244 passed nine mutations against its own tests while one of its three consumers was never wired to it, and only a per-consumer test found that. The sweep is recorded in the Evidence section of PR #4233, which is where the guard and its wiring tests landed.
7. **Prove a guard fires before the effect it guards, not merely that it raised**. A negative test SHOULD end with an isolating assertion that the guarded side effect never happened, because `pytest.raises` alone passes when the code performs the effect and then raises. Exemplar: `test_copilot_complete_rejects_assistant_role` in `tests/eval/test_providers.py` closes with `assert "argv" not in seen`, which fails if the provider shells out before validating; the `pytest.raises` block above it passes either way.

## MUST NOT

1. MUST NOT rename a test to silence a failure.
2. MUST NOT add `Skip` or `@pytest.mark.skip` without a linked issue tracking re-enablement.
3. MUST NOT suppress protocol validation in tests (investigation exemption is narrow; see ADR-034).
4. MUST NOT leave files in the repository working tree. Durable fixtures go in `.pytest_tmp/`, which `.gitignore` covers and `validate_plugin_manifests.py` prunes; ephemeral scratch goes through `tempfile`. A test that deliberately exercises a repo-local `TMPDIR` may use `.pytest_cache/` (see `tests/test_pytest_repo_local_temp_roots.py`). Near-miss spellings such as `.pytest-tmp` are neither ignored nor pruned. Fix at the write target, not with `monkeypatch.chdir`.

## References

- `.agents/architecture/ADR-023-quality-gate-prompt-testing.md`. Structural contract.
- `.agents/architecture/ADR-034-investigation-session-qa-exemption.md`. Narrow skip policy.
- `.agents/steering/testing-approach.md`. Pester patterns and anti-patterns.
- `.agents/governance/TESTING-ANTI-PATTERNS.md`. Forbidden patterns.
