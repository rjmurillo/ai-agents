# pre-mortem

Finds project risks before they happen. You imagine the project has already failed, list the reasons, and rank each one by likelihood and impact. The result is a risk inventory with mitigations, owners, and a review schedule.

## When to use it

- You are starting a new project or feature and want risks up front.
- The team is overly optimistic and the downsides need to surface.
- Stakeholders need to understand risk before they commit resources.
- Scope changed a lot and you need to reassess risk.
- You say `run a pre-mortem on`, `what could cause this to fail`, `identify project risks`, `what could go wrong with`, or `pre-mortem analysis`.

## When not to use it

- You are analyzing security threats, such as STRIDE or attack trees: use [`threat-modeling`](threat-modeling.md) instead.
- You want to stress-test a single decision's reasoning: use [`decision-critic`](decision-critic.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:pre-mortem`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the pre-mortem skill to run a pre-mortem on our plan to migrate the billing service to the new queue by end of Q2.
```

The agent walks you through five phases. At the end you get a risk inventory in Markdown, ranked by score.

## What you get

A risk inventory with this structure:

- Project context: objective, timeline, key dependencies.
- A risk summary table with counts per priority.
- Critical and High risks in full, each with category, failure scenario, likelihood, impact, score, root cause, mitigation, owner, and status.
- Medium risks in short form, and Low risks as a list.
- An action items table with owner, due date, and the risk addressed.
- A review schedule.

Scores are likelihood times impact, each on a 1 to 5 scale.

| Score | Priority | Action |
| --- | --- | --- |
| 15 to 25 | Critical | Address immediately. |
| 8 to 14 | High | Plan mitigation. |
| 4 to 7 | Medium | Monitor. |
| 1 to 3 | Low | Accept or defer. |

## Advanced use

### The five phases

| Phase | Time | Output |
| --- | --- | --- |
| 1. Brief | 2 to 3 min | Project context documented. |
| 2. Failure announcement | 30 sec | Mindset shift. The agent says the project has failed, in past tense. |
| 3. Independent analysis | 3 to 5 min | Raw list of 5 to 10 failure reasons, unfiltered. |
| 4. Round-robin collection | 5 to 10 min | Reasons grouped by category, without debate. |
| 5. Review and mitigate | 10 to 15 min | Risk inventory with mitigations. |

Categories are Technical, People, Process, Organizational, External, and Unknown Unknowns. In a team setting, each person writes alone first, then shares one reason per round, and senior members speak last.

Each mitigation has three parts: Prevention (how to stop it), Detection (how to know early), and Response (what to do if it happens).

### Validate the inventory

Run from the root of a checkout of this repository:

```bash
uv run python .claude/skills/pre-mortem/scripts/pre-mortem.py --help
```

| Flag | Meaning |
| --- | --- |
| `--inventory-path` | Path to the risk inventory Markdown file. Required. |
| `--validate` | Run validation (the default behavior). |
| `--quiet` | Suppress output and return only the exit code. |
| `--json` | Output the result as JSON. |

```bash
uv run python .claude/skills/pre-mortem/scripts/pre-mortem.py --inventory-path inventory.md --validate --json
```

| Exit code | Meaning |
| --- | --- |
| `0` | Valid inventory with all required fields. |
| `1` | Invalid arguments or file not found. |
| `10` | Validation failed: missing required sections. |

> [!WARNING]
> Exit `0` is necessary but not sufficient. The script treats a single `**Prevention:**` line as a mitigation, so a Critical or High risk can pass with an incomplete one. Check by hand that every Critical and High mitigation has Prevention, Detection, and Response.

### Chaining

[`buy-vs-build-framework`](buy-vs-build-framework.md) always runs this skill in its Phase 3 for risk identification. The skill's own related-skill notes say [`decision-critic`](decision-critic.md) is post-decision validation while the pre-mortem is pre-decision. The [`milestone-planner`](../agents/milestone-planner.md) agent can use the output to inform planning, and the [`architect`](../agents/architect.md) agent can take technical risks into ADR considerations.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`decision-critic`](decision-critic.md): stress-tests a single decision after it is made.
- [`threat-modeling`](threat-modeling.md): security-specific threat analysis.
- [`buy-vs-build-framework`](buy-vs-build-framework.md): runs this skill in Phase 3.
- [`milestone-planner`](../agents/milestone-planner.md): uses the output to inform planning.
- Source: [`SKILL.md`](../../src/claude/skills/pre-mortem/SKILL.md)
- Reference: [Gall's Law](../../src/claude/skills/pre-mortem/references/mental-models-galls-law.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
