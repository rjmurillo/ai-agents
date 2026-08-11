---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14680-pr-4865-review-fix.json
qaCommit: a94c0704a9f790839ca446bcfde46ab83e8fc18b
---

# QA Report: PR 4865 review-fix round

## Verdict

PASS. Commit `a94c0704a9f790839ca446bcfde46ab83e8fc18b` closes both review clusters raised on PR 4865 without regressing the cross-harness contract this PR ships.

## Scope

Eight unresolved review threads, clustered into two findings.

| Cluster | Threads | Finding |
|---|---|---|
| A | 6 | The duplicate-routing rule contradicts the Context Maintenance retry rule on all six orchestrator surfaces. |
| B | 2 | Two contract tests assert literals their own fixture created, so the behavioral criteria were unmeasured. |

## Finding verification

Cluster A verdict holds. `templates/agents/orchestrator.shared.md:304` read "Do not re-delegate work already routed this session" while line 210 reads "Change the approach or context before retrying a failed delegation." A failed delegation was routed, so the two rules could not both be satisfied. The diff introduced the conflict: it added the Context Maintenance section and replaced a longer routing rule whose scope was "the log of open delegations is the authority on what is in flight."

Cluster B verdict holds. `test_active_phase_continues_without_restarting` asserted `"implementer phase is active" in active_phase_scenario.prompt`, a string the fixture had just constructed, and never read `expected_outcome`. `test_oversized_synthesis_uses_the_same_bounds` had the same shape. Neither test ran a model, so a restart or a 2,000-word synthesis passed both.

## Fixes

Cluster A: the routing rule now binds work still in flight or returns still held and trusted, and states the changed-retry escape inline. Applied to the four hand-maintained surfaces; both mirrors regenerated.

Cluster B: the behavioral claims moved to `tests/evals/orchestrator-scenarios.json` as `S6` (continue the active implementer phase) and `S7` (trim to the stated bound), which `scripts/eval/eval-prompt-change.py` scores against a model. The pytest file keeps the static claims only, with the tautologies deleted, plus three checks that the graded scenarios stay registered and stay tied to the shipped prompt text.

## Evidence

| Check | Result |
|---|---|
| Targeted tests | 313 passed across `test_orchestrator_shared_contracts.py`, `test_context_budget_management.py`, `tests/eval/test_eval_prompt_change.py`, `tests/commands/test_spec_step0_5.py`. |
| Shipped-scenario schema gate | `TestShippedScenariosValid` passed over the two new scenarios. |
| Python lint | `ruff check tests/test_orchestrator_shared_contracts.py` passed. |
| Python types | `mypy tests/test_orchestrator_shared_contracts.py` passed. |
| Generated agents | `build/generate_agents.py --validate` reported all generated files match committed files. |
| Full generation pipeline | `build/scripts/build_all.py --check` reported no staleness after commit. |
| Install parity | `validate_install_parity.py` returned OK. |
| Semantic drift | Both orchestrator comparisons reported 100.0 percent, 0 drift. |
| Copilot prompt limit | Both Copilot prompts are 29,610 characters, 390 below the 30,000 limit. |

## Mutation evidence

The new assertions fail when the contract regresses. Reverting the routing sentence in `templates/agents/orchestrator.shared.md` and deleting `S6` from the scenario file produced 2 failed, 38 passed, naming both regressions.

## Limitations

The behavioral scenarios are graded on the eval path, which calls a live model and is not part of the pytest run. The pytest suite proves the scenarios exist, are well formed, and match the shipped prompt text; it does not itself score a model response. That boundary is the reason the assertions moved rather than being rewritten in place.
