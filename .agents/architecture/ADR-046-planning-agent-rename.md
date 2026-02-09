# ADR-046: Planning Agent Rename for Role Clarity

## Status

Accepted

## Date

2026-02-08

## Context

The agent system has three planning-related agents with confusingly similar names:

1. **planner** - Translates roadmap epics into implementation-ready milestones
2. **task-generator** - Decomposes PRDs and epics into atomic work items
3. **task-planner** - Proactively analyzes project state and creates backlog items

The naming overlap creates routing ambiguity risk. "Planner" and "task-planner" differ by a single prefix. "Task-generator" and "task-planner" both start with "task-" but serve opposite purposes (reactive decomposition vs. proactive discovery). This is a preventive rename to eliminate structural ambiguity before it causes incorrect agent invocation, rather than a reaction to observed confusion. The risk is highest for new users and orchestrator routing decisions.

PR #1101 introduced the task-planner agent but it was not integrated into the build system (no shared template exists in `templates/agents/`). This provides a natural opportunity to rename all three agents while completing the integration.

## Decision

Rename all three planning agents to reflect their distinct roles:

| Current Name | New Name | Role |
|---|---|---|
| planner | **milestone-planner** | Translates epics into milestones with acceptance criteria |
| task-generator | **task-decomposer** | Breaks PRDs into atomic, estimable work items |
| task-planner | **backlog-generator** | Proactively discovers work from project state analysis |

**Note**: The `.claude/skills/planner/` directory is an interactive planning skill, not the planner agent definition. It retains its current name and is unaffected by this rename.

## Rationale

### Naming Principles Applied

1. **Action-object pattern**: Each name pairs what the agent does with what it produces.
   - milestone-planner plans milestones
   - task-decomposer decomposes tasks
   - backlog-generator generates backlog items

2. **No shared prefix**: Eliminates the "planner/task-planner" collision and the "task-generator/task-planner" collision.

3. **Self-documenting**: A new user can infer each agent's purpose from its name alone.

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| Keep current names, add documentation | Zero migration cost | Does not solve routing ambiguity | Ambiguity persists regardless of docs |
| planner -> epic-planner | Describes input | "Epic" is one input type; agent also handles features | Too narrow |
| task-generator -> task-splitter | Simple, descriptive | "Splitter" implies mechanical division | "Decomposer" captures analysis aspect |
| task-planner -> backlog-planner | Consistent -planner suffix | Three agents ending in -planner recreates confusion | Defeats purpose |

### Trade-offs

- **Migration cost**: ~150 files require updates across templates, generated output, documentation, and configuration. (Estimated via `git diff --stat` on the rename branch; actual count verified during implementation.)
- **Muscle memory**: Users accustomed to `planner` must learn `milestone-planner`.
- **Benefit**: Permanent elimination of naming ambiguity across the agent system.
- **Reversibility**: A single `git revert` of the rename commit restores all files. Historical records (session logs, archives) are unaffected.

## Consequences

### Positive

- Orchestrator routing becomes unambiguous for planning-related tasks
- New users can identify the correct agent without reading documentation
- Build system integration for backlog-generator closes the PR #1101 gap
- Consistent action-object naming pattern established for future agents

### Negative

- One-time migration of ~150 files
- Existing session logs and archived documents retain old names (acceptable, historical record)
- External references to old names (if any) will break

### Neutral

- The `planner` skill (`.claude/skills/planner/`) is a separate interactive planning workflow, not the agent definition. It retains its name and functionality.
- Archive and session history files are not updated (they are historical records)

## Implementation Notes

### Scope of Changes

1. **Template files** (`templates/agents/`): Rename shared sources, update content
2. **Generated files** (`src/`, `.github/agents/`): Regenerate via `Generate-Agents.ps1`
3. **Claude Code agents** (`.claude/agents/`): Rename and update frontmatter
4. **Documentation** (`AGENTS.md`, `SKILL-QUICK-REF.md`, `CRITICAL-CONTEXT.md`, etc.)
5. **Configuration** (`.github/labeler.yml`, workflows, copilot instructions)
6. **Orchestrator routing** (all orchestrator.md variants)
7. **Governance documents** (`.agents/governance/naming-conventions.md`)

### Excluded from Rename

Historical documents retain old names as artifacts of their creation time:

- Archive files (`.agents/archive/`)
- Session logs (`.agents/sessions/`)
- Planning documents (`.agents/planning/`)
- Analysis documents (`.agents/analysis/`)
- Retrospective documents (`.agents/retrospective/`)
- Specification documents (`.agents/specs/`)
- Git branch names (e.g., `feat/task-planner-agent` is merged)

Serena memories (`.serena/memories/`) will be updated organically in future sessions.

### Verification

After rename, run:

```bash
pwsh build/Generate-Agents.ps1 -Validate
```

All generated files must match committed files.

## Related Decisions

- ADR-036: Two-source agent template architecture (defines the template/generated file split)
- ADR-039: Agent model cost optimization (agent naming affects routing)

## References

- PR #1101: Introduced task-planner agent
- `.agents/governance/naming-conventions.md`: Artifact naming patterns
