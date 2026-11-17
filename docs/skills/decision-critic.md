# decision-critic

Stress-tests a decision before you commit to it. It pulls out the claims and assumptions behind your reasoning, checks each one, argues the other side, and returns a verdict.

## When to use it

- You are making a consequential decision that is hard to reverse.
- You are evaluating a plan, ADR, or design before commitment.
- You want structured adversarial feedback, not just a second opinion.
- You say things like `Validate my thinking on...`, `Poke holes in this decision`, `Criticize this approach`, or `Stress-test this tradeoff`.
- You present a decision rationale and ask for criticism.

## When not to use it

- You want to surface failure risks before a launch: use [`pre-mortem`](pre-mortem.md) instead.
- You want to know why a constraint exists before you remove it: use [`chestertons-fence`](chestertons-fence.md) instead.
- You need the user to choose between options: use [`decision-question`](decision-question.md) instead.
- You need strategic challenge on direction (whether, not how), or the question is about project scope or priorities: use the [`independent-thinker`](../agents/independent-thinker.md) agent instead.
- The decision is trivial. The workflow costs time and fits only consequential choices.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:decision-critic`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the decision-critic skill to stress-test our decision to replace the queue worker with a managed service. Constraints: two engineers, ship in six weeks.
```

The agent works through seven steps, carrying its analysis forward each time. At the end you see a verdict and the list of claims that failed or stayed uncertain.

## What you get

The workflow runs in four phases.

| Steps | Phase | What happens |
| --- | --- | --- |
| 1-2 | Decomposition | Extracts claims, assumptions, constraints, and judgments. Gives each a stable ID (`C1`, `A1`, `K1`, `J1`). |
| 3-4 | Verification | Writes verification questions and answers them independently. Marks each item `VERIFIED`, `FAILED`, or `UNCERTAIN`. |
| 5-6 | Challenge | Generates a contrarian perspective and an alternative framing. |
| 7 | Synthesis | Returns the verdict. |

The verdict is one of `STAND` (clean or flagged), `REVISE`, or `ESCALATE`.

- A `STAND` is flagged, not clean, when the rewrite-regression check answered questions 1 through 4 but left question 5 (the institutional incentive that produced the original problem) unanswered.
- Read every `UNCERTAIN` and `FAILED` item even when the verdict is `STAND`.
- The inversion analysis covers at least three failure modes.

## Advanced use

### Run the script directly

The script prints guidance for one step per call. Run it from the root of a checkout of this repository:

```bash
uv run python .claude/skills/decision-critic/scripts/decision-critic.py --help
```

| Flag | Required | Meaning |
| --- | --- | --- |
| `--step-number` | Yes | Current step, 1 to 7. |
| `--total-steps` | Yes | Always 7. |
| `--decision` | Step 1 | The decision being criticized. |
| `--context` | Step 1 | Constraints, background, and system context. |
| `--thoughts` | Yes | Your analysis, with all IDs and statuses from prior steps. |

| Exit code | Meaning |
| --- | --- |
| `0` | Step guidance printed. |
| `1` | Step number outside 1 to 7, or `--decision` missing at step 1. |

The SKILL.md also lists an exit code `2` for failed or incomplete analysis. The `--help` output does not list it.

Example:

```bash
uv run python .claude/skills/decision-critic/scripts/decision-critic.py --step-number 1 --total-steps 7 --decision "Adopt X" --thoughts "Initial claim"
```

### Rewrite-regression halt

When the decision is a rewrite, refactor, or migration justified by improvement, the skill applies the rewrite-regression check during steps 3 and 4. A `STAND` is not valid while that halt is open.

- If the proposer can answer only the v0 win, and not the baseline, the v1 projection, and the regression plan, the skill halts.
- It returns `ESCALATE` when only the v0 win exists.
- It returns `REVISE` for partial answers, per the reference table.

### Inversion thinking

Before you finalize a decision, the skill applies an inversion protocol: state the goal, invert it into failure, list failure scenarios, reverse each into a success criterion, then check the decision against those criteria. Use it as a final check before approving plans or ADRs.

### Chaining

[`buy-vs-build-framework`](buy-vs-build-framework.md) feeds its Phase 4 rationale to this skill for validation. The skill is not user-facing in that routing.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pre-mortem`](pre-mortem.md): surfaces failure risks before launch.
- [`chestertons-fence`](chestertons-fence.md): probes why a constraint exists.
- [`decision-question`](decision-question.md): asks the user to choose.
- [`buy-vs-build-framework`](buy-vs-build-framework.md): calls this skill to validate its rationale.
- Source: [`SKILL.md`](../../src/claude/skills/decision-critic/SKILL.md)
- Reference: [Rewrite-regression check](../../src/claude/skills/decision-critic/references/rewrite-regression-check.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
