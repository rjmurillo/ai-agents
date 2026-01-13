# ADR Reference Index

**Purpose**: Quick lookup for Architecture Decision Records
**Location**: `.agents/architecture/ADR-*.md`
**Updated**: 2025-12-28

This is a REFERENCE index, not a skills index. ADRs live in `.agents/architecture/`, not `.serena/memories/`.

## Active ADRs by Topic

### Agent System

| ADR     | Title                                  | Keywords                        |
| ------- | -------------------------------------- | ------------------------------- |
| ADR-002 | Agent Model Selection Optimization     | model haiku sonnet opus routing |
| ADR-003 | Agent Tool Selection Criteria          | tool allocation agent           |
| ADR-007 | Memory-First Architecture              | memory context retrieval        |
| ADR-009 | Parallel-Safe Multi-Agent Design       | parallel worktree isolation     |
| ADR-010 | Quality Gates with Evaluator-Optimizer | quality gate evaluator          |
| ADR-014 | Distributed Handoff Architecture       | handoff session log             |

### CI/CD and Workflows

| ADR | Title | Keywords |
|-----|-------|----------|
| ADR-004 | Pre-Commit Hook as Validation Orchestration | pre-commit hook validation |
| ADR-006 | Thin Workflows, Testable Modules | thin workflow bash module |
| ADR-008 | Protocol Automation via Lifecycle Hooks | protocol automation lifecycle |
| ADR-025 | GitHub Actions ARM Runner Migration | arm runner macos |
| ADR-015 | Artifact Storage Minimization | artifact storage retention |
| ADR-026 | PR Automation Concurrency and Safety | pr automation lock concurrency |
| ADR-016 | Workflow Execution Optimization | workflow cache optimization |

### Standards and Patterns

| ADR | Title | Keywords |
|-----|-------|----------|
| ADR-001 | Markdown Linting Configuration | markdown lint autofix |
| ADR-005 | PowerShell-Only Scripting Standard | powershell ps1 pwsh |
| ADR-017 | Tiered Memory Index Architecture | memory index L1 L2 L3 tier |
| ADR-018 | Cache Invalidation Strategy | cache invalidate TTL session-local cloudmcp |

### Proposed (Not Yet Implemented)

| ADR | Title | Status |
|-----|-------|--------|
| ADR-011 | Session State MCP | Proposed |
| ADR-012 | Skill Catalog MCP | Proposed |
| ADR-013 | Agent Orchestration MCP | Proposed |

## How to Read an ADR

```text
Read(".agents/architecture/ADR-NNN-title.md")
```

## Related Memories

- [adr-014-review-findings](adr-014-findings.md) (analysis of ADR-014)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md) (metrics for ADR-017)

## Related

- [adr-007-augmentation-research](adr-007-augmentation-research.md)
- [adr-014-findings](adr-014-findings.md)
- [adr-014-review-findings](adr-014-review-findings.md)
- [adr-019-quantitative-analysis](adr-019-quantitative-analysis.md)
- [adr-021-quantitative-analysis](adr-021-quantitative-analysis.md)
