# PR 4865: contract tests that graded nothing

## Summary

Two tests shipped in PR 4865 asserted a string literal that their own fixture had just constructed. Both passed. Neither could fail for the reason it existed. A bot reviewer caught them; the local suite, the QA report, and the six-surface parity checks all reported green.

## Failure mode

Class 4, False completion markers (`.agents/governance/FAILURE-MODES.md`). The green test was the completion marker. It marked an acceptance criterion satisfied while measuring nothing about that criterion.

## Evidence

- PR: <https://github.com/rjmurillo/ai-agents/pull/4865>
- Issue: <https://github.com/rjmurillo/ai-agents/issues/4851>, acceptance criteria "add a fixture where phases 1 and 2 are complete and phase 3 is active" and "add a synthesis fixture that proves both prompts respect the same output bounds"
- Offending code, commit `9e75924ed`, `tests/test_orchestrator_shared_contracts.py`:

```python
assert "implementer phase is active" in active_phase_scenario.prompt
```

  The fixture two functions above sets `prompt` to a literal containing that substring. `ActivePhaseScenario.expected_outcome` was declared and never read.

- Prior QA report `.agents/qa/000-pr-4865-qa.md` recorded "Positive: both prompts continue the active implementer phase" under Scenario Coverage. No run produced a continuation to observe.
- Fix: commit `a94c0704a9`, retro-linked QA at `.agents/qa/001-pr-4865-review-fix-qa.md`.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Issue 4851 acceptance | Medium | Two of seven criteria were reported met on evidence that could not distinguish a passing prompt from a failing one. |
| QA evidence | Medium | The QA report inherited the test's claim and restated it as scenario coverage. |
| Review cost | Low | Caught before merge by the bot reviewer, so no defect reached main. |

## Root cause

Five whys.

1. Why did the test pass without measuring the behavior? It asserted against fixture-owned data, not against any output of the system under test.
2. Why was the assertion written that way? The behavior is a model behavior, and pytest has no model in it, so there was nothing available to assert against.
3. Why did that gap not stop the test from being written? The acceptance criterion said "add a fixture," and a dataclass named `ActivePhaseScenario` satisfies that wording literally.
4. Why did the shape survive self-review? A scenario-shaped dataclass with `prompt`, `expected_outcome`, and `required_contract` reads like a behavioral test at a glance. The unread field is invisible unless you trace each attribute to an assertion.
5. Why did no gate catch it? No gate distinguishes an assertion whose left side is derived from the system under test from one whose left side is derived from the fixture. Coverage counts the line either way.

Root cause: the repository has two grading surfaces, pytest for static artifact claims and `scripts/eval/eval-prompt-change.py` for model behavior, and the change routed a behavioral claim to the surface that cannot observe it.

## What worked

- The bot reviewer read the assertion against its fixture and named the exact defect, twice, with the specific remedy.
- The repository already had the right surface: `tests/evals/orchestrator-scenarios.json` with five existing orchestrator scenarios and a shipped-scenario schema gate that picked up the two new entries with no wiring.

## Remediation

| Action | Status | Owner or issue |
|---|---|---|
| Move the two behavioral claims to `tests/evals/orchestrator-scenarios.json` as `S6` and `S7` | Done, commit `a94c0704a9` | This PR |
| Delete the tautological assertions and name the remaining pytest checks as static contract checks | Done, commit `a94c0704a9` | This PR |
| Add pytest checks that the graded scenarios stay registered and stay tied to the shipped prompt text | Done, commit `a94c0704a9` | This PR |
| Mutation-test the new assertions before claiming they work | Done: reverting the routing sentence and deleting `S6` each failed a test, 2 failed and 38 passed | This PR |
| State the surface split in the test module docstring so the next author routes correctly | Done, commit `a94c0704a9` | This PR |

## Learning

When an acceptance criterion names a behavior, ask which surface can observe it before writing the test. If pytest cannot run the thing that produces the behavior, a pytest fixture that describes the behavior is prose, not evidence. Route it to the eval harness and leave a pytest check that the graded scenario still exists, so deleting the coverage fails a test instead of passing quietly.

A cheap detector for this shape: for every assertion, name what produced the left side. If the answer is "the fixture, three lines up," the assertion grades the fixture.
