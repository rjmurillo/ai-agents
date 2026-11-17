# independent-thinker agent

The `independent-thinker` agent is a contrarian analyst. It challenges an assumption with evidence, presents alternatives with trade-offs, says "I don't know" when it lacks evidence, and cites sources.

## When to use it

- You want a devil's advocate on a decision before you commit.
- You want opposing critique, trade-off analysis, or verification instead of agreement.
- A claim sounds obvious and you want it checked.

## When not to use it

- You want a direct verdict on what to do: use [`high-level-advisor`](high-level-advisor.md) instead.
- You want a plan stress-tested for completeness: use [`critic`](critic.md) instead.
- You want one decision's reasoning tested: use the [`decision-critic`](../skills/decision-critic.md) skill instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
independent-thinker: challenge the assumption that we should move all hook scripts from Python to PowerShell
```

In GitHub Copilot CLI:

```bash
copilot --agent independent-thinker --prompt "challenge the assumption that we should move all hook scripts from Python to PowerShell"
```

In VS Code or Visual Studio Copilot Chat:

```text
@independent-thinker challenge the assumption that we should move all hook scripts from Python to PowerShell
```

## What you get

One of three Markdown layouts. The third, the topic analysis, is in the Claude Code version only.

The assumption challenge:

```text
## Assumption Under Challenge
## Evidence For
## Evidence Against
## Alternative Interpretations
## Uncertainty Level
## Recommendation
```

The alternative analysis:

```text
## Current Approach
## Concerns
## Alternatives
## Comparison Matrix
## Verdict
```

The topic analysis:

```text
## Analysis of [Topic]
### Evidence Review
### Alternative Perspectives
### Uncertainty Areas
### Assessment
### Recommendation
```

Every challenge cites evidence or reasoning. The uncertainty level is High, Medium, or Low, with a reason. The agent states its confidence explicitly and uses measured language.

## Advanced use

Core directives: accuracy comes first, and the agent does not agree with a premise automatically. Before it reasons inside a question's frame, it names the implicit frame. It reads the primary source (the spec, the benchmark, the ADR) before the summary, and it cross-checks against materially different sources. It applies the "Is that true?" check hardest to claims that sound most obvious.

It does:

- Ask "What evidence supports this?"
- Present alternatives with trade-offs.
- Say "I don't know" when uncertain.
- Challenge groupthink.

It does not:

- Validate unsupported claims.
- Go along to avoid conflict.
- Guess.
- Be contrarian for its own sake.

It searches memory before analysis and can save learnings under an `analysis/challenge-[topic]` memory name. Serena writes happen only from the checkout Serena started in.

The agent cannot delegate. It returns its assessment to the orchestrator, with a recommended next agent and any areas that need more investigation:

| Target | When | Purpose |
| --- | --- | --- |
| `architect` | Technical alternative needed | Design decision |
| `analyst` | Deep research required | Investigation |
| `orchestrator` | Analysis complete | Continue workflow |
| `critic` | Validate challenge | Second opinion |

A multi-step prompt:

```text
independent-thinker: read ADR-042, list the evidence for and against it, offer two alternatives with a comparison matrix, and tell me whether architect or analyst should go next.
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

- [`high-level-advisor`](high-level-advisor.md): turns analysis into a verdict.
- [`critic`](critic.md): validates your plan or the challenge.
- [`architect`](architect.md): decides on technical alternatives.
- [`analyst`](analyst.md): researches deeper.
- [`decision-critic`](../skills/decision-critic.md): the skill for testing one decision.
- Source template: [`independent-thinker.shared.md`](../../templates/agents/independent-thinker.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
