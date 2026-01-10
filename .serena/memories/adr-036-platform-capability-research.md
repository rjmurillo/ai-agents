# ADR-036 Platform Capability Matrix Research

**Research Date**: 2026-01-01
**Status**: Complete
**Analysis Document**: `.agents/analysis/122-adr-036-platform-capability-matrix-research.md`

## Key Findings

### Platform Tiers

**Tier 1: Full Local Control**
- Claude Code: 19 agents, Task tool, full MCP (Serena + cloudmcp-manager), persistent memory
- Copilot CLI: 18 agents, @agent syntax, GitHub MCP + custom, agent skills (Dec 2025)
- VS Code: 18 agents, #runSubagent, Agent Sessions, multi-model support

**Tier 2: Cloud-Constrained**
- GitHub Copilot (web): Custom agents, delegation support, BUT single repo + one PR + copilot/* branch constraints

### Updated Capability Matrix

| Capability | Claude | CLI | VS Code | Web |
|------------|--------|-----|---------|-----|
| Multi-Agent Orchestration | Full (19) | Full (18) | Full (18) | Partial (constrained) |
| MCP Tools | Full | GitHub + custom | Custom | Custom via config |
| Persistent Memory | Yes (Serena) | No | No | No |
| Repository Scope | Unlimited | Unlimited | Unlimited | **Single repo** |
| Branch Constraints | None | None | None | **copilot/* only** |
| PR Creation | Unlimited | Unlimited | Unlimited | **One at a time** |

### Critical Corrections

**OUTDATED CLAIM** (ADR-036 debate log):
> "Copilot CLI has limited capabilities"

**2026 REALITY**:
- Agent skills support (Dec 18, 2025)
- Custom MCP servers
- Full delegation syntax

**NEEDS CLARIFICATION**:
> "GitHub Copilot can only operate on a single agent"

**MORE ACCURATE**:
- Supports custom agents and delegation
- Architectural constraints (single repo, one PR, sandbox) limit orchestration vs local platforms

## Evidence Sources

- [GitHub Copilot CLI Docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli)
- [VS Code Agent Sessions](https://code.visualstudio.com/blogs/2025/11/03/unified-agent-experience)
- [GitHub Copilot Coding Agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)
- [Agent Skills Changelog](https://github.blog/changelog/2025-12-18-github-copilot-now-supports-agent-skills/)
- Codebase: `src/claude/`, `src/copilot-cli/`, `src/vs-code-agents/`

## Next Review Date

**2026-04-01** (quarterly update recommended due to rapid platform evolution)

## Recommendations

1. Update ADR-036 matrix with verified data (P0)
2. Revise outdated Copilot CLI limitation claims (P1)
3. Add research date to matrix for staleness tracking (P2)
