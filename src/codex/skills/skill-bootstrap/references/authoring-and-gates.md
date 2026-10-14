# Authoring Brief, Optimization Gates, and Report

Load this reference in Phases 4 to 6.

## Contents

- [skillforge brief](#skillforge-brief)
- [Workflow skill shape](#workflow-skill-shape)
- [Writing standard](#writing-standard)
- [Advanced campaigns](#advanced-campaigns)
- [context-optimizer then skillopt](#context-optimizer-then-skillopt)
- [Review](#review)
- [Bootstrap report](#bootstrap-report)

## skillforge brief

Invoke `skillforge` through its supported interface, once per selected
workflow. Pass:

1. The accepted outcome and the observations that prove it.
2. The verified friction, each item with its evidence label and source
   reference.
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
sibling routes. Put conditional detail in `references/`. Add a script only
for repeated deterministic work that no existing feature performs. Use a
Mermaid diagram when the branching is easier to read as a graph. Keep each
command, coordinate, authority requirement, and success check as text beside
the diagram.

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
2. **skillopt.** Run it only when all of these hold. Otherwise report
   `skillopt: NOT RUN` and the missing item.
   - context-optimizer completed. Its output is the incumbent.
   - Scored tasks exist with a held-out split, verifiers, and a canonical
     deployment owner.
   - The evaluation cases were frozen before any candidate was proposed.
     Verified session failures may select tasks. They never become
     fabricated gold answers.
   - Use the installed `skillopt` gate, edit budget, and rejected-candidate
     handling. A candidate is accepted only when it adds a held-out pass and
     loses none. Use a null control when the scorer is nondeterministic.
   - An accepted candidate is not installed. Report it as accepted but not
     deployed until the canonical source and its mirrors carry it.

## Review

1. Run three independent reviews on the final workflows: factual (paths,
   commands, provider semantics, references), doctrine (project constraints
   and authority), and usability (a zero-context engineer or a smaller model
   reaches the outcome).
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
| Workflows | Name, accepted outcome, state: authored, evaluated, or installed |
| Reused features | Existing skills and scripts each workflow composes |
| Verified shortcuts | Each hint with its evidence label and source reference |
| Source coverage | Repository, discourse, each session client, memory: read, partial, or `UNAVAILABLE` |
| Stages | skillforge, context-optimizer, skillopt, review: ran or skipped, with the reason |
| Evaluation | Accepted results, human corrections, rejected attempts, recovery, unnecessary discovery; tokens, tool calls, context size, elapsed time where measured |
| Boundary | Output root, authorized names, `bootstrap_boundary.py verify` exit code |
| Limits | Unresolved disagreements, unmeasured outcomes, smaller-model checks not run |
