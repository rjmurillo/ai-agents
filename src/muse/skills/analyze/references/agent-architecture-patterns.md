---
source: wiki/concepts/AI Productivity/Agent Architecture Patterns.md
created: 2026-04-11
review-by: 2026-07-11
---

# Agent Architecture Patterns

Narrow agents with clear goals outperform general-purpose agents. Most agent failures are architecture failures, not model failures.

## Skill Budget Rule

Limit each agent to 7-10 skills tied to explicit goals. As skills increase, reliability decreases: context blurs, wrong tools trigger, dependability drops. If a skill does not serve the agent's specific goals, do not add it.

## 6-Step Structured Prompt Design

1. **Core Mission**: ONE primary outcome, explicit scope boundaries
2. **Role Identity**: Specific persona, decision-making style, authority limits
3. **Decision Logic**: 3-5 scenarios with input signal, action, output format, plus "if unclear" fallback
4. **Constraints**: What agent must NEVER do, what requires human review
5. **Output Format**: Structured format, required fields, ambiguous input handling
6. **Escalation Paths**: When to stop, when to pass to human, how to communicate uncertainty

## 3-File Planning Pattern (Context Engineering)

```
task_plan.md   -> phases with checkboxes
findings.md    -> research (not context stuffing)
progress.md    -> session log and test results
```

Agent reads the plan before every decision. This is attention manipulation: re-reading keeps goals in the attention window as context grows.

## MCP Tool Selection Criteria

Tools that stick eliminate repetitive context-stuffing. Skip MCP when CLI already has training coverage (e.g., GitHub CLI vs GitHub MCP). Selection criteria: minimal setup, reliability, continued use after novelty.

## Meta-Rules for Agent Design

- No vague instructions ("be helpful" is banned)
- No capability creep beyond user request
- No nested conditionals beyond 2 levels
- Every constraint must be testable
- Self-contained: no references to prior conversation

## Diagnostic Signals

| Signal | Indicates |
|--------|-----------|
| Wrong tool triggered | Too many skills, context blur |
| Unpredictable branching | Nested conditionals > 2 levels |
| Agent loses track of goals | Missing plan re-read mechanism |
| Low reliability over time | Capability creep, scope expansion |
