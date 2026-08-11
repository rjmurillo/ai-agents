---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-4728-pr-autofix.json
qaCommit: 384e615fe404bee562b7274b856ec628283a30ad
---

# QA Report: Issue 4691 merge-group readiness

## Scope

Ten workflows gain a `merge_group:` trigger scoped to `main`, plus the
structural test that pins the contract. This validation also merges current
`main` twice, so the commit-count gate grants its documented 40-commit limit.
It verifies the review fixes for the required `Run Python Tests` producer,
act's Git exit-128 signature, and the action-specific anti-vacuity controls.

## Evidence

- CI root and review fixes: focused pytest command for seven affected suites,
  327 passed.
- Lint: scoped `ruff check` for all changed Python files, all checks passed.
- Retrospective lint: `npx --yes markdownlint-cli` on the retrospective,
  0 errors.

Total: 327 tests, 0 failures, measured at `384e615f`.

## Non-vacuity control

The readiness assertions were loaded against the `origin/main` workflow tree
extracted with `git archive origin/main .github/workflows`. They produced 27
errors, including `ai-pr-quality-gate.yml: missing merge_group trigger` and
`codeql-analysis.yml: missing shared event policy`. The contract therefore
fails against the unfixed tree, which is what issue #4691 asks for.

Fourteen parametrized structural negative controls cover the other direction.
They mutate required triggers, force events, bypass markers, each workflow's
validation action, `github.ref`, `push`, producers, contexts, reachability,
and the base-ref fallback. Each mutation must produce its matching error.

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
