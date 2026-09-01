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

## Second failure, same session: the imagined child contract

Round one of review caught a defect in the fix that is a textbook FM-9,
Confident-Incorrectness Recurrence. The section above rules FM-9 out for the
original defect and notes it was "a live risk in the fix". It landed anyway, in
a place I did not check.

`run_rule_activation` parsed the child evaluator's stdout as JSON, because the
three sibling runners in the same file do exactly that. I never ran the child.
The real contract, at `scripts/eval/eval-rule-activation.py:2450-2452`, is:

```python
    if args.output:
        Path(args.output).write_text(json.dumps(all_results, indent=2), encoding="utf-8")
        print(f"\nWrote results: {args.output}")
```

JSON goes to `--output` only. stdout gets a human table. Every real rule
evaluation would have failed to parse and returned `EXIT_EXTERNAL`, which is the
same failure shape as the bug this PR set out to fix, reintroduced one layer
down.

The mock hid it. `_stub_child` returned `{"verdict": "PASS"}` on stdout, so nine
tests agreed with the imagination instead of the CLI. This is the
"self-referential test" anti-pattern in `.claude/rules/canonical-source-mirror.md`:
the test asserted the shape I assumed rather than the shape the artifact
produces.

Measured after the fix, by running the real CLI:

```text
$ eval-rule-activation.py --scenarios tests/evals/rule-scenarios/code-quality.json \
    --dry-run --output /tmp/rr.json
exit=0
stdout: [DRY-RUN] code-quality: 4 scenarios x 3 mechanisms x 4 ... = 48 calls
/tmp/rr.json: No such file or directory
```

Two facts that only running it produces: stdout is not JSON, and `--dry-run`
returns before the `--output` write, so a dry run yields no results file at all.
Both are now pinned by tests that invoke the real child rather than a mock.

The generalizable lesson is narrower than "read the source". It is: **when you
copy a call pattern from a sibling, you have inherited that sibling's contract
assumption, not verified your own.** Three runners parsing stdout is evidence
about those three children, not about a fourth.

## Remediation actions

| # | Action | Status | Owner or issue |
|---|---|---|---|
| 1 | Replace broad prefix matching with the ordered `ROUTING_RULES` table | Done, this PR | PR #5460 |
| 2 | Give every category a runner or an explicit `not_evaluated` reason, pinned by a test that fails if a category has neither | Done, this PR | PR #5460 |
| 3 | Make `--dry-run` invoke no evaluator and parse no model output | Done, this PR | PR #5460 |
| 4 | Read the rule evaluator's results from `--output`, not stdout, and pin the contract with tests that run the real child CLI | Done, this PR | PR #5460 |
| 5 | Filter the routing plan by `--scope` so the dry-run plan matches `_run_evals` | Done, this PR | PR #5460 |
| 6 | Reconcile the published plan against actual results so a scored rule is not reported unscored | Done, this PR | PR #5460 |
| 7 | Fail loudly on a malformed scenario file instead of reporting `not_evaluated`, matching the canonical coverage checker | Done in two passes. Round two caught only `OSError` and `JSONDecodeError`; round three found `UnicodeDecodeError` subclasses `ValueError`, so a binary scenario file still crashed with a traceback instead of the documented config exit. Both paths are now covered and pinned | PR #5460 |
| 8 | Replace the always-skipping end-to-end test with one that builds an isolated fixture repository | Done, this PR | PR #5460 |
| 9 | Three-state evidence in the activation coverage checker's own output, so baseline exemption is never read as efficacy | Not done, deliberately out of scope | Issue #4882, acceptance criterion 7 |
| 10 | Shape `routing_plan` for the always-on reduction work to consume | Not done, needs that work's requirements first | Issue #4871 |
| 11 | The three `nosemgrep` comments in this file sit two lines above their `subprocess.run`, so they attach to nothing; decide whether to repair or delete them repo-wide | Not done. Measured with a probe, patch written, commit refused by `security-suppressions-staged`, reverted | Flagged to a maintainer on PR #5460 |
| 12 | Reject a parseable child payload that names no verdict for the requested rule, instead of reading it as scored | Done, round three | PR #5460 |
| 13 | Preserve the child's own exit code (2 config, 4 auth) instead of flattening a missing results file to 3 | Done, round three | PR #5460 |
| 14 | Promote a routing-plan entry to `scored` only on the runner's evidence label, never inferred from `passed` | Done, round three | PR #5460 |
| 15 | Route command-mirror Copilot skills away from the skill evaluator, which cannot resolve them | Done, round four | PR #5460 |
| 16 | Move the entrypoint row ahead of the prefix rows and test it through the assembled table | Done, round four | PR #5460 |
| 17 | Accept only the real ADR-088 shape as a reference-scenario skip; everything else is malformed | Done, round four | PR #5460 |
| 18 | Give every timeout an explicit `EXIT_EXTERNAL` code, at all five runner sites | Done, round four | PR #5460 |

