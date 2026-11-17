# slo-designer

Walks you through designing Service Level Objectives (SLOs): the user journeys that matter, the indicators that measure them, the targets, the error budget, and the burn rate alerts. You get an SLO document you can review with stakeholders. The method follows Google SRE practice.

## When to use it

- You are defining reliability targets for a new or existing service.
- You need an error budget for capacity planning.
- You are setting up service level indicators (SLIs) and alert thresholds.
- Someone asks `what should our availability target be?`
- You say `Design SLOs for my service`, `Define reliability targets`, `Calculate error budget`, or `Define SLIs for this system`.

## When not to use it

- Testing whether the system meets its SLOs by injecting failures: use [`chaos-experiment`](chaos-experiment.md) instead.
- Analyzing security threats: use [`threat-modeling`](threat-modeling.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:slo-designer`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the slo-designer skill to design availability and latency SLOs for our checkout API.
```

The skill asks about the service, its top user journeys, current metrics, infrastructure, and target levels. At the end you get an SLO document with SLIs, targets, error budgets, an alerting strategy, and an implementation checklist.

To calculate one error budget without a conversation, run this from the root of a checkout of `rjmurillo/ai-agents`:

```bash
uv run python .claude/skills/slo-designer/scripts/calculate_error_budget.py --target 99.9 --period monthly
```

## What you get

The SLO document has these sections:

- Service overview (name, owner, description, business criticality).
- Critical user journeys.
- SLIs with a definition, a measurement query, and a data source.
- SLOs as a table of SLI, target, measurement window, and rationale.
- Error budgets with the allowance per period.
- Alerting strategy, split into page-worthy and ticket-worthy alerts.
- Implementation checklist: metrics, dashboard, alerts, runbook, and error budget policy training.

The skill considers five SLI categories: availability, latency, throughput, error rate, and correctness.

## Advanced use

The design process runs in six steps: discovery of user journeys, SLI definition, SLO targets, error budget, alerting, and documentation.

Typical targets the skill offers as a starting point:

| Service type | Availability | Latency (p99) | Error rate |
| --- | --- | --- | --- |
| Consumer web | 99.9% | under 500 ms | under 1% |
| Internal API | 99.5% | under 1 s | under 2% |
| B2B critical | 99.95% | under 200 ms | under 0.1% |
| Batch jobs | 99% | not applicable | under 5% |
| Real-time | 99.99% | under 100 ms | under 0.01% |

Burn rate alerts use multiple windows, for example: alert if the 1-hour burn rate is above 14.4 and the 6-hour burn rate is above 6, or if the 6-hour rate is above 6 and the 24-hour rate is above 2.

Keep the SLO stricter than any SLA so you have a buffer. Do not target 100 percent. Define an error budget policy for what happens when the budget runs out.

### Scripts

Run these from the root of a checkout of this repository:

```bash
uv run python .claude/skills/slo-designer/scripts/calculate_error_budget.py --help
uv run python .claude/skills/slo-designer/scripts/generate_slo_document.py --help
```

`calculate_error_budget.py` flags:

| Flag | Effect |
| --- | --- |
| `--target` | Required. SLO target percentage, such as `99.9`. |
| `--period` | `daily`, `weekly`, `monthly` (default), `quarterly`, or `yearly`. |
| `--format` | `text` (default), `json`, or `markdown`. |

Exit codes: `0` budget calculated, `1` target outside 0 to 100, `2` invalid arguments or a calculation error.

`generate_slo_document.py` flags: `--config` (YAML file), `--output` (default: stdout), and `--sample-config` (print a sample config and exit). It needs PyYAML for YAML configs.

```bash
uv run python .claude/skills/slo-designer/scripts/generate_slo_document.py --sample-config > slo-config.yaml
uv run python .claude/skills/slo-designer/scripts/generate_slo_document.py --config slo-config.yaml --output docs/slo-user-api.md
```

The [`review`](review.md) skill invokes this skill when a change defines or affects a reliability target. For observability signals that feed SLIs, see [`observability`](observability.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`chaos-experiment`](chaos-experiment.md): test SLOs through failure injection.
- [`observability`](observability.md): logging and metrics that supply SLIs.
- [`review`](review.md): calls this skill when a change touches a reliability target.
- Source: [`SKILL.md`](../../src/claude/skills/slo-designer/SKILL.md)
- Reference: [`slo-design-patterns.md`](../../src/claude/skills/slo-designer/references/slo-design-patterns.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
