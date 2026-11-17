# negotiation

Analyzes an offer and drafts a counter-proposal. It quantifies the value gap in dollars, applies the RADAR protocol, and returns a draft counter that waits for your approval.

## When to use it

- You are reviewing any offer: real estate, compensation, vendor contract, or resource allocation.
- You are designing how an agentic system should analyze and counter-propose.
- You say `review this offer`, `analyze counter`, `value gap`, `draft counter`, `should I walk`, or `anchor first or wait`.

## When not to use it

- Your question is descriptive, such as "explain how anchoring works": ask for a plain answer, not the skill.
- The artifact is not an offer or counter, such as a status update: do not use this skill.
- You need broader business strategy: use [`business-strategy`](business-strategy.md) instead. It routes deal and offer analysis here.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:negotiation`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the negotiation skill to review this job offer and draft a counter. Base is 180k, my target is 205k, and I have a competing offer at 195k.
```

The agent works through the five RADAR phases and ends with a counter-proposal marked DRAFT. Nothing is sent until you approve it.

## What you get

A marked-DRAFT counter-proposal with an explicit human approval gate. The output is acceptable when it meets these checks:

- Offer net value, achievable value, and the gap are quantified in dollars.
- At least one written-signal observation is cited when the offer arrived in writing.
- The counter carries PCP framing (Perception, Context, Permission), not just a number.
- A BATNA worksheet is filled before the first counter goes out.
- No single-dimension concession appears in the counter (the bundling rule).
- The final output is marked DRAFT and waits for explicit human approval.
- If routed through an agentic system, the analysis runs on a senior-tier model.

## Advanced use

### The RADAR protocol

Apply the phases in order. Skipping a step is the most common failure mode.

| Phase | Name | What happens |
| --- | --- | --- |
| 1 | Read | Extract every term. List anchors, hedging, urgency signals, and omissions. Do not interpret yet. |
| 2 | Analyze | Map ZOPA, BATNA, information asymmetry, and the value gap. Quantify the gap in dollars before any qualitative language. |
| 3 | Design | Draft PCP framing before producing a number. |
| 4 | Assess | Run the invisible-disadvantage check. Compare the risk of countering with the risk of accepting. Apply the anchor-first decision rule and BATNA discipline. |
| 5 | Review | Produce a DRAFT counter with a human approval gate. Apply the closing pattern once verbal agreement is reached. |

### Anti-patterns the skill guards against

- **Reactive countering:** producing a number before Read and Analyze are done.
- **Single-dimension concessions:** trading price without extracting value elsewhere.
- **Matching urgency:** accepting tactical deadlines as genuine.
- **Mid-negotiation BATNA drift:** relaxing the walkaway under sunk-cost pressure. Pre-commit in writing and require a 24-hour delay for any change.
- **Routing to a junior model:** model capability is the variable that consistently changes outcomes.
- **Verbal-only close:** confirm in writing within one hour.

### Extension points

- A new domain such as insurance or M&A gets its own reference file under `references/`. Do not edit the canonical skill list.
- The PCP framing, the comfort and discomfort signal table, and the BATNA worksheet can be swapped through a sibling reference.
- When you wire the skill into an agentic system, set `model_tier: opus` (or an equivalent senior tier) in the agent template.

The full set of ten crystallized skills, with implementation patterns and evidence citations, is in the [`references/skills.md`](../../src/claude/skills/negotiation/references/skills.md) file. The skill has no scripts.

### Chaining

[`business-strategy`](business-strategy.md) routes deal and offer analysis requests to this skill. A [`negotiation` agent](../agents/negotiation.md) also exists for the same work.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`business-strategy`](business-strategy.md): routes deal and offer analysis to this skill.
- [`negotiation` agent](../agents/negotiation.md): the agent form of the same analysis.
- Source: [`SKILL.md`](../../src/claude/skills/negotiation/SKILL.md)
- Reference: [Crystallized skills](../../src/claude/skills/negotiation/references/skills.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
