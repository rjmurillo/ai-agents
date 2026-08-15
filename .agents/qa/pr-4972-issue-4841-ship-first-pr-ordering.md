---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14705.json
qaCommit: f38e33061aff7d36208b548f78629076e3b39ed8
---

# PR 4972 Ship First-PR Ordering QA

## Scope

Validate the `/ship` pre-flight reordering and review-comment fixes across
`.claude/commands/ship.md`, its generated Copilot mirror
`src/copilot-cli/skills/ship/SKILL.md`, and the contract test
`tests/commands/test_ship_first_pr_ordering.py`.

## Acceptance Criteria

Quoted from issue 4841, "Expected": "For GitHub owner mode with no PR, run local
readiness checks, create the PR, then validate its CI checks. Existing GitHub PRs can
keep preflight pipeline validation."

- [x] GitHub owner mode with no open PR records `Pipeline: DEFERRED` at pre-flight
  check 1 and never invokes `pipeline-validator` there.
- [x] The same run still executes pre-flight checks 2 to 4 (security, review marker,
  tests) as the local readiness checks, then reaches `/push-pr`.
- [x] Process step 4 validates CI through `get_pr_checks.py` (GitHub-aware) against the
  PR `/push-pr` created and fails the ship on a red result.
- [x] A GitHub run with an open PR keeps `pipeline-validator` in pre-flight, unchanged.
- [x] Contributor mode and the ADO branch are unchanged.
- [x] The Copilot mirror carries the same ordering.

## Review Comment Fixes (commit 17db94d)

Three copilot-pull-request-reviewer comments addressed in `17db94d3c`:

| Thread | Issue | Fix | Test |
|--------|-------|-----|------|
| PRRT_kwDOQoWRls6ZAEZi (line 54) | `gh pr view` non-zero exit conflates no-PR with auth/network errors | Fact (b) now requires distinguishing the documented no-PR stderr message; other non-zero exits stop with an error | `TestPrDetectionDistinguishesErrors` |
| PRRT_kwDOQoWRls6ZAEaB (line 123) | Process step 4 invoked ADO-only pipeline-validator for GitHub discharge | Discharge routes through `get_pr_checks.py --wait` for GitHub | `test_discharge_uses_github_aware_ci_check` |
| PRRT_kwDOQoWRls6ZAEaS (line 64) | Hardcoded `.claude/skills/pipeline-validator/SKILL.md` path violates plugin-self-containment | Generic reference used instead | `test_no_pr_bullet_quotes_the_canonical_validator_contract` updated |

## Evidence

| Check | Result |
|-------|--------|
| Targeted contract tests | 28 passed (`tests/commands/test_ship_first_pr_ordering.py`), up from 24 (4 new tests for review fixes) |
| Pre-fix control (same tests, `origin/main` ship documents at `ab9c636de5`) | 16 of 24 failed; the 8 that passed are the ADO sibling, contributor-mode, and inline pre-fix control checks |
| Generated-tree drift | `build_all.py` regenerated mirror; no manual edits to generated files |
| Command size | 1 file, 0 failures, 1 warning: `ship.md` 156 lines against a 200-line ceiling and a 150-line warning |

## Canonical Source Check

The pipeline-validator skill Step 1 contract (read this session):

```text
- **No PR found:** Report to user. A PR must exist before pipeline validation. The calling skill should have created one.
```

`ship.md` quotes that sentence verbatim without naming a tree-specific path, and
`test_no_pr_bullet_quotes_the_canonical_validator_contract` re-reads the skill at test
time, so a reworded validator contract fails the suite instead of leaving a stale quote.

## Testing Quality Checklist

- [x] Security-critical paths: none touched. The change reorders workflow prose; it adds
  no secret handling, input parsing, command execution, or path construction.
- [x] Tests verify behavior, not execution: each assertion targets one branch of the
  ordering, and the pre-fix control demonstrates that 16 of them fail on the old text.
- [x] Coverage gaps only in low-risk code: the ADO and contributor branches are asserted
  as unchanged rather than left unread.
- [x] No coverage theater: the two inverse failures (deferring when a PR exists, and
  deferring without discharging) each have a dedicated test.

## Verdict

PASS. The first-PR deadlock is removed for GitHub owner mode without weakening pipeline
validation for any other path. All three review comments addressed with tests.
