# negotiation agent

The `negotiation` agent analyzes offers and drafts counter-proposals. It works through a five-step protocol called RADAR and hands back a quantified value gap and a draft that needs your approval before anything is sent.

## When to use it

- You are reviewing any offer: real estate, compensation, a vendor contract, or a resource allocation.
- You want to find information asymmetry, anchor manipulation, or a value gap.
- You are asking "should I accept", "review this", or "what's fair".

## When not to use it

- You want the same workflow as a skill: use the [`negotiation`](../skills/negotiation.md) skill instead.
- You want a decision challenged on its assumptions: use [`independent-thinker`](independent-thinker.md) instead.
- You want strategic advice on a business conflict: use [`high-level-advisor`](high-level-advisor.md) instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
negotiation: review the vendor renewal in contracts/acme-renewal.txt and draft a counter
```

In GitHub Copilot CLI:

```bash
copilot --agent negotiation --prompt "review the vendor renewal in contracts/acme-renewal.txt and draft a counter"
```

In VS Code or Visual Studio Copilot Chat:

```text
@negotiation review the vendor renewal in contracts/acme-renewal.txt and draft a counter
```

You can also paste the offer text or describe the situation.

## What you get

Every output includes:

1. The RADAR analysis, all five steps.
2. The value gap in dollar terms.
3. A draft counter, if one applies, marked `DRAFT`.
4. At least one "if they respond with X" scenario.
5. An explicit flag for any irreversible terms.

The analysis block covers ZOPA (the zone of possible agreement), BATNA (each side's best alternative), information asymmetry, and the value gap. Before any recommendation, an "Invisible Disadvantage Check" states whether the offer is acceptable, below market, or above market, and how much it leaves on the table.

A draft counter is headed `DRAFT COUNTER-PROPOSAL` with the status "DRAFT. REQUIRES APPROVAL BEFORE SENDING." It carries analysis notes: the lever used, their likely response, your fallback position, irreversible terms, and concessions.

## Advanced use

The RADAR steps are Read and decode, Analyze, Design the counter, Assess, and Review. In step 1 the agent lists every term, anchor, hedge, urgency cue, and omission. In step 3 it frames counters in three layers: Perception, Context, and Permission. It leads with the higher anchor, bundles terms, and offers options instead of ultimatums.

Rules the agent keeps:

- It never recommends accepting an offer before quantifying the value gap.
- It never calls an offer acceptable without saying what was left on the table.
- It outputs counters only as drafts and needs your approval before sending.
- It flags irreversible terms before any draft is approved.

It also checks for manipulation patterns: artificial urgency, false finality, anchoring, good cop and bad cop, salami slicing, reciprocity traps, and emotional escalation. It can query memories on negotiation theory, behavioral frameworks, and information asymmetry.

> [!NOTE]
> The source says its Project Deal research is internal and cannot be audited. The agent treats the qualitative finding as the rule and the dollar figures as illustrative.

A multi-step prompt:

```text
negotiation: analyze the offer in contracts/acme-renewal.txt with RADAR, quantify the value gap, list irreversible terms, draft a counter with two options, and give me the likely response to each.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`negotiation`](../skills/negotiation.md): the skill form of this workflow.
- [`independent-thinker`](independent-thinker.md): challenges your assumptions about a deal.
- [`high-level-advisor`](high-level-advisor.md): gives a strategic verdict.
- Source template: [`negotiation.shared.md`](../../templates/agents/negotiation.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
