# AI Agents Enhancement Session

Read the contents of the `.agents` directory before starting work:

1. **FIRST**: Read `.agents/AGENT-SYSTEM.md` - agent catalog and protocols
2. **SECOND**: Read `.agents/AGENT-INSTRUCTIONS.md` - task execution protocol
3. **THIRD**: Read `.agents/HANDOFF.md` - previous session context
4. **FOURTH**: Read `.agents/planning/enhancement-PROJECT-PLAN.md` - project phases and tasks

## Project Context

- **Repository**: rjmurillo/ai-agents
- **Branch**: `main` (create feature branches per phase)
- **Goal**: Reconcile Kiro planning patterns, Anthropic agent patterns, and existing implementation
- **Timeline**: 12-18 sessions across 6 phases

## Key Enhancements

1. **Spec Layer**: 3-tier hierarchy (requirements → design → tasks) with EARS format
2. **Traceability**: Cross-reference validation between artifacts
3. **Parallel Execution**: Fan-out/fan-in for multi-agent work
4. **Steering Scoping**: Context-aware prompt injection
5. **Evaluator-Optimizer**: Formal regeneration loop

## Session Protocol

1. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.md`
2. Review HANDOFF.md for previous session state
3. Identify current phase and next task from PROJECT-PLAN.md
4. Delegate task to orchestrator agent with full context
5. Create feature branch if starting new phase: `feat/phase-N-description`
6. Work incrementally with small, conventional commits
7. Check off tasks in PROJECT-PLAN.md as completed
8. Update session log with decisions and challenges
9. Before completing, invoke retrospective agent
10. Update HANDOFF.md with session summary

## Build Commands

```powershell
# Validate markdown
npx markdownlint-cli2 --fix "**/*.md"

# Format code (if any)
dotnet format

# Run any validation scripts
./scripts/Validate-Traceability.ps1 -WhatIf  # Once created
```

## Agent Invocation Pattern

When delegating to orchestrator, provide:

```text
@orchestrator

## Task
[Specific task from PROJECT-PLAN.md]

## Context
- Phase: [N]
- Task ID: [ID]
- Dependencies: [Completed dependencies]

## Acceptance Criteria
[From PROJECT-PLAN.md]

## Constraints
- Follow existing agent prompt patterns in src/claude/
- Maintain consistency with AGENT-SYSTEM.md
- Use YAML front matter for all new spec files
- Document all decisions in session log
```

## Current State

Review HANDOFF.md for:
- Last completed phase/task
- Open issues or blockers
- Files changed in previous session
- Recommended next steps

Continue with the next task from PROJECT-PLAN.md based on phase priorities.
