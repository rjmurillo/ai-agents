# evidence-provenance

Decides whether two pieces of evidence are independent or the same loop twice, and whether a named check actually ran. It returns a verdict and the number of independent confirmations you may cite.

## When to use it

- A review or test gate must decide whether two pieces of evidence confirm a claim independently.
- You need to know if a reviewer confirmed a claim from primary evidence or from the implementer's conclusion.
- You need to report which checks ran, using `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, or `FAILED`.
- Trigger phrases: `is this independent evidence`, `did the reviewer confirm this`, `closed loop`, `count the confirmations`, `which checks actually ran`.

## When not to use it

- You want to report progress: follow the voice rule instead.
- You want to pick which validator governs a change: use [`validation-authority`](validation-authority.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:evidence-provenance count the independent confirmations for the retry fix: the new test, the reviewer comment, and the CI run
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/evidence-provenance`.

The skill records each item with its lineage, classifies the record, and tells you how many independent loops you can cite.

## What you get

A verdict from the classifier:

| Verdict | Meaning |
| --- | --- |
| `CORROBORATED` | At least one independent loop verified the claim. `independent_loops` is the count to cite. |
| `SINGLE_LOOP` | Verified, but only inside the subject's loop. Cite it as one loop, however many files. |
| `FALSIFIED_BY_INDEPENDENT_OBSERVATION` | An independent item with normative or executable-runtime authority failed. It wins over any same-loop pass. |
| `FAILED` | An item failed without independent authority. Investigate before citing anything else. |
| `NO_VERIFIED_EVIDENCE` | Nothing verified, or every item was rejected for a binding problem. |

The core rule: a second artifact is not a second proof. A test and an implementation written from the same reading of a requirement are useful evidence about the implementation. They are not two confirmations of the requirement.

## Advanced use

Write the record as JSON and run the classifier from the root of a checkout of this repository:

```bash
uv run python .claude/skills/evidence-provenance/scripts/classify_lineage.py record.json --promotion
```

| Option | Meaning |
| --- | --- |
| `record` | JSON evidence record. |
| `--promotion` | Require artifact, revision, validator, command, and result on every item. Use it when the evidence gates a deployment. |

| Exit code | Meaning |
| --- | --- |
| 0 | Classification computed, no violation. This is not a pass: `NO_VERIFIED_EVIDENCE` also exits 0. |
| 1 | A violation, a `FAILED` item, or independent falsification. |
| 2 | Unreadable JSON, unknown enum value, or missing field. |

Rules that decide most cases:

- Shared premise or inheritance joins the subject's loop. A reviewer handed the implementer's conclusion is in that loop.
- An item with no recorded premises is never independent.
- An item whose `bound_to` names a different artifact or revision is rejected as `binding-mismatch`. Under `--promotion`, a missing binding is rejected as `binding-missing`.
- Set `claimed_independent` to the number you intend to write. A claim above `independent_loops` exits 1 as `inflated-confidence`.
- Independence and authority are separate axes. The output carries both.

A promotion gate must also require a `CORROBORATED` or `SINGLE_LOOP` verdict and an empty `rejected` list.

Evidence that strengthens a claim: a pre-existing test that was red and is now green, observation of the real runtime, a reviewer who rebuilt the result from primary evidence, and a new test that fails when the defect is restored (marked `discriminating`, still one loop for the premise).

Named checks carry one of four states. Any other wording ("should run X", "pending", no state) exits 1 as `named-without-state`. A `NOT RUN` or `FAILED` item used as support exits 1 as `unverified-support`. A cheap check left `NOT RUN` and not cited returns the warning `cheap-gate-not-run`. Expensive, destructive, or credentialed checks are never mandatory. You only report their state.

The script trusts the lineage fields it receives, so a fabricated premise list defeats it. Check the fields against the diff and the transcript, not the agent's summary. The field model is in [`references/lineage-model.md`](../../src/claude/skills/evidence-provenance/references/lineage-model.md).

[`review`](review.md) invokes this skill when a gate must decide on independence.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`review`](review.md): invokes this skill and owns review verdicts.
- [`validation-authority`](validation-authority.md): picks the validator that governs a change.
- [`analysis-provenance`](analysis-provenance.md): finds who owns a validator or linter (upstream, local, or vendored) before you change it.
- Source: [`SKILL.md`](../../src/claude/skills/evidence-provenance/SKILL.md)
- Reference: [`lineage-model.md`](../../src/claude/skills/evidence-provenance/references/lineage-model.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
