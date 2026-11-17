# chaos-experiment

Designs and documents a chaos engineering experiment. You get a scoped plan with a steady-state baseline, a falsifiable hypothesis, a failure injection plan with rollback, and a way to analyze the result.

## When to use it

- You are planning a game day or a failure injection exercise.
- You want confidence in resilience before a production launch.
- You need to check that auto-scaling, circuit breakers, or failover work as designed.
- You want to confirm after a real incident that the fix prevents a repeat.
- You say `design a chaos experiment`, `plan a game day`, `failure injection`, `test resilience`, or `chaos engineering`.

## When not to use it

- You are analyzing security threats: use [`threat-modeling`](threat-modeling.md) instead.
- You are identifying project risks before a system exists: use [`pre-mortem`](pre-mortem.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:chaos-experiment Design a chaos experiment for our API gateway failover
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/chaos-experiment`.

The skill walks you through six phases and writes an experiment document.

## What you get

| Phase | Output |
| --- | --- |
| 1. Scope | System under test, limits on customer impact, stakeholder sign-off |
| 2. Baseline | Steady-state metrics with green, yellow, and red thresholds |
| 3. Hypothesis | A falsifiable prediction: given steady state, when a failure is injected, then behavior stays in tolerance because a named mechanism exists |
| 4. Injection | Failure type, method, scope, duration, ramp-up, and rollback |
| 5. Execute | A timestamped observation log |
| 6. Analyze | A verdict and prioritized action items |

The verdict is one of three words:

| Verdict | Meaning |
| --- | --- |
| `VALIDATED` | The hypothesis held. Document it and expand scope. |
| `INVALIDATED` | The hypothesis failed. Report the bugs to the owner and prioritize fixes. |
| `INCONCLUSIVE` | You could not decide. Refine the experiment design. |

Files go to `.project-toolkit/chaos/`, for example `YYYY-MM-DD-experiment-name.md` and `YYYY-MM-DD-experiment-name-results.md`.

## Advanced use

The baseline needs 7 to 30 days of metrics. Thresholds are baseline plus or minus one standard deviation for green, two for yellow, and beyond two for red. Start with the smallest scope, such as one instance, and set automatic abort criteria before you begin.

> [!WARNING]
> For a State-category experiment (data corruption or cache invalidation) in production, rehearse and verify a restoration path for the corrupted data first. Rollback stops the injection. It does not undo data already corrupted.

Run the scripts from the root of a checkout of this repository.

```bash
uv run python .claude/skills/chaos-experiment/scripts/generate_experiment.py --name "API Gateway Resilience" --dry-run
uv run python .claude/skills/chaos-experiment/scripts/validate_experiment.py experiment.md --strict --json
```

`generate_experiment.py` flags:

| Flag | Meaning |
| --- | --- |
| `--name` | Required. Name of the experiment. |
| `--system` | System under test. Default `TBD`. |
| `--owner` | Experiment owner. Default `TBD`. |
| `--region` | Target region or zone. Default `TBD`. |
| `--target-date` | Target execution date. Default `TBD`. |
| `--output` | Output directory. Defaults to `<cwd>/.project-toolkit/chaos`, or the `chaos/` folder under `AI_AGENTS_ARTIFACT_ROOT` when set. |
| `--json` | Print the result as JSON. |
| `--dry-run` | Print the document without saving. |

`validate_experiment.py` takes a document path plus `--strict` (treat incomplete markers as errors) and `--json`.

| Exit code | `generate_experiment.py` | `validate_experiment.py` |
| --- | --- | --- |
| 0 | Document generated, or printed with `--dry-run` | Validation passed |
| 1 | Generation failed | General failure |
| 2 | Not used | Invalid arguments |
| 10 | Not used | Missing required sections |

Two references ship with the skill: chaos engineering principles, and an SLO, SLI, and SLA reference. Use [`slo-designer`](slo-designer.md) to set the SLO targets that inform your tolerance thresholds. [`review`](review.md) invokes this skill when a change adds a new failure mode worth a game day.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`threat-modeling`](threat-modeling.md): covers security threats, not resilience.
- [`pre-mortem`](pre-mortem.md): finds risks at planning time.
- [`slo-designer`](slo-designer.md): sets SLO targets for your thresholds.
- [`security-scan`](security-scan.md): security review for production experiments.
- [`review`](review.md): invokes this skill for new failure modes.
- Source: [`SKILL.md`](../../src/claude/skills/chaos-experiment/SKILL.md)
- References: [`chaos-engineering-principles.md`](../../src/claude/skills/chaos-experiment/references/chaos-engineering-principles.md), [`slo-sli-sla-reference.md`](../../src/claude/skills/chaos-experiment/references/slo-sli-sla-reference.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
