# Session 24: Component AGENTS.md Documentation

**Date**: 2025-12-18
**Branch**: `feat/ai-agent-workflow`
**Agent**: orchestrator (Claude Opus 4.5)

## Objective

Crawl the repository, extract knowledge from memories, and generate `AGENTS.md` files for each logical component documenting all automated actors (agents) that operate as part of that component.

## Protocol Compliance

### Phase 1: Serena Initialization

- [x] `mcp__serena__activate_project` - Completed
- [x] `mcp__serena__initial_instructions` - Completed

### Phase 2: Context Retrieval

- [x] Read `.agents/HANDOFF.md` - Completed
- [x] Read relevant memories:
  - `codebase-structure` - Repository structure overview
  - `project-overview` - Project purpose and agent catalog
  - `code-style-conventions` - Documentation standards
  - `install-scripts-cva` - Installation script patterns
  - `research-agent-templating-2025-12-15` - Template system research
  - `epic-2-variant-consolidation` - Consolidation strategy

### Phase 3: Session Log

- [x] Created this session log

## Identified Logical Components

Based on repository analysis:

| Component | Path | Description |
|-----------|------|-------------|
| Templates | `templates/` | Source of truth for shared agent definitions |
| Build | `build/` | Agent generation and drift detection scripts |
| Scripts | `scripts/` | Installation and utility scripts |
| GitHub | `.github/` | Workflows, actions, and CI/CD automation |

## Key Conventions Discovered

1. **Template System**: `templates/agents/*.shared.md` is the SOURCE OF TRUTH
2. **Generation Flow**: `build/Generate-Agents.ps1` transforms templates into platform-specific outputs
3. **Claude Maintained Separately**: `src/claude/` is NOT generated from templates
4. **Drift Detection**: Weekly CI checks for semantic drift between Claude and generated agents

## Deliverables

- [x] `templates/AGENTS.md` - Template system agents documentation
- [x] `build/AGENTS.md` - Build automation agents documentation
- [x] `scripts/AGENTS.md` - Installation automation agents documentation
- [x] `.github/AGENTS.md` - GitHub Actions agents documentation

## Progress Log

### Phase 1: Repository Exploration

- Explored directory structure using `mcp__serena__list_dir`
- Identified 4 logical components with automated actors
- Read existing `AGENTS.md` and `templates/README.md` for patterns
- Read memories: `codebase-structure`, `project-overview`, `code-style-conventions`, `install-scripts-cva`, `research-agent-templating-2025-12-15`, `epic-2-variant-consolidation`

### Phase 2: Documentation Generation

Generated AGENTS.md files for each component:

1. **templates/AGENTS.md** - Documents the 18 AI agent templates, platform configurations, transformation process, and Mermaid architecture diagrams
2. **build/AGENTS.md** - Documents build scripts (Generate-Agents, Detect-AgentDrift, Validate-PlanningArtifacts, Validate-PathNormalization, Invoke-PesterTests), their inputs/outputs, invocation, and monitoring
3. **scripts/AGENTS.md** - Documents installation scripts (install.ps1, legacy wrappers), utility scripts (Sync-McpConfig, Check-SkillExists, Validate-Consistency, Validate-SessionProtocol), shared library functions, and testing
4. **.github/AGENTS.md** - Documents GitHub Actions workflows (ai-pr-quality-gate, ai-issue-triage, ai-session-protocol, ai-spec-validation, drift-detection, validate-*, pester-tests), composite actions, and prompt templates

## Files Created

| File | Lines | Description |
|------|-------|-------------|
| `templates/AGENTS.md` | ~180 | Template system and AI agent catalog |
| `build/AGENTS.md` | ~220 | Build automation scripts |
| `scripts/AGENTS.md` | ~290 | Installation and utility scripts |
| `.github/AGENTS.md` | ~340 | GitHub Actions workflows and actions |

## Key Patterns Applied

1. **Mermaid Diagrams**: Each AGENTS.md includes architecture flowcharts and sequence diagrams
2. **Agent Catalog Tables**: Comprehensive tables of agents/scripts with attributes
3. **Input/Output Documentation**: Clear specification of inputs, outputs, triggers
4. **Error Handling**: Documented error scenarios and behaviors
5. **Security Considerations**: Security controls per component
6. **Monitoring**: CI workflows and validation mechanisms
7. **Cross-References**: Links between component AGENTS.md files

## Notes

- The existing root `AGENTS.md` documents AI agent usage instructions
- Component-level `AGENTS.md` files document automated actors within each component
- Claude agents (`src/claude/`) are maintained separately (not generated from templates)
- Drift detection monitors consistency between Claude and generated agents
