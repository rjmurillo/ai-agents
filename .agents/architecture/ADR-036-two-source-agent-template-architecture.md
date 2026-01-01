# ADR-036: Two-Source Agent Template Architecture

## Status

Accepted

## Date

2026-01-01

## Context

The ai-agents system deploys agents to three platforms:

1. **Claude Code** (`src/claude/*.md`)
2. **GitHub Copilot CLI** (`src/copilot-cli/*.agent.md`)
3. **VS Code Copilot** (`src/vs-code-agents/*.md`)

These platforms have different requirements:

- **Claude**: Unique prompts per agent with Claude-specific features (MCP tools, Serena integration)
- **Copilot CLI**: Shared prompts with Copilot-specific frontmatter (model field, tool syntax)
- **VS Code**: Nearly identical to Copilot CLI with minor frontmatter differences

A single-source architecture would require:
- Conditional logic in templates for platform differences
- Complex build transforms
- Difficulty maintaining Claude-specific features

A three-source architecture would require:
- Maintaining 54 files (18 agents x 3 platforms)
- High risk of drift between platforms
- Tedious manual synchronization

## Decision

Adopt a **two-source architecture**:

### Source 1: Claude-Specific (`src/claude/*.md`)

- **Purpose**: Claude Code platform agents
- **Maintenance**: Manual edits only
- **Content**: Claude-specific prompts with unique sections (MCP tools, Serena integration, handoff protocols)
- **Files**: 18 agent files
- **Not Generated**: These files are the authoritative source for Claude

### Source 2: Shared Templates (`templates/agents/*.shared.md`)

- **Purpose**: Source for Copilot CLI and VS Code agents
- **Maintenance**: Manual edits, auto-generates outputs
- **Content**: Shared prompts applicable to both Copilot platforms
- **Files**: 18 template files
- **Generates**: `src/copilot-cli/*.agent.md` and `src/vs-code-agents/*.md` via `build/Generate-Agents.ps1`

### Synchronization Requirement

**CRITICAL**: When adding content that applies to ALL platforms (like the Traceability Validation section), you MUST update BOTH sources:

1. Edit `templates/agents/{agent}.shared.md` (triggers auto-generation for Copilot CLI + VS Code)
2. Edit `src/claude/{agent}.md` (manual update for Claude)

The pre-commit hook handles generation but NOT content synchronization between sources.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Single Source | One file to edit | Complex conditionals, hard to maintain Claude-specific features | Complexity outweighs benefits |
| Three Sources | Full control per platform | 54 files, high drift risk, tedious | Too much maintenance burden |
| Two Sources (chosen) | Balance of control and efficiency | Requires manual sync for shared content | Best trade-off |

### Trade-offs

**Accepted Trade-off**: Manual synchronization of shared content between `src/claude/` and `templates/agents/` is required. This is "toil" but acceptable because:

1. Claude-specific content (MCP tools, Serena) justifies separate source
2. Copilot CLI and VS Code are similar enough to share a source
3. Auto-generation reduces total maintenance from 54 to ~36 manual files
4. Shared content changes are infrequent (governance, validation sections)

## Consequences

### Positive

- Claude agents can have unique features without affecting Copilot platforms
- Copilot CLI and VS Code stay automatically synchronized
- Reduced file count from 54 to 36 (18 Claude + 18 templates)
- Pre-commit hook prevents Copilot platform drift

### Negative

- Shared content must be edited in two places
- Easy to forget updating one source (causes platform drift)
- No automated detection of content desync between sources

### Neutral

- Total agent count unchanged (18 agents x 3 platforms = 54 outputs)
- Build complexity localized to `Generate-Agents.ps1`

## Implementation Notes

### Directory Structure

```text
Source Files (Edit These)
├── src/claude/                         # Claude-specific (18 files)
│   ├── orchestrator.md
│   ├── implementer.md
│   └── ...
└── templates/agents/                   # Shared source (18 files)
    ├── orchestrator.shared.md
    ├── implementer.shared.md
    └── ...

Generated Files (Do Not Edit)
├── src/copilot-cli/                    # Auto-generated (18 files)
│   ├── orchestrator.agent.md
│   └── ...
└── src/vs-code-agents/                 # Auto-generated (18 files)
    ├── orchestrator.md
    └── ...
```

### Synchronization Procedure

When adding shared content (e.g., governance sections, validation checklists):

```bash
# Step 1: Update the shared template
edit templates/agents/{agent}.shared.md

# Step 2: Update Claude source (MANUAL - not auto-synced)
edit src/claude/{agent}.md

# Step 3: Commit (pre-commit auto-generates Copilot outputs)
git add templates/agents/{agent}.shared.md src/claude/{agent}.md
git commit -m "feat(agents): add [feature] to {agent}"
# Pre-commit hook runs Generate-Agents.ps1 and stages outputs
```

