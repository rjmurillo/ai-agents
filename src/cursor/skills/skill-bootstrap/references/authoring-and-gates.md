# Authoring Brief, Optimization Gates, and Report

Load this reference in Phases 4 to 6.

## Contents

- [Plan file](#plan-file)
- [skillforge brief](#skillforge-brief)
- [Workflow skill shape](#workflow-skill-shape)
- [Provenance contract](#provenance-contract)
- [Writing standard](#writing-standard)
- [Advanced campaigns](#advanced-campaigns)
- [Capability eval](#capability-eval)
- [context-optimizer then skillopt](#context-optimizer-then-skillopt)
- [Review](#review)
- [Bootstrap report](#bootstrap-report)

## Plan file

Phase 3 writes one plan file outside the repository. `bootstrap_forms.py
check` validates it; Phase 4 passes each item to `skillforge`.

```json
{"project": "acme", "mode": "workflow",
 "items": [
  {"id": "I1", "skill": "acme-change-control", "lens": "change-control",
   "claim": "A change under templates/ requires a build_all.py run and a drift check",
   "evidence": ["commit 1a2b3c4 revert", "PR #812 review thread"],
   "computable": true, "form": "both", "script": "scripts/gates_for_path.py",
   "why": "Prose keeps the incident that made the rule; the script maps paths to gates"},
  {"id": "I2", "skill": "acme-architecture-contract", "lens": "architecture-contract",
   "claim": "Generators never write the install tree",
   "evidence": ["ADR-0109", "incident 2025-12-15"],
   "computable": false, "form": "scaffold",
   "why": "The rule is a design reason; its enforcement already exists as a gate the skill links"}
 ]}
```

| Field | Rule |
|---|---|
| `lens` | One of `change-control`, `debugging-playbook`, `failure-archaeology`, `architecture-contract`, `domain-reference`, `config-and-flags`, `build-and-env`, `run-and-operate`, `diagnostics-and-tooling`, `validation-and-qa`, `docs-and-writing`, `external-positioning`, `hardest-problem-campaign`, `proof-and-analysis-toolkit`, `research-frontier`, `research-methodology`, or `other:<name>` |
| `evidence` | Non-empty list of source references: commit, PR thread, issue, file, decision record |
| `computable` | Required boolean on every item. `true` when a program can answer the claim from repository state; a missing or non-boolean value is a violation |
| `form` | `scaffold`, `instrument`, or `both`. `computable: true` forbids `scaffold` |
| `script` | Required for `instrument` and `both`: a path in the skill's scripts directory |
| `why` | Required for `scaffold`: why no program can carry it |
| `baseline_case` | Required in `knowledge` mode: the eval case id that shows the gap |

### Sorting an item by tool form

Ask in order. Stop at the first yes.

1. Can a program answer it every time from files, git history, or a tool's
   output? It is `instrument`. If a wrong use of the answer has a history,
   or the answer has edges a reader must know, it is `both`.
2. Does it guide a judgment that depends on context a program cannot see,
   such as intent, trade-offs, or which evidence to trust? It is
   `scaffold`.
3. Is it a fact that will drift? It still needs a `reverify.json` check,
   whatever its form.

## skillforge brief

Invoke `skillforge` through its supported interface, once per selected
workflow. Pass:

1. The accepted outcome and the observations that prove it.
2. The plan items for this skill, each with its evidence label, source
   reference, and tool form.
3. The existing features to reuse, and how each output feeds the next input.
4. Constraints: output root, the `<project>-<lens>` name, the authority
   boundary, and the budget.
5. The required decision: reuse, improve, compose, or create. `skillforge`
   runs its own Phase 0 triage and may return a reuse or compose route
   instead of a new skill. Accept that route.

The bootstrap skill is repository-agnostic. Each workflow it produces is
intentionally project-specific.

If `skillforge` is not installed, stop the authoring phase and report
`skillforge: UNAVAILABLE`. Do not hand-write skills to replace it.

## Workflow skill shape

Each workflow skill holds:

- **First useful action.** The command or read that starts real work.
- **Discriminating observations.** What to look at to choose a branch.
- **Decision branches.** One branch per observed outcome, each with its next
  action.
- **Outcome checks.** The observations that prove the accepted outcome.
- **Sibling routes.** Where to go for failures and out-of-scope tasks.
- **Project hints.** Only hints that prevent a known wrong turn or remove
  repeated discovery. Each surprising hint cites its source: a file, commit,
  issue, PR thread, or decision record.

Prefer a link to a maintained procedure over a copied manual. Keep `SKILL.md`
thin: triggers, outcomes, decisions, feature order, essential hints, and
sibling routes. Put conditional detail in `references/`.

**Every computable claim ships with a script.** For each `instrument` or
`both` item, the skill gets a script in its scripts directory that computes the
answer, plus tests with a positive, a negative, and an edge case. Reuse an
existing project script when one computes the answer; link it instead of
copying it. Prose covers what no program can carry: the reason, the
history, and where the script's answer stops being the whole answer. Reject
a draft that asks the model to count, look up, compare, or list what a
script could. Scripts follow the project's language and exit-code
conventions, print the examined count, and stay read-only unless the skill's
outcome is a write.

The rejected alternative is "add a script only for repeated deterministic
work". It was dropped because a claim computed once is still a claim the model
can miscompute, and the repeat count is unknowable before the skill ships.
The SKILL.md Limits entry records that run `20261017T164000Z-2e1e279c` did not
show a capability gain from the script-first rule, so this rationale is a
design argument, not a measured result.

Use a
Mermaid diagram when the branching is easier to read as a graph. Keep each
command, coordinate, authority requirement, and success check as text beside
the diagram.

## Provenance contract

Every authored skill ships `reverify.json` at its skill root, so
`bootstrap_drift.py` can detect drift before an agent follows a dead route.
Add one check per load-bearing fact: each path the skill tells an agent to
read or run, each line reference, each literal it quotes from a file, and
each retired surface it says is gone.

```json
{"checks": [
  {"id": "R1", "kind": "path_exists", "path": "build/scripts/build_all.py"},
  {"id": "R2", "kind": "contains", "path": "AGENTS.md", "text": "ADR-042"},
  {"id": "R3", "kind": "line_count_at_least", "path": "build/scripts/build_all.py", "min": 905},
  {"id": "R4", "kind": "absent", "path": ".agents/HANDOFF.md"},
  {"id": "R5", "kind": "command", "argv": ["python3", "scripts/check.py", "--help"], "expect_exit": 0}
]}
```

Prefer `path_exists`, `contains`, `line_count_at_least`, and `absent`: they
run without executing repository code. A `command` check runs only under
`--allow-commands`. Date-stamp a volatile fact in the prose beside its check.
End each skill with a `Provenance and Maintenance` section that names
`reverify.json` and the drift command.

## Writing standard

Follow [ASD-STE100](https://www.asd-ste100.org/about_STE.html) guidance:

- Imperative instructions, active voice, short sentences.
- One action per step. One term per concept.
- Keep identifiers, paths, commands, and domain terms exact.
- Define an unfamiliar term once.
- Remove repetition and generic engineering advice the model already knows.

Call the result "STE-inspired" unless you checked it against the STE
specification and dictionary. Correct execution outranks a low word count.
Do not compress a step until it becomes cryptic.

## Advanced campaigns

Use this shape for the hardest-problem campaign, the proof and analysis
toolkit, and research lenses:

1. Number the phases. Give exact commands and the expected observation for
   each.
2. Give a failure branch for each phase.
3. Rank solution options. State what analysis or derivation each option
   needs.
4. Require an explanation that accounts for positive and negative
   observations.
5. For supported research, give three repository steps and one falsifiable
   milestone.
6. Label unproven ideas as candidates. Promote a result only through the
   project's existing change-control and acceptance gates.

## Capability eval

Capability is what an agent achieves with the skill. The eval measures it
as the pass rate with the skill minus the pass rate without it, on the same
frozen cases. Build it in every run.

1. **Write cases.** For each skill, write at least three cases outside the
   repository. If the user wants them committed, authorize their paths in
   Phase 1 (pass each to `verify` as `--also-allow`) and pass
   `--allow-in-repo` to `freeze`:
   - one from each verified correction or failure the skill targets
     (`source: correction:<ref>`), using the task the agent faced, not the
     answer it was given;
   - one from each accepted outcome (`source: outcome:<ref>`);
   - in `knowledge` mode, one per covered lens (`source: lens:<name>`).
2. **Grade deterministically.** Use `contains_all`, `regex`, or
   `json_set_f1` with gold you derived from the repository before authoring.
   A case with no deterministic gold is not a case; record it under Limits.
3. **Freeze** with `bootstrap_eval.py freeze` before you run anything. The
   hash makes a later edit to a case visible.
4. **Run** each case at least twice per condition (protocol advice; `score`
   does not enforce it), in fresh agent contexts
   that differ only in whether the skill is installed. Use the smaller
   model the library targets. Write one JSON line per run:
   `{"case_id", "condition": "baseline" | "with_skill", "output"}`.
5. **Score** with `bootstrap_eval.py score`. Read each case status:

   | Status | Meaning | Action |
   |---|---|---|
   | `gain` | The skill raises the pass rate | Keep |
   | `no_gap` | Baseline already passes | The knowledge is not missing. In `knowledge` mode, a skill whose cases are all `no_gap` fails the gate, enforced by `score --mode knowledge` (exit 1, cases listed in `failing_cases`): drop the skill |
   | `flat` | Equal pass rates, below 1.0 | The skill does not transfer. Fix the skill or the case |
   | `regression` | The skill lowers the pass rate | Blocking finding |
   | `incomplete` | A condition has no runs, or a run is ungraded (regex timeout) | Run it, or report it under Limits |

When no agent runner is available, freeze the cases anyway and report
`capability: NOT RUN (no runner)` with the frozen file. The next run scores
them.

## context-optimizer then skillopt

The order is fixed. Each stage reads the previous stage's output.

1. **context-optimizer.** Run it on each authored skill and its composition.
   - Inspect duplication, placement, retrieval cost, and the first useful
     action.
   - Delete redundant content before compressing.
   - Keep trigger-critical decisions and essential hints in `SKILL.md`.
   - Preserve scope, commands, prerequisites, branches, authority, and
     acceptance conditions.
   - Check that every reference link resolves after a move.
   - Add no always-on context. Change no instruction outside the boundary.
2. **skillopt.** Run it only when both preconditions hold. Otherwise
   report `skillopt: NOT RUN` and name the missing precondition.
   - context-optimizer completed on this skill.
   - The capability eval froze this skill's cases. They are the held-out
     set; never tune on them and then report them as held out.

   When a run starts, `skillopt` owns the acceptance gate; follow its
   contract. Bootstrap adds two constraints:
   - The context-optimized draft is the incumbent.
   - Freeze the evaluation cases before any candidate exists. Verified
     session failures may select tasks. They never become fabricated gold
     answers.

   Reporting rule: an accepted candidate is not installed. Report it as
   accepted but not deployed until the canonical source and its mirrors
   carry it.

## Review

1. Run three independent reviews on the final workflows. Independent means
   a separate agent context that receives only the artifacts and the
   requirements, never the author's reasoning.
   - Factual: run `bootstrap_mine.py claims` and `bootstrap_drift.py check`
     (without `--allow-commands` unless the user approved the argv list) first, then check what the scripts cannot: provider semantics, and
     whether each claim is true, not only whether its path exists.
   - Doctrine: the repository's instruction files, rules, and authority
     limits.
   - Usability: a zero-context engineer or a smaller model reaches the
     outcome from the skill alone. The capability eval is the measured
     form of this review; the reviewer reads its result.
   - Tool form: every computable claim is backed by a script, and no
     script hides a judgment that needs prose.
2. Follow `skillforge`'s own review requirements.
3. Check that every referenced sibling skill and script exists in the
   supported installation.
4. Judge the composition by outcome, not by the number of features invoked.
5. Fix blocking and important findings by returning to Phase 4. Run
   context-optimizer and the eligible skillopt gate again on changed
   workflows.
6. Never write an approval marker yourself in place of an independent review.

## Bootstrap report

Return these sections. Use `UNAVAILABLE`, `NOT RUN`, or `UNMEASURED` instead
of a guess.

| Section | Content |
| --- | --- |
| Mode | `workflow` or `knowledge`, and the gate evidence per skill |
| Workflows | Name, accepted outcome, state: authored (files written), evaluated (capability eval scored), or installed (a fresh harness session lists it) |
| Tool forms | Per skill: counts of scaffold, instrument, and both items; scripts shipped; `bootstrap_forms.py` exit code |
| Capability | Per skill: baseline and with-skill pass rates, capability delta, case statuses, model, runs per condition; else `NOT RUN` with the frozen cases path |
| Provenance | Per skill: `reverify.json` check count; `bootstrap_drift.py` and `claims` exit codes |
| Reused features | Existing skills and scripts each workflow composes |
| Verified shortcuts | Each hint with its evidence label and source reference |
| Source coverage | Repository, discourse, each session client, memory: read, partial, or `UNAVAILABLE` |
| Stages | candidates, skillforge, context-optimizer, capability eval, skillopt, review: ran or skipped, with the reason |
| Evaluation | Accepted results, human corrections, rejected attempts, recovery, unnecessary discovery; tokens, tool calls, context size, elapsed time where measured, else `UNMEASURED` |
| Boundary | Output root, authorized names, `bootstrap_boundary.py verify` exit code |
| Limits | Unresolved disagreements, unmeasured outcomes, smaller-model checks not run |
| Handoff | Uncommitted files and the commands the user runs next, such as the repository's build and validation gates |
