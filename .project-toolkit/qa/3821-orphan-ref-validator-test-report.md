# Test Report: #3821 orphan-ref-validator platform-neutral invocation wording

## Objective

Verify that `orphan-ref-validator` no longer claims a platform-specific invocation syntax is platform-agnostic.

- **Feature**: Issue #3821
- **Scope**: `.claude/skills/orphan-ref-validator/SKILL.md`, generated Copilot CLI mirror, and Copilot translation contract tests
- **Acceptance Criteria**: Reproduce the false prose claim, replace it with platform-neutral wording, regenerate the mirror, and cover the regression with a test

## Approach

- Added a regression test that checks both the canonical skill and Copilot mirror for platform-neutral wording.
- Ran the new test before the fix and confirmed it failed for the expected missing wording.
- Replaced the syntax-specific claim in the canonical skill.
- Regenerated `src/copilot-cli/skills/orphan-ref-validator/SKILL.md` from the canonical source.
- Ran targeted and broader validation commands.

## Results

### Summary

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| New regression test red run | 1 failed | 1 expected failure | [PASS] |
| Targeted build-script tests | 49/49 passed | 0 failures | [PASS] |
| Ruff checks | 3 paths passed | 0 findings | [PASS] |
| Skill size validation | 2/2 passed, 2 warnings | 0 failures | [PASS] |
| Full pytest | Timed out after 600s at 43% | Complete suite | [SKIP] |

### Evidence

| Command | Result |
|---------|--------|
| `uv run pytest tests/build_scripts/test_generate_commands_copilot_contract.py::test_orphan_ref_validator_uses_platform_neutral_invocation_wording -q` before fix | [PASS] Failed as expected on missing platform-neutral wording |
| `python3 build/scripts/generate_skills.py --config templates/platforms/copilot-cli.yaml --repo-root .` | [PASS] 96 skills processed, 608 files written |
| `uv run pytest tests/build_scripts/test_generate_commands_copilot_contract.py tests/build_scripts/test_generate_skills.py -q` | [PASS] 49 passed in 7.11s |
| `uv run ruff check tests/build_scripts/test_generate_commands_copilot_contract.py build/scripts/copilot_body_translation.py build/scripts/generate_skills.py` | [PASS] All checks passed |
| `uv run python scripts/validation/skill_size.py --changed-files .claude/skills/orphan-ref-validator/SKILL.md src/copilot-cli/skills/orphan-ref-validator/SKILL.md` | [PASS] Both files within limits. Existing 334-line size warnings only |
| `uv run pytest tests/ -q` | [SKIP] Timed out after 600s at 43% without observed failures before timeout |

## Coverage Gaps

| Gap | Reason | Priority |
|-----|--------|----------|
| Full test suite did not complete locally | 16,051-test suite exceeded the 600s foreground command cap | P2 |

## Verdict

**Status**: PASS
**Confidence**: High
**Rationale**: The regression test failed before the change, passes after the fix, and the generated mirror now preserves the same platform-neutral meaning.
