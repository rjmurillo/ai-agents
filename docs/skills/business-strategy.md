# business-strategy

Routes a founder problem to the one business framework that fits it. It names the real problem, points you to a single reference, and refuses to guess when the symptom is vague.

## When to use it

- You have a felt problem ("sales are flat", "nobody replies", "I do not know what to build") and do not know which framework applies.
- You need to validate demand, price a product, position it, generate leads, or close deals.
- You say `diagnose my business problem`, `what framework applies`, `validate demand or find customers`, `price or position this`, or `get leads or close deals`.

## When not to use it

- Your problem is software design: use the engineering rules instead.
- You have one named decision to challenge: use [`decision-critic`](decision-critic.md) instead.
- You already know the framework, such as SPIN Selling: skip the router and read that reference directly.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:business-strategy 20 trials started, 1 paid. Why?
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/business-strategy`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /business-strategy skill to ...`.

State the symptom in one sentence with a number. The skill walks the decision tree, picks the earliest broken funnel stage, and reads only the one reference that applies.

## What you get

A diagnosis and a route to one of 14 references, each a distillation of one book:

| Symptom | Reference |
| --- | --- |
| You do not know what to build, or whether anyone wants it | `mom-test.md`, then `four-steps.md` once interviews name a repeatable buyer |
| You can build it but have not proven demand | `lean-startup.md` |
| You cannot say who it is for, or prospects say "interesting" and do nothing | `obviously-awesome.md` |
| You are entering a crowded market | `crossing-the-chasm.md`, then `blue-ocean-strategy.md` if no beachhead gives a defensible position |
| People balk at the price, or you guess the number | `monetizing-innovation.md` |
| The offer feels weak | `100m-offers.md` |
| Traffic is fine but no leads | `100m-leads.md` |
| The words on the page fall flat | `storybrand.md`, then `made-to-stick.md` if the message is clear but not remembered |
| Leads stall, or you lose at the close | `spin-selling.md`, then `influence.md` if discovery is sound |
| You have product-market fit but no growth channel | `traction.md` |

The skill then applies that reference's scored checklist and sets a falsifiable success metric.

## Advanced use

When two symptoms apply, the skill takes the earliest funnel stage. An upstream positioning problem usually causes the downstream messaging or pricing problem.

The process has four steps:

1. State the symptom in one concrete sentence with a number.
2. Walk the tree to the earliest broken stage.
3. Read only the primary reference.
4. Apply its checklist. If it passes and names a follow-up, load the follow-up. Otherwise re-diagnose, because funnels often break in more than one place.

A short self-assessment tells you whether the router is the right entry point. It scores 8 points and passes at 4. Below 4, you probably know your stage, so read the named reference directly.

Limits the source states: a symptom like "we need to grow" routes nowhere. The model assumes one dominant broken stage. The books target early-stage software founders, so regulated, hardware, and enterprise businesses may find routes mis-weighted. The router points and does not execute.

The skill bundles no scripts.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [Optional skill packs](../installation.md#optional-skill-packs): this skill is the `business` pack for a non-marketplace install.
- [`decision-critic`](decision-critic.md): challenges one named decision.
- [`autoplan`](autoplan.md): routes founder business-strategy problems here.
- Source: [`SKILL.md`](../../src/claude/skills/business-strategy/SKILL.md)
- References: [`mom-test.md`](../../src/claude/skills/business-strategy/references/mom-test.md), [`obviously-awesome.md`](../../src/claude/skills/business-strategy/references/obviously-awesome.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
