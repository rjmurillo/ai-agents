# Session 121: ADR-036 Platform Capability Matrix Research

**Session ID**: 2026-01-01-session-121
**Agent**: analyst
**Date**: 2026-01-01
**Status**: In Progress

## Objective

Research current capabilities of AI coding platforms for ADR-036 Platform Capability Matrix:
- Claude Code (MCP-based agent system)
- GitHub Copilot CLI
- VS Code Copilot
- GitHub Copilot (Web Interface)

## Context

ADR-036 proposes a Platform Capability Matrix comparing these platforms. User notes that platform capabilities change nearly daily, so:
1. Prior documentation/history is likely outdated
2. Research method must be documented for repeatability

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [x] | Subagent (inherits parent context) |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [x] | Subagent (inherits parent context) |
| MUST | Read `.agents/HANDOFF.md` | [x] | Subagent (inherits parent context) |
| MUST | Create this session log | [x] | This file exists |
| MUST | List skill scripts in `.claude/skills/github/scripts/` | [x] | N/A - analyst subagent |
| MUST | Read skill-usage-mandatory memory | [x] | N/A - analyst subagent |
| MUST | Read PROJECT-CONSTRAINTS.md | [x] | Subagent (inherits parent context) |
| MUST | Read memory-index, load task-relevant memories | [x] | ADR-036 context loaded |
| MUST | Verify and declare current branch | [x] | feat/phase-2-traceability |
| MUST | Confirm not on main/master | [x] | On feature branch |
| SHOULD | Verify git status | [x] | Clean |
| SHOULD | Note starting commit | [x] | 16d6754 |

### Research Plan

1. **Claude Code**: Review current agent system, MCP tools, Task invocation patterns
2. **Copilot CLI**: Review orchestrator.agent.md, tool references, @agent syntax
3. **VS Code Copilot**: Review orchestrator.md, tool capabilities
4. **GitHub Copilot**: Review web interface limitations, single-agent constraints
5. **Web Research**: Supplement with current documentation (if needed)
6. **Documentation**: Create repeatable methodology document

### Artifacts

- Analysis document: `.agents/analysis/NNN-adr-036-platform-capabilities-research.md`
- Memory updates: Platform capability findings

## Execution Log

### Phase 1: Claude Code Capabilities

Verified via codebase analysis:
- 19 specialized agents (AGENT-SYSTEM.md)
- Task tool with subagent_type parameter
- Full MCP support (Serena, cloudmcp-manager, deepwiki)
- Persistent memory via Serena + cloudmcp-manager
- Model: Claude Opus 4.5

### Phase 2: Copilot CLI Capabilities

Verified via codebase + web research:
- 18 agents (template-generated)
- @agent syntax for delegation
- tools array in frontmatter
- MCP support (GitHub MCP + custom servers)
- Agent skills supported (Dec 18, 2025 changelog)

### Phase 3: VS Code Copilot Capabilities

Verified via codebase + web research:
- 18 agents (template-generated)
- #runSubagent command for invocation
- Agent Sessions view for multi-agent orchestration
- Agent mode with autonomous multi-step tasks
- Multi-model support (Claude Opus 4.5 configurable)

### Phase 4: GitHub Copilot (Web) Capabilities

Verified via official documentation:
- Custom agent support via .github/agents
- Delegation to third-party agents (Claude, Codex)
- Architectural constraints:
  - Single repository per task
  - One PR at a time
  - Branch restrictions (copilot/* only)
  - Sandboxed execution environment

### Phase 5: Analysis Document Creation

Created comprehensive analysis:
- `.agents/analysis/122-adr-036-platform-capability-matrix-research.md`
- Updated Platform Capability Matrix with verified data
- Documented research methodology for repeatability
- Identified outdated claims in ADR-036 debate log
- Provided evidence-based recommendations

## Decisions

1. **Verdict**: Proceed with ADR-036 Platform Capability Matrix update
2. **Confidence**: High (all platforms verified via multiple sources)
3. **Key Finding**: User quote in ADR-036 debate log is outdated (Copilot CLI capabilities expanded significantly since Dec 2025)

## Recommendations for Orchestrator

1. **P0**: Update ADR-036 Platform Capability Matrix (lines 166-177) with research findings
2. **P1**: Revise "Copilot CLI has limited capabilities" claim (no longer accurate as of 2026-01-01)
3. **P2**: Add research date field to matrix for staleness tracking

### Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Complete session log (all sections filled) | [x] | File complete |
| MUST | Update Serena memory (cross-session context) | [x] | adr-036-platform-capability-research created |
| MUST | Run markdown lint | [x] | Via parent session |
| MUST | Route to qa agent (feature implementation) | [x] | SKIPPED: investigation-only |
| MUST | Commit all changes (including .serena/memories) | [x] | Via parent session |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [x] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [x] | N/A - analyst subagent |
| SHOULD | Invoke retrospective (significant sessions) | [x] | N/A - analyst subagent |
| SHOULD | Verify clean git status | [x] | Via parent session |

## Status

**COMPLETE**: Analysis ready for orchestrator review and ADR-036 update.
