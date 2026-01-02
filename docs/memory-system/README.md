# Memory System Documentation

## Overview

The ai-agents memory system (v0.2.0) is a four-tier architecture designed for efficient knowledge retrieval and causal reasoning. This is the third iteration of memory systems in the project, combining lexical search, semantic search, episodic replay, and causal analysis.

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Working Memory (Tier 0)                   │
│         Current context window, recent interactions          │
│                    (Managed by Claude)                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Semantic Memory (Tier 1)                   │
│          Facts, patterns, rules - Serena + Forgetful         │
│                    (ADR-037 Memory Router)                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                   Episodic Memory (Tier 2)                   │
│      Session transcripts, decision sequences, outcomes       │
│               (.agents/memory/episodes/)                     │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                    Causal Memory (Tier 3)                    │
│        Cause-effect graphs, counterfactual analysis          │
│              (.agents/memory/causality/)                     │
└─────────────────────────────────────────────────────────────┘
```

### Tier 0: Working Memory

Current context window managed by Claude. Contains recent interactions and active task context.

**Scope**: Last few turns of conversation (typically 8-20K tokens)

### Tier 1: Semantic Memory

Persistent knowledge base with two subsystems:

| System | Type | Storage | Query Method |
|--------|------|---------|--------------|
| **Serena** | Lexical | `.serena/memories/*.md` | Keyword matching |
| **Forgetful** | Semantic | Vector DB (HTTP MCP) | Embedding similarity |

**Access**: Unified via Memory Router (ADR-037)

**Content**: 460+ memories covering PowerShell patterns, Git workflows, agent protocols, and project learnings.

### Tier 2: Episodic Memory

Structured extracts from session logs optimized for replay and analysis.

**Storage**: `.agents/memory/episodes/{session-id}.json`

**Content**: Decision sequences, events, outcomes, and metrics from past sessions.

**Use Cases**:

- Review past decisions and their outcomes
- Identify what worked and what failed
- Compare similar scenarios across sessions

### Tier 3: Causal Memory

Cause-effect relationship graph built from episodic data.

**Storage**: `.agents/memory/causality/causal-graph.json`

**Content**: Nodes (decisions, events, outcomes), edges (causal relationships), and patterns (recurring sequences).

**Use Cases**:

- Trace root causes of failures
- Identify high-success patterns
- Perform what-if analysis

## Key Components

### Memory Router (.claude/skills/memory/scripts/MemoryRouter.psm1)

Unified search interface across Serena and Forgetful.

**Routing Strategy**: Serena-first with Forgetful augmentation

```powershell
# Unified search (Serena + Forgetful)
Search-Memory -Query "PowerShell arrays" -MaxResults 10

# Lexical only (Serena)
Search-Memory -Query "git hooks" -LexicalOnly

# Semantic only (Forgetful, requires MCP running)
Search-Memory -Query "authentication patterns" -SemanticOnly
```

**See**: [Memory Router Documentation](memory-router.md)

### Reflexion Memory (.claude/skills/memory/scripts/ReflexionMemory.psm1)

Episodic replay and causal reasoning capabilities.

```powershell
# Episode queries
Get-Episode -SessionId "2026-01-01-session-126"
Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-7)

# Causal queries
Get-CausalPath -FromLabel "decision" -ToLabel "outcome"
Get-Patterns -MinSuccessRate 0.7
```

**See**: [Reflexion Memory Documentation](reflexion-memory.md)

## Performance

### Benchmarking

Use `.claude/skills/memory/scripts/Measure-MemoryPerformance.ps1` to benchmark memory search performance:

```powershell
# Run default benchmarks
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1

# Custom queries with more iterations
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1 -Queries @("PowerShell arrays") -Iterations 10

# Markdown report
pwsh .claude/skills/memory/scripts/Measure-MemoryPerformance.ps1 -Format markdown
```

**See**: [Benchmarking Documentation](benchmarking.md)

### Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| Serena search | 530ms | 530ms (baseline) |
| Router overhead | <50ms | Pending validation |
| Total latency | <700ms | Pending validation |
| Availability | 100% | 100% (Serena always available) |

**Target**: 96-164x faster than claude-flow baseline for equivalent operations.

## Quick Start

### For Agents

```powershell
# Search memory before making decisions
$results = Search-Memory -Query "relevant topic" -MaxResults 5

# Review past failures
$episodes = Get-Episodes -Outcome "failure" -Since (Get-Date).AddDays(-30)

# Check for known patterns
$patterns = Get-Patterns -MinSuccessRate 0.7
```

### For Humans

```bash
# Search memory via skill
pwsh .claude/skills/memory/scripts/Search-Memory.ps1 -Query "git hooks" -Format Table

# Check memory system status
pwsh -c "Import-Module .claude/skills/memory/scripts/MemoryRouter.psm1; Get-MemoryRouterStatus"
pwsh -c "Import-Module .claude/skills/memory/scripts/ReflexionMemory.psm1; Get-ReflexionMemoryStatus"
```

## Architecture Decision Records

This memory system is defined by two ADRs:

- **ADR-037**: Memory Router Architecture (Tier 1 - Serena/Forgetful integration)
- **ADR-038**: Reflexion Memory Schema (Tiers 2 & 3 - Episodes and causality)

**Location**: `.agents/architecture/`

## Documentation Structure

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](README.md) | This overview | All |
| [quick-start.md](quick-start.md) | Common usage patterns | All |
| [memory-router.md](memory-router.md) | Memory Router (Tier 1) | Developers |
| [reflexion-memory.md](reflexion-memory.md) | Reflexion Memory (Tiers 2 & 3) | Developers |
| [api-reference.md](api-reference.md) | Complete API documentation | Developers |
| [agent-integration.md](agent-integration.md) | Agent workflow integration | AI Agents |
| [skill-reference.md](skill-reference.md) | Skill script documentation | AI Agents |
| [troubleshooting.md](troubleshooting.md) | Problem diagnosis and solutions | All |
| [benchmarking.md](benchmarking.md) | Performance measurement | Developers |
| [HISTORY.md](HISTORY.md) | Evolution across three versions | All |

## Related Resources

- **Issue #167**: Vector Memory System
- **Issue #180**: Reflexion Memory with Causal Reasoning
- **Task M-003**: Memory Router Implementation
- **Task M-004**: Reflexion Memory Schema
- **Task M-005**: Reflexion Memory Module
- **Task M-008**: Memory Search Benchmarks

## Design Principles

### Serena-First (ADR-007)

Serena is the canonical memory layer because it travels with the Git repository. Forgetful provides supplementary semantic search but its database is local-only.

**Implication**: Memory system always works via Serena, even when Forgetful is unavailable.

### Memory-First Architecture (ADR-007)

Agents retrieve memory before reasoning to ground decisions in past learnings.

**Implication**: All agents use `Search-Memory` as first step in multi-step tasks.

### Token Efficiency

Episodic memory provides structured, compressed access to session history instead of full transcript replay.

**Savings**: Episodes are 500-2000 tokens vs 10K-50K tokens for full session logs.

### Causal Integrity

Causal graph links are derived from actual session data, not inferred or assumed.

**Verification**: All edges have `evidence_count` showing how many episodes support the relationship.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v0.2.0 | 2026-01-01 | Phase 2A: Memory Router + Reflexion Memory |
| v0.1.0 | 2025-12 | Serena MCP + Forgetful MCP |
| v0.0.1 | 2025-11 | Initial Serena file-based memory |

## Support

For issues or questions:

1. Start with [Troubleshooting Guide](troubleshooting.md) for common problems
2. Check the [API Reference](api-reference.md) for function signatures
3. Review [Quick Start Guide](quick-start.md) for common patterns
4. For agents, see [Agent Integration](agent-integration.md) and [Skill Reference](skill-reference.md)
5. Consult ADR-037 and ADR-038 for design rationale
6. File an issue with `memory-system` label