## Fourth round: the original bug, twice more, inside my own fix

Round four found `src/copilot-cli/skills/` conflates two artifact kinds. Most
entries mirror `.claude/skills/<name>/`. Fourteen mirror
`.claude/commands/<name>.md` and have no Claude skill at all. The skill
evaluator resolves only `.claude/skills/`:

```text
$ eval-knowledge-integration.py --skill spec --dry-run
exit=1
ERROR: Skill directory not found for 'spec' in .../.claude/skills
```

That is issue #4882's exact failure shape, at a site my own fix created by
adding `src/copilot-cli/skills/` to the skill prefixes without asking what was
actually in that directory. I widened a prefix to fix a widening bug.

The same round found the `entrypoints` row was dead. It sat after the prefix
rows in a first-match table, and every real path-local entrypoint lives inside
a prefix that precedes it, so `.claude/commands/CLAUDE.md`,
`.claude/skills/CLAUDE.md`, `.claude/skills/github/CLAUDE.md` and twenty more
were classified as prompts or skills. My round-one test exercised the matcher
in isolation, where it passed. The shadowing exists only in the assembled
table, and no test drove that.

Both are one mistake in different clothes: **I checked that each rule matches
what it should, never that it wins.** The reachability test from round one used
synthetic representative paths, so it proved each row could win for a path
invented to suit it, not for the paths that actually exist in the tree. A
routing table's contract is resolution order against real inputs, and synthetic
inputs cannot test order because they were built to match exactly one row.

Round four's tests are anchored to real tree contents, with negative controls
asserting the premise (these entrypoint files exist; these fourteen skills have
a command and no Claude skill) so the assertions cannot pass vacuously.
Reverting the four fixes together fails 37 tests.

## Third failure, same shape as the second

Round two fixed the child contract but left four adjacent paths wrong, and the
common thread is the same one the section above names: I fixed the case I was
shown rather than the class it belongs to.

- Round two made the runner read `--output`. It did not ask what a *parseable
  but empty* payload should mean, so `{"schema_version": 1, "rules": {}}` was
  accepted as a pass and published as scored efficacy evidence for a run that
  produced no verdict.
- Round two mapped a missing results file to `EXIT_EXTERNAL`. The child exits 2
  on an invalid scenario and 4 on a missing key, writing no file in either
  case, so that mapping reported an API failure for a config or auth fault.
- Round two caught `OSError` and `JSONDecodeError` on scenario reads.
  `UnicodeDecodeError` subclasses `ValueError`, so it escaped both.
- Round two reconciled the plan by checking `"passed" in outcome`. `passed` is
  False for a failing verdict, a timeout, and an unreadable result alike, so a
  timeout was promoted to `scored`.

Each is a different exception type or a different branch, and each was
reachable from the code round two shipped. The generalizable lesson: **after
fixing a contract, enumerate the states the contract can be in, not just the
state that failed.** Parse success is not verdict presence; a nonzero exit is
not one kind of failure; a decode error is not an I/O error; and a boolean that
means "did not pass" cannot distinguish "failed" from "never ran".

The negative control for round three: reverting all four fixes at once fails 16
tests, spread across all four findings.

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
