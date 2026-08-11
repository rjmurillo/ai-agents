# Claude Code Instructions

@AGENTS.md

## Claude Code Specifics

For non-trivial tasks, delegate to specialized agents via Task tool:

- `Task(subagent_type="orchestrator")` for multi-step coordination
- `Task(subagent_type="Explore")` for codebase exploration
- Specialized agents (implementer, architect, analyst, etc.) for focused work

## Path-scoped instructions

Claude scopes rules only with `paths`. Source `applyTo` and `alwaysApply` are
legacy keys that load unconditionally. Generated Copilot mirrors use `applyTo`.

## Skill routing

Explicit skill invocations still win: when the request names an available skill or uses that skill's slash command, invoke that skill first. Concrete requests that name no skill go through `/autoplan` below.

`/autoplan` is the canonical intent router for concrete requests that name no skill, per ADR-078. It routes to skills, lifecycle commands, and agent handoffs (for example orchestrator for multi-step work), not skills alone. Keep the routing table in `.claude/skills/autoplan/SKILL.md`; do not duplicate it here.

Explicit routing not owned by `autoplan`: weekly retros invoke `reflect`.
