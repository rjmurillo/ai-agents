# cynefin-classifier

Classifies a problem into a Cynefin domain (Clear, Complicated, Complex, Chaotic, or Confusion) and recommends the response strategy that fits. It stops you from analyzing a problem that needs experiments, or experimenting on one that needs a procedure.

## When to use it

- You are unsure whether to analyze, experiment, or act.
- You face analysis paralysis on a decision.
- Your team disagrees on whether to research more or start building.
- You need to justify an experiment to stakeholders.
- You say `classify this problem`, `cynefin analysis`, `what approach should we take`, `should we analyze or experiment`, or `is this complex or complicated`.

## When not to use it

- You have a concrete proposal to challenge, or a Complicated problem with a decision to validate: use [`decision-critic`](decision-critic.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:cynefin-classifier`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the cynefin-classifier skill to classify this problem: tests pass locally but fail randomly in CI.
```

You get a domain, a confidence level, a rationale, a response strategy, and three recommended actions.

## What you get

| Domain | Cause and effect | Response |
| --- | --- | --- |
| Clear | Obvious to everyone | Sense, categorize, respond. Apply best practice. |
| Complicated | Experts can find it | Sense, analyze, respond. Get expert analysis, then act. |
| Complex | Known only in hindsight | Probe, sense, respond. Run safe-to-fail experiments. |
| Chaotic | No time to analyze | Act, sense, respond. Stabilize first. |
| Confusion | Not enough information | Gather information and reclassify. |

The output has these parts: the restated problem, the domain, confidence (`HIGH`, `MEDIUM`, or `LOW`), a rationale, a response strategy, recommended actions, a pitfall warning, and related considerations (temporal, boundary, compound).

For a compound problem, the skill splits it into sub-problems, classifies each, and orders the work: Chaotic first, then Clear, then Complicated, then Complex.

## Advanced use

Run the classifier from the root of a checkout of this repository:

```bash
uv run python .claude/skills/cynefin-classifier/scripts/classify.py --problem "Choose a queue for the new service" --context "Team of 4, Azure" --json
```

| Flag | Meaning |
| --- | --- |
| `--problem` | Required. Description of the problem. |
| `--context` | Extra context about constraints and environment. |
| `--json` | Output JSON instead of markdown. |

| Exit code | Meaning |
| --- | --- |
| 0 | Classification complete |
| 1 | Invalid arguments |
| 2 | Insufficient information (Confusion domain) |

Exit 2 is a valid Confusion classification when the script printed one and stderr has no `ptk_run:` line. A `ptk_run:` line means the launcher failed and nothing was classified.

Escalate to a human decision-maker when confidence is `LOW`, the problem sits on a domain boundary, stakes are high (production, security, data), the result contradicts team consensus, or a Chaotic problem has no runbook.

The source suggests these handoffs: [`decision-critic`](decision-critic.md) after a Complicated result, the `milestone-planner` agent to design experiments after a Complex result, the `architect` agent for Complicated architecture decisions, and the `analyst` agent for Confusion. [`buy-vs-build-framework`](buy-vs-build-framework.md) runs this skill first when the problem domain is unclear. Three references cover the framework, domain transitions, and software applications.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`buy-vs-build-framework`](buy-vs-build-framework.md): calls this skill when the domain is unclear.
- [`decision-critic`](decision-critic.md): validates a decision after classification.
- [`milestone-planner`](../agents/milestone-planner.md): designs experiments for Complex problems.
- [`analyst`](../agents/analyst.md): investigates Confusion.
- Source: [`SKILL.md`](../../src/claude/skills/cynefin-classifier/SKILL.md)
- References: [`cynefin-deep-dive.md`](../../src/claude/skills/cynefin-classifier/references/cynefin-deep-dive.md), [`domain-transitions.md`](../../src/claude/skills/cynefin-classifier/references/domain-transitions.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
