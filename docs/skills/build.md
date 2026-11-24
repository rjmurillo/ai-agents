# build

Implements a planned change in thin vertical slices, test-first, with atomic commits. It is not done until four exit gates return clean.

## When to use it

- You have a plan step or task and want the code written with tests.
- You say `build this`, `implement this slice`, `write the code for this task`, or `start building`.
- You have already run [`plan`](plan.md).

## When not to use it

- You have not decided what to build: use [`spec`](spec.md).
- You need the work sequenced into milestones: use [`plan`](plan.md).
- You have a finished diff to review: use [`review`](review.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:build add retry with backoff to the sync job, task 3 of the plan
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/build`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /build skill to ...`.

With no argument, it looks for recent plan output in the conversation. If it finds none, it asks what to build.

## What you get

Working code and tests committed in atomic commits, one logical change each, with the test and implementation together. Every test traces to an acceptance criterion (AC) identifier from the spec. Commit messages follow `<type>(<scope>): <desc>` and carry a `Co-Authored-By:` trailer when an AI agent wrote them.

The build ends with the four exit gates reported as clean, or each failing gate reported as FAILED with its disposition.

Hand-off (ADR-123): Writes `implementation-change` and `validation-record`. Next: [`test`](test.md). `metadata.inputs` and `metadata.outputs` in the skill's frontmatter declare the same data.

## Advanced use

Before changing existing behavior, reuse the spec's prior-art evidence when
it covers the same scope. Use [memory-gate](memory-gate.md) or the
[memory](memory.md) recall procedure for gaps.

**Phases.**

| Phase | What happens |
| --- | --- |
| 0. Existing-PR check | Runs `check_existing_pr_for_issue.py` from the `github` skill before branching for an issue. Exit `1` means an open PR claims it: stop and use that PR. Exits `2` to `4` stop and report. |
| 1. Assess complexity | The `analyst` agent classifies the task as Tier 1 to 5. Tiers 1 and 2 are implemented directly. Tier 3 validates the approach first. Tiers 4 and 5 start with a proof of concept and design sign-off. |
| 2. Pre-mortem | Runs [`pre-mortem`](pre-mortem.md) and records the top 2 to 3 risks in the plan or handoff. |
| 2b. Provenance and authority | Decides whether the change can alter validation semantics (see below). |
| 3. Implement | The `implementer` agent works each slice: read the AC, write a failing test, write the minimum code, refactor, self-apply any new detector, commit. |

Code limits during refactor: cyclomatic complexity of 10 or less, methods of 60 lines or less, no nested code, and full test coverage.

**Validation trigger.** Phase 2b runs `validation_trigger.py` with every planned or verified changed path. It prints JSON with the decision, matched targets, and reason. Run it from the root of a checkout:

```bash
uv run python .claude/skills/build/scripts/validation_trigger.py --help
```

Flags: repeatable `--changed-path PATH`, repeatable `--effect NAME`, and `--repo-root`. Known effects: `pass-fail-semantics`, `severity-change`, `baseline-update`, `fixture-redefines-case`, `validator-config`, `vendored-logic`, `generated-validator`. Exit `0` means a decision was emitted. Exit `2` means no changed paths or an unknown effect.

On `"decision": "skip"`, record the reason and go to Phase 3. On `"activate"`, the build invokes [`analysis-provenance`](analysis-provenance.md) for each target and [`validation-authority`](validation-authority.md) to write a decision record. It then checks the record with `validation_record.py`. Exit `0` allows edits only at each target's permitted change location. Exit `1` stops edits until the record is fixed.

**Mandatory exit gates.** Run in order, and all four must return clean:

1. [`code-qualities-assessment`](code-qualities-assessment.md) with `--changed-only --base origin/main --gate-mode regression`.
2. [`taste-lints`](taste-lints.md) against the changed files. Error-level violations reject the build.
3. The documentation gate: the `test` skill's `doc_accuracy_trigger.py`, then [`doc-accuracy`](doc-accuracy.md) when it activates.
4. [`orphan-ref-validator`](orphan-ref-validator.md). `VERDICT: CRITICAL_FAIL` or `VERDICT: ERROR` rejects the build.

**Gate failure disposition.** A finding caused by this diff, or inside the allowed paths, is repaired in the same cycle. A pre-existing finding outside the allowed paths is recorded, not edited. If that finding blocks delivery, the branch stops and the gate is reported FAILED with the owner named. A failed gate stays FAILED: the skill never weakens a gate, adds suppression directives, or changes baselines to pass.

**Hook work.** If the task touches Claude Code or Copilot CLI hook configuration, the skill first invokes [`agent-harness-reference`](agent-harness-reference.md). In the `rjmurillo/ai-agents` repository it then uses [`ai-agents-portability-campaign`](ai-agents-portability-campaign.md).

Before changing a validator, hook, ADR constraint, or shared infrastructure, it invokes [`memory-gate`](memory-gate.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`plan`](plan.md): produces the plan this skill implements.
- [`review`](review.md): reviews the finished diff.
- [`ship`](ship.md): runs pre-flight and opens the PR.
- Source: [`SKILL.md`](../../src/claude/skills/build/SKILL.md)
- Reference: [`implementer-design-and-errors.md`](../../src/claude/skills/build/references/implementer-design-and-errors.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
