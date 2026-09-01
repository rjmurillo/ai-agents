# Issue #4882: the eval router's `other` bucket was a silent default

**Date**: 2026-09-01
**Issue**: #4882
**Scope**: `scripts/eval/eval-suite.py` routing table plus its tests
**Failure mode**: FM-10, Silent Defaults and Guard-Clause Suppression
(`.agents/governance/FAILURE-MODES.md`, section 10)

## What happened

`classify_changes` in `scripts/eval/eval-suite.py` routed changed files by broad
directory prefix. `AGENT_PATTERNS` carried `src/copilot-cli/`, and the agent
branch ran before the skill branch, so every Markdown file anywhere under the
Copilot plugin tree was classified as an agent. `.claude/rules/` and
`.github/instructions/` matched no pattern at all and fell into `other`.

Reproduced at the commit the issue names,
`2628d8c1282277ad39bc605eb6a31131eff2d77e`, with the issue's own command:

```text
PYTHONPATH=scripts/eval uv run --frozen python \
  scripts/eval/eval-suite.py --base-ref HEAD~1 --dry-run --scope all

Changed files: 17
agents: 4 files
skills: 2 files
other: 11 files
Overall: FAIL
exit 3
```

That output matches the issue body line for line, so the report was not stale.

## Why FM-10

FM-10's unifying property is stated as: "the call site has no way to know the
operation didn't actually do what its name claims."

`eval-suite.py --scope all` claims to evaluate everything that changed. On this
diff it evaluated no rule and no instruction mirror, and said nothing about it.
Six context-bearing files landed in a bucket named `other` that has no runner,
no message, and no exit-code consequence. The categories were even printed
(`other: 11 files`), which reads as accounting rather than as a gap. That is
FM-10's `dict.get(key, default)` shape at the routing layer: the missing key was
itself the bug, and the default absorbed it.

The second half is the same mode with the polarity flipped. The misrouted files
did reach a runner, `eval-agents.py`, which cannot evaluate them:

```text
$ eval-agents.py --agent canonical-source-mirror.instructions --dry-run
exit=1
stderr: ERROR: Agent definition not found: .../.claude/agents/canonical-source-mirror.instructions.md
```

Empty stdout, so `_parse_child_json` raised, so `exit_code` became
`EXIT_EXTERNAL`, so the suite exited 3. The suite reported an external API
failure for what was actually a routing bug. The verdict was wrong about its own
cause, which is the "verdict laundering" bullet in FM-10's trigger list read in
reverse: absence of signal became a confident, and misattributed, negative one.

## Near-miss modes ruled out

**FM-9, Confident-Incorrectness Recurrence.** The closest call, because this fix
touches a component that mirrors another source. FM-9 requires an author who
"models the contract from memory instead of reading it." The original defect has
no such claim: `AGENT_PATTERNS` asserts nothing about a canonical source, it is
just a prefix list that grew too broad. FM-9 was a live risk in the *fix*, not
the defect, because the new `rule_id_for_path` claims to mirror
`scripts/validation/check_rule_activation_coverage.py`. That claim is quoted
verbatim in the docstring per `.claude/rules/canonical-source-mirror.md`, and the
scenario lookup reads each scenario's `rule_path` rather than assuming the
filename stem, which is what would have been the imagined contract:
`tests/evals/rule-scenarios/` also holds ADR-088 scenarios carrying `skill_path`
and no `rule_path`, so a stem convention would have invented rule ids for
`clean-architecture`, `data-intensive-applications`, and four others.
Not FM-9, but only because the check was run.

**FM-4, False Completion Markers.** FM-4 is an agent reporting success against an
unmet acceptance criterion. Here the suite reported FAIL, loudly, with a nonzero
exit. Nothing claimed completion. FM-10 is named upstream of FM-4 in the catalog;
this incident stopped at the mechanism and never produced the symptom.

**FM-11, Customer-facing generated artifact shipped without runtime
verification.** `eval-suite.py` is a contributor-facing script under `scripts/`.
It is not inside `.claude/`, `src/claude/`, or `src/copilot-cli/`, so it ships in
no plugin and reaches no consumer. FM-11 does not apply.

**FM-3, Ambiguous Instruction Inversion.** No instruction was inverted. The
routing table did exactly what it said; what it said was too broad.

## What changed

An ordered `ROUTING_RULES` table replaces the prefix loops, per
`.claude/rules/code-quality.md` section "Table-Driven Logic". Narrowest row
first, first match wins. Reference rows precede the trees that contain them;
instruction rows precede agent rows.

Every category now names a runner or carries an explicit `not_evaluated` reason,
and a test asserts that each category appears in exactly one of
`RUNNER_BY_CATEGORY` and `NOT_EVALUATED_REASONS`. That is the direct FM-10
countermeasure: a new category cannot be added without deciding, in code, whether
it is evaluated.

`--dry-run` no longer invokes any child evaluator. The same reproduction now
exits 0 in 0.3 seconds and prints a deterministic routing plan.

## Negative controls

The ordering claim is the load-bearing one, so it is tested rather than asserted.

Reintroducing the bare `src/copilot-cli/` prefix into `AGENT_PATTERNS` fails four
tests, verified by doing it:

```text
FAILED test_classify_path_routes_to_expected_category[src/copilot-cli/docs/copilot-instructions.md-other]
FAILED test_classify_changes_agrees_with_classify_path[src/copilot-cli/docs/copilot-instructions.md-other]
FAILED test_non_agent_paths_never_route_to_the_agent_evaluator[src/copilot-cli/docs/copilot-instructions.md]
FAILED test_agent_rows_no_longer_carry_the_broad_copilot_prefix
4 failed, 120 passed
```

Worth recording what that run also showed: with the broad prefix restored, skill
references and instruction mirrors still routed correctly, because the ordering
protects them independently of the prefix width. Narrowing the prefix is not what
fixes those; row order is. So a second control moves the agent rows ahead of the
reference rows and asserts the misroute returns, and a per-row test asserts every
row still wins for its own representative path. Without those two, the suite
would have been pinning a property it was not actually testing.

## What I would tell the next person

Two things.

A fall-through bucket with no runner is a silent default even when it is printed.
`other: 11 files` looks like accounting and reads like coverage. If a category
can hold something that should have been evaluated, it needs a reason string, not
a count.

And when a fix has two plausible mechanisms, find out which one is load bearing
before writing the test. I assumed narrowing the prefix was the fix and would
have shipped tests that passed for the wrong reason. The negative control is what
surfaced that ordering, not prefix width, is what actually protects the narrow
categories.

## References

- Issue #4882.
- `.agents/governance/FAILURE-MODES.md`, section 10.
- `.claude/rules/code-quality.md`, section "Table-Driven Logic".
- `.claude/rules/canonical-source-mirror.md`.
- `scripts/validation/check_rule_activation_coverage.py`, the canonical
  scenario-to-rule-id contract.
- `tests/eval/test_eval_suite_routing.py`.
