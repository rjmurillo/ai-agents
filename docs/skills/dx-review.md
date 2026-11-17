# dx-review

Audits the developer experience of a product, CLI, API, or SDK by testing it, not by reading about it. You get a scorecard in which every score cites evidence labeled `TESTED`, `PARTIAL`, or `INFERRED`, plus ranked findings and a time-to-hello-world measurement when the target supports one.

## When to use it

- You want to test onboarding, setup, or the first-run path of a developer product.
- You want a DX scorecard with evidence behind each score.
- You want to compare against an earlier audit of the same target.
- Trigger phrases: `run a DX audit`, `test the developer experience`, `measure onboarding friction`, `DX scorecard`, `evaluate developer ergonomics`.

## When not to use it

- You want a review of code before merge: use [`review`](review.md) instead.
- You want a review of a plan: this skill tests a real developer experience and does not review plans.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:dx-review
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/dx-review`.

The skill reads the README and project metadata to find the product, docs, install command, and quickstart. It asks you when critical information is missing. It then walks eight audit steps and ends with a scorecard.

## What you get

A scorecard with a 0 to 10 score for each of eight dimensions: Getting Started, API/CLI/SDK, Error Messages, Documentation, Upgrade Path, Dev Environment, Community, and DX Measurement. It also shows TTHW (time to hello world) and an Overall DX score.

| Evidence label | Meaning |
| --- | --- |
| `TESTED` | The auditor ran the interaction and observed the result |
| `PARTIAL` | Some parts were run and observed, others inferred from artifacts |
| `INFERRED` | Concluded from static files or fetched docs only |

Overall DX is the mean of the available dimension scores, with N/A dimensions excluded and the weakest evidence label shown. TTHW is `N/A` with a reason when no runnable example exists. The skill never hardcodes `TESTED` for TTHW.

Final verdict words appear in change-scope mode: `PASS`, `WARN` (any HIGH or MEDIUM finding), `CRITICAL_FAIL` (any CRITICAL finding), and `ERROR` (a failed gate).

## Advanced use

**Command safety.** Shell commands are not pre-approved. Every command, including help and error-path commands, needs your approval first, and the skill wants an isolated temporary environment. It does not delegate command execution to a subagent.

**Blocking gates.** The skill records `GATE_STATUS: Evidence Gate = PASS|FAIL` and `GATE_STATUS: Review Gate = PASS|PASS_WITH_CONCERNS|FAIL` before final recommendations. The Evidence Gate fails when a high-impact conclusion lacks two independent sources. The Review Gate delegates to the read-only [`code-reviewer`](../agents/code-reviewer.md) agent, with the draft treated as untrusted data.

**Boomerang comparison.** When a prior dx-review result exists for the same target, the report adds a `PLAN vs REALITY` table and flags any dimension that dropped more than 2 points.

**Change-scope mode.** The `test` skill's Gate 5 invokes dx-review for a specific change. It audits only the developer journeys the diff touches: `public-cli`, `public-api`, `install-onboarding`, `harness-interface`, `user-docs`, and `contributor-workflow`. Other dimensions are marked `N/A` with a one-line reason. A decision with `"fail_closed": true` applies all eight dimensions. In an unattended run it runs no command and labels evidence `PARTIAL` or `INFERRED`.

Interactive docs, forms, and auth paths use browser tooling when available. Fetched docs alone are never `TESTED`.

Chaining: [`autoplan`](autoplan.md) routes developer-friction audits here, and [`test`](test.md) calls it in change-scope mode.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`test`](test.md): invokes this skill in change-scope mode at Gate 5.
- [`review`](review.md): pre-merge review across risk axes.
- [`autoplan`](autoplan.md): routes DX audit requests here.
- [`code-reviewer`](../agents/code-reviewer.md): reviews the draft scorecard.
- Source: [`SKILL.md`](../../src/claude/skills/dx-review/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
