# Code-quality changed-only gate is regression scoped

Source: issues #4364 triage on 2026-08-05 against origin/main 5ec85be51a and branch fix/4261-4364-encoding-debt-scope.

Current behavior: `.claude/skills/code-qualities-assessment/scripts/assess.py` uses `check_regressions()` when both `--changed-only` and `--base` are supplied. Existing files below the absolute threshold do not fail if their scores did not drop. Score drops return exit 10. New files absent from the base fall through to absolute thresholds and can return exit 11.

Evidence:

- Comment-only change to a legacy file with cohesion 1.0 returned exit 0.
- Synthetic score drop returned exit 10 with `Cohesion regressed 8.7 -> 1.0`.
- Focused tests: `uv run --frozen pytest tests/test_assess_regression.py .claude/skills/code-qualities-assessment/tests/test_assess.py tests/validation/test_check_subprocess_encoding.py -q` returned 103 passed.
- Mutation proof killed changed-only absolute fallback and suppressed exit-10 mutants, while a cosmetic docstring mutant survived.

Decision: Treat issue #4364's original absolute-debt claim as stale on current main. Keep tests that pin the live contract because this behavior is review-gate policy.
