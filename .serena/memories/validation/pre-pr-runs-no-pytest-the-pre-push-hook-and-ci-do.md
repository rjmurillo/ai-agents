# pre_pr.py passes without running pytest, so a test failure appears at push or in CI

## What happens

`scripts/validation/pre_pr.py` and `pre_pr_sequence.py` run validators. Neither invokes pytest. A change can pass the pre-PR checks and still fail a test.

Pytest runs in two other places:

- The `python-tests` job in the pre-push group of `lefthook.yml` (line 774), which runs `git_hook_policy.py pytest` with a 15 minute cap. It uses `pytest --testmon`, which re-runs only tests whose recorded dependencies changed.
- The required `Run Python Tests` check in CI.

## The case that exposed it

Issue 7286: PR 7263 added one Markdown file. `pre_pr.py` exited 0. CI then failed `tests/test_forgetful_decommission_scope.py`, which scans the tree for a retired backend name. INFERRED from the title of PR 7296: the testmon data did not list a new Markdown file as an input, so the pre-push job skipped the test too.

PR 7296 (merged 2026-11-11, `d34536c95`) closed that gap. It changed `scripts/validation/testmon_data_inputs.py` so a changed Markdown file re-selects tree-scanning tests. It did not touch `pre_pr.py`, and 7286 asked for that file. `pre_pr.py` still runs no pytest.

## Practice

Do not read a clean `pre_pr.py` as a green test run. For a docs-only change that adds a new file, run the tree-scanning tests yourself:

```bash
uv run --frozen pytest tests/test_forgetful_decommission_scope.py
```

## Evidence

- OBSERVED 2026-11-11 on `origin/main` at `c4550d9ee`: searching `scripts/validation/pre_pr*.py` for pytest invocations found only comments (`pre_pr_sequence.py` lines 306, 389, 493, 497, 598).
- `lefthook.yml` lines 742 to 776.
- Issue 7286, closed as completed by PR 7296.

## Relations

- **related_to**: [decision-local-pass-does-not-clear-red-ci](../decision-local-pass-does-not-clear-red-ci.md)
