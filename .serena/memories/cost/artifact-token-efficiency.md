# Artifact Token Efficiency

## Principle

When writing artifacts that will be consumed later (ADRs, plans, specs), minimize token waste.

## Anti-Patterns

- Strikethrough text (~~example~~) - no-op context
- Verbose explanations when concise suffices
- Redundant information repeated across sections
- Decorative formatting that doesn't aid comprehension

## Why It Matters

- ADRs are read frequently by AI agents
- Every token in the document costs API budget
- Wasted tokens compound across sessions
- Clean, concise artifacts improve reasoning quality

## Source

Session 129 adr-review feedback: "you don't need to strike out. The ADR is read often by AI and that is no-op context that wastes tokens"

## Applies To

- ADRs (`.agents/architecture/`)
- Plans (`.agents/planning/`)
- Specs (`.agents/specs/`)
- Session logs (`.agents/sessions/`)
- Any artifact consumed by agents