### Pre-Commit Hook Behavior

The `.githooks/pre-commit` hook (lines 597-649):

1. Detects staged `templates/agents/*.shared.md` files
2. Runs `build/Generate-Agents.ps1`
3. Stages generated `src/copilot-cli/*.agent.md` and `src/vs-code-agents/*.md`
4. Does NOT sync to `src/claude/` (intentionally separate source)

### Common Mistake

**Anti-pattern**: Editing only `templates/agents/*.shared.md` and forgetting `src/claude/*.md`

**Result**: Claude agents miss the new content; Copilot platforms have it

**Prevention**: When editing shared sections, always grep both sources:

```bash
# Verify section exists in both sources
grep -l "Section Name" templates/agents/{agent}.shared.md src/claude/{agent}.md
```

## Platform Capability Matrix

Platforms have genuinely different capabilities, justifying intentional divergence in agent prompts:

| Capability | Claude Code | Copilot CLI | VS Code Copilot | GitHub Copilot |
|------------|-------------|-------------|-----------------|----------------|
| MCP Tools | ✓ Full | ✗ None | Partial | ✗ None |
| Serena Integration | ✓ Full | ✗ None | ✗ None | ✗ None |
| Multi-Agent Orchestration | ✓ Full | ✓ Full | ✓ Full | ✗ Single-agent only |
| Subagent Invocation | ✓ Task tool | ✓ @agent syntax | ✓ @agent syntax | ✗ Not supported |
| Persistent Memory | ✓ Serena + MCP | ✗ None | ✗ None | ✗ None |

### Intentional Divergence

Claude agents contain Claude-specific sections (MCP tool references, Serena memory protocols, handoff instructions) that have no equivalent on other platforms. Similarity metrics comparing Claude to templates measure divergence that is **BY DESIGN**, not sync failure.

- **Shared content** (governance sections, validation protocols) → MUST remain synchronized
- **Platform-specific content** (tool invocation, capability references) → SHOULD NOT be synchronized

Historical drift analysis showing 2-12% similarity between Claude and templates reflects this intentional platform differentiation, not maintenance failure.

## Strategic Dependency

Issue #124 (P1, opened 2025-12-20) requests strategic decision on whether to continue the two-source pattern documented here. This ADR records the **current architecture**. Issue #124 addresses whether that architecture should evolve.

**Relationship**: Complementary

- **ADR-036**: Documents current state ("What is our architecture?")
- **Issue #124**: Evaluates future state ("Should we change our architecture?")

This ADR does NOT resolve Issue #124. Both documents serve distinct purposes.

## Related Decisions

- ADR-029: Skill File Line Ending Normalization (related build tooling)
- ADR-004: Pre-Commit Hook Architecture (hook framework)

## References

### Implementation Artifacts

- `build/Generate-Agents.ps1`: Generation script for Copilot CLI and VS Code variants
- `.githooks/pre-commit`: Pre-commit hook (lines 597-649) that auto-generates on template changes

### Planning & Design Documents

- `.agents/planning/prd-agent-consolidation.md`: Original PRD defining consolidation approach
- `.agents/planning/implementation-plan-agent-consolidation.md`: Implementation plan details
- `.agents/planning/tasks-agent-consolidation.md`: Task breakdown for consolidation work
- `.agents/architecture/2-variant-consolidation-review.md`: Architecture review of 2-variant approach
- `.agents/roadmap/epic-agent-consolidation.md`: Epic definition for agent consolidation

### Session Documentation

- `.agents/sessions/2025-12-27-session-68-template-sync-check-analysis.md`: Root cause analysis of template sync vs session validation distinction
- `.agents/retrospective/2026-01-01-pr-715-phase2-traceability.md`: Identified synchronization toil pattern

### Serena Memories (Cross-Session Context)

- `prd-agent-consolidation-context`: 2-variant decision rationale, file count reduction (54→36)
- `pattern-agent-generation-three-platforms`: Documents that Claude is NOT auto-generated
- `planning-multi-platform`: Multi-platform deployment context and sync strategy
- `architecture-template-variant-maintenance`: Anti-pattern documentation (assuming Claude is generated)
- `research-agent-templating-2025-12-15`: Initial templating research findings

### Related Pull Requests

- PR #715: Phase 2 Traceability Implementation (identified this architecture as source of synchronization toil)
- PR #235: DevOps review discussing agent generation patterns

---

*Created from learnings in PR #715 Phase 2 Traceability Implementation*
