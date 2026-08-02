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

## SHOULD

1. **AAA pattern**. SHOULD follow Arrange, Act, Assert structure for readability.
2. **Descriptive names**. `Describe`, `Context`, `It` (Pester) and test function names SHOULD describe the behavior under test, not the implementation.
3. **Mock at boundaries**. SHOULD mock external dependencies (HTTP, filesystem, shells); avoid mocking domain logic.
4. **Mirror obligation on contract changes**. SHOULD grep for tests asserting old contracts (signatures, return types, error shapes) and flip them in the same diff, per `.agents/governance/TESTING-RIGOR.md`.
5. **Isolate process-global state in a subprocess**. A regression guard that asserts on process-global state (`sys.path`, `sys.modules`, `os.environ`, `cwd`) SHOULD run in a clean subprocess when the property under test can be masked by another test module's import-time mutation. Sibling modules under `tests/` insert directories on `sys.path` at collection, so an in-process guard for the *absence* of such an entry passes for the wrong reason and stops catching the regression it was written for. Exemplar: the subprocess-isolated lazy-import guard in `tests/validation/test_pre_pr_model_pin_wiring.py` (#3073), whose earlier in-process form passed with the bug reinstated because sibling portability tests kept `scripts/validation` on `sys.path`.

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
