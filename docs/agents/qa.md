# qa agent

The `qa` agent verifies that an implementation works for real users, not only that tests pass. It designs test strategies, checks coverage against acceptance criteria, and hands back a test report with evidence and a verdict.

## When to use it

- You want a test strategy before implementation.
- You want a verification report after implementation.
- You want regression testing, edge-case coverage, or user-scenario validation.
- You want a pre-PR quality gate with a verdict of `APPROVED`, `CONDITIONAL`, or `BLOCKED`.

## When not to use it

- You want the tests or fixes written: use [`implementer`](implementer.md) instead. The `qa` agent cannot change implementation code.
- You want test coverage gaps ranked on a PR: use [`pr-test-analyzer`](pr-test-analyzer.md) instead.
- You want a run of the proof gates as a workflow: use the [`test`](../skills/test.md) skill instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
qa: verify the dry-run feature for close_pr.py against the acceptance criteria in issue 7102
```

In GitHub Copilot CLI:

```bash
copilot --agent qa --prompt "verify the dry-run feature for close_pr.py against the acceptance criteria in issue 7102"
```

In VS Code or Visual Studio Copilot Chat:

```text
@qa verify the dry-run feature for close_pr.py against the acceptance criteria in issue 7102
```

## What you get

Documents in `.project-toolkit/qa/`:

| File | When |
| --- | --- |
| `NNN-[feature]-test-strategy.md` | Before implementation |
| `NNN-[feature]-test-report.md` | After implementation |
| `pre-pr-validation-[feature].md` | The pre-PR gate |

Every report has quantified metrics: line coverage, branch coverage, pass rate, flaky test count, and execution time. Results use `[PASS]`, `[FAIL]`, `[SKIP]`, and `[FLAKY]`.

A verdict is backed by a reconciliation block directly above the status line:

```text
Promised: [list from issue/delegation]
Delivered: [list from workspace]
Gap: [missing items, if any]
Result: PASS | FAIL
```

If the agent cannot find what was promised, it stops and reports "Cannot verify completeness without requirements."

The final status is `QA COMPLETE` or `QA FAILED`. `QA COMPLETE` requires that passed equals total, total is above 0, and no suite is `NOT RUN` or `UNAVAILABLE`. Otherwise the agent reports `[BLOCKED] Cannot evaluate: <suite>` or `QA FAILED`.

## Advanced use

The agent works in fresh context. It has not seen the implementer's reasoning and does not ask the implementer for clarification. Missing context is a finding. It does not invent findings to hit a count. When a full inspection finds nothing, it says what it checked and issues a PASS.

Before it designs a test it answers three questions: what behavior the test verifies, what the negative cases are, and what the minimum test is that proves correctness. It runs the coverage tool in the session before it claims any coverage number.

Pre-PR gate steps:

1. CI-equivalent test run.
2. Fail-safe pattern check: input validation, error handling, timeouts, and fallbacks.
3. Test-to-implementation alignment against acceptance criteria.
4. Coverage thresholds.
5. PR description validation.

The agent takes test and coverage commands from the repository's own documented commands, manifest, or CI configuration. It never invents one. If it cannot find one, it reports `UNRESOLVED EVIDENCE` and leaves the gate unmet.

| Condition | Verdict |
| --- | --- |
| All gates pass, line coverage 80 percent or more, branch coverage 70 percent or more, new-code coverage 80 percent or more | `APPROVED` |
| Line coverage 70 to 79 percent or branch coverage 60 to 69 percent, with no other gate failing | `CONDITIONAL` (name the gap and flag it to the owner) |
| Any gate fails, or line coverage under 70 percent, branch under 60 percent, or new-code under 70 percent | `BLOCKED` (name the gate and the number) |
| Coverage tool, CI environment, or gate evidence is missing | `BLOCKED` with the missing artifact |

It flags a test as `[FAIL]` when the test passes without running the code under test, such as regex checks on script content, a file-existence check alone, or unmocked external dependencies. Code quality gates: methods up to 60 lines, cyclomatic complexity of 10 or less, nesting depth of 3 or less, and at least 80 percent coverage on new code.

Risk-based effort: high-risk areas target 100 percent coverage with integration tests, medium-risk 80 percent, and low-risk 60 percent.

Optional references live in the `test` skill's `references/` folder: `qa-impact-analysis.md` and `qa-test-quality-patterns.md`. In impact analysis mode, when `milestone-planner` asks, it saves `.project-toolkit/planning/impact-analysis-qa-[feature].md`.

Handoffs: failures go to `implementer`, inadequate test infrastructure goes to `milestone-planner`, and a pass goes to the orchestrator for business validation. The agent cannot delegate.

A multi-step prompt:

```text
qa: run the pre-PR gate for the dry-run feature, paste the coverage tool output line, fill the Promised/Delivered/Gap block, and write pre-pr-validation-dry-run.md with a verdict.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`implementer`](implementer.md): fixes failures and gaps.
- [`pr-test-analyzer`](pr-test-analyzer.md): ranks test gaps on a PR.
- [`milestone-planner`](milestone-planner.md): revises plans when test infrastructure is inadequate.
- [`test`](../skills/test.md): runs the proof gates this agent's references serve.
- [`validate-pr-description`](../skills/validate-pr-description.md): validates PR metadata.
- Source template: [`qa.shared.md`](../../templates/agents/qa.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
