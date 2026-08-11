---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14654.json
qaCommit: 29cc49504f3a0e36d6cad674305ecafe002750e5
---

# QA Report: Issue 4691 merge-group readiness

## Scope

Ten workflows gain a `merge_group:` trigger scoped to `main`, plus the
structural test that pins the contract. The branch was rebased onto
`origin/main` and re-measured after the rebase, not before it.

## Evidence

| Check | Command | Result |
|---|---|---|
| Readiness contract | `pytest tests/ci/test_merge_group_readiness.py` | 11 passed |
| Trigger fan-out | `pytest tests/ci/test_workflow_trigger_fanout.py` | 69 passed |
| Frontmatter path filter | `pytest tests/ci/test_frontmatter_gate_paths_filter.py` | 4 passed |
| Shared event policy | `pytest tests/workflows/test_determine_should_run_from_filters.py` | 26 passed |
| Local workflow gate | `pytest tests/validation/test_run_workflow_local_test.py` | 143 passed |
| Lint | `ruff check` on the two changed Python files | All checks passed |
| Workflow lint | pre-commit `actionlint` and `workflow-validation` | Passed |

Total: 253 tests, 0 failures, measured at `29cc4950`.

## Non-vacuity control

The readiness assertions were loaded against the `origin/main` workflow tree
extracted with `git archive origin/main .github/workflows`. They produced 27
errors, including `ai-pr-quality-gate.yml: missing merge_group trigger` and
`codeql-analysis.yml: missing shared event policy`. The contract therefore
fails against the unfixed tree, which is what issue #4691 asks for.

Ten parametrized structural negative controls cover the other direction: each
mutates one workflow (drop the trigger, drop the force event, drop the bypass
marker, erase the real work, drop `github.ref`, bare `push`, remove a producer,
duplicate a context, make a producer unreachable, drop the base-ref fallback)
and asserts the matching error appears.

## Required-context inventory

Queried live on 2026-08-10:

```bash
gh api repos/rjmurillo/ai-agents/rulesets/11104075 --jq \
  '.rules[] | select(.type=="required_status_checks")
   | .parameters.required_status_checks[].context'
```

Sixteen contexts, not the seventeen the issue recorded. `Aggregate Results`
has been retired from the ruleset. All sixteen map to a job in ten workflows,
so `ai-session-protocol.yml` and `test-codeql-integration.yml` produce none of
them and keep their `main` content.

## Not verified here

Queue behavior itself. Ruleset `11104075` carries no `merge_queue` rule and
`GET /repos/rjmurillo/ai-agents` still reports `owner.type = User`, so no real
merge group can be created to observe. Issue #4774 owns that step and its
acceptance criteria already require a live queue entry.

`test-codeql-integration.yml` is unchanged on this branch, so the
`workflow-local-run` pre-push gate no longer has to execute it. That gate
cannot execute it: the workflow installs a 788,113,376-byte CodeQL bundle with
`--force` and budgets 15 to 20 CI minutes per job, against a 600-second
per-job local budget.
