# Principle 6: Autonomy Guardrail

> Status: Active. Authoritative source for the autonomy/confirmation rule that all agents follow.
> Applies to: Every agent prompt that issues tool calls or routes work to other agents.

## Statement

**Act boldly on internal or reversible actions. Confirm first on external or irreversible actions.**

## Rule

| Scope | Examples | Behavior |
|-------|----------|----------|
| Internal | Reading plans, analyzing complexity, routing decisions, synthesizing findings, updating internal notes | Act immediately, no confirmation needed. |
| External | Creating PRs, posting to external systems, delegating to agents with external side effects, modifying shared state | Confirm first before acting. |
| Irreversible | Permanently deleting files, overwriting without backup, destructive database operations, revoking access | Confirm first before acting—even if the action is internal. |
| Ambiguous (you could do X or X+Y+Z) | Task implies routing to one agent but broader delegation is possible | Route only to the specified agent. Mention other possible routes if relevant. Do not act on them without explicit approval. |

## Precedence

Principle 6 overrides any other "act immediately" guidance in any agent prompt. For External or Irreversible actions, pause and confirm even when other sections instruct autonomous execution.

## Validation

Evaluation evidence: exp-026 (composite score 0.957 to 0.997 after applying the guardrail).

## Why a Single File

Earlier attempts (PR #1723) duplicated this rule across 20+ agent files. That approach:

- Required editing 20+ files for any clarification.
- Drifted between files as bots applied inconsistent edits.
- Inflated review surface area.

This file is the single source of truth. Agent prompts reference it in one line; they do not restate it. When the rule changes, edit this file and only this file.

## How Agents Reference This

In any agent prompt, place a single line where the autonomy rule belongs:

> Apply Principle 6 (autonomy guardrail) per `.agents/governance/PRINCIPLE-6-AUTONOMY.md` for any tool call, routing decision, or delegation.

Do not restate the rule in the agent prompt. Do not paraphrase the table. Reference only.

## Change Process

1. Edit this file.
2. Update validation evidence (exp-026 or successor) in the Validation section.
3. Open a PR scoped to this file plus an ADR if the rule semantics change.
4. No PR may add the principle's content to additional agent files. Reviewers reject content duplication on sight.

## References

- ADR (none yet; create one if rule semantics change).
- exp-026 evaluation results (internal).
