# prompt-engineer

Improves a system prompt for an agent using documented prompt engineering patterns. You review each proposed change as a card with the problem, the technique, and a before and after, and you approve before anything is applied.

## When to use it

- You have a prompt, tool instruction, or agent system prompt and want it improved, refined, or reviewed.
- Trigger phrases: `optimize this prompt`, `improve this system prompt`, `review my agent prompt`, `refine this prompt for better results`, `make this prompt more effective`.

## When not to use it

- You want to write a prompt from scratch.
- The prompt already works and you only want validation.
- The content is not a prompt, such as documentation or code.
- You want a measured, eval-gated improvement of a skill or prompt: use [`skillopt`](skillopt.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:prompt-engineer`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the prompt-engineer skill to improve the system prompt in .claude/agents/triage.md.
```

The skill reads its pattern references, analyzes the prompt, and shows you a plan. It waits for your approval, applies the approved changes, and presents the complete optimized prompt.

## What you get

- A plan of visual cards. Each card shows scope, problem, technique, and a BEFORE and AFTER, and quotes the trigger condition from the reference.
- After you approve, the changed prompt with a coherence check and an anti-pattern check.
- A completion checklist: every change traces to a documented pattern, no section contradicts another, and no more than 3 emphasis markers remain.

## Advanced use

Phases:

| Phase | Work |
| --- | --- |
| 0 Triage | Under 20 lines with one purpose and no conditionals uses a lightweight pass; anything else uses the full process |
| 1 Understand | Operating context, current state, problems quoted from the prompt |
| 2 Plan | Visual cards; you approve here, once |
| 3 Execute | Apply the approved before and after changes |
| 4 Integrate | Check cross-section coherence and anti-patterns, then present the final prompt |

The skill always reads `references/prompt-engineering-single-turn.md`. It reads `references/prompt-engineering-multi-turn.md` only when the prompt involves multi-turn flows or sub-agent orchestration. `references/workflow.md` holds the phase detail and the card template.

Principles it follows: quote the reference's trigger condition before you pick a technique, ask open verification questions ("what behavior will this produce?"), and preserve what already works. It rewrites problems, not the whole prompt.

It stays explicit-only because a prompt rewrite changes agent behavior.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skillopt`](skillopt.md): measured improvement against an eval set.
- [`skillforge`](skillforge.md): create or improve skills.
- [`prose-self-check`](prose-self-check.md): check your own prose for AI vernacular.
- Source: [`SKILL.md`](../../src/claude/skills/prompt-engineer/SKILL.md)
- Single-turn patterns: [`prompt-engineering-single-turn.md`](../../src/claude/skills/prompt-engineer/references/prompt-engineering-single-turn.md)
- Anti-patterns: [`prompting-anti-patterns.md`](../../src/claude/skills/prompt-engineer/references/prompting-anti-patterns.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
