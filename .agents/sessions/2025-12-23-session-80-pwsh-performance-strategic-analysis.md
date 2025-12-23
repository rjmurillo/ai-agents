# Session 80: Strategic PowerShell Performance Analysis

**Date**: 2025-12-23
**Branch**: feat/skill-leverage
**Type**: Strategic Analysis

---

## Protocol Compliance

- [x] Phase 1: Serena initialized (`mcp__serena__initial_instructions`)
- [x] Phase 2: HANDOFF.md read (read-only reference)
- [x] Phase 3: Session log created (this file)
- [x] Relevant memories read: skills-powershell, skills-bash-integration, skills-github-cli, project-overview, codebase-structure, user-preference-no-bash-python

---

## Objective

Conduct comprehensive strategic analysis of Claude Code's PowerShell performance problem when invoking skills via the Bash tool. The goal is not to optimize the current approach but to reimagine how Claude Code should interact with PowerShell.

### Problem Statement

Every `pwsh` invocation from Claude Code's Bash tool suffers from process spawn overhead:
- Without -NoProfile: 1,044ms per call
- With -NoProfile: 183ms per call (82.4% faster, but still significant)
- Issue #283 (batching) papers over the problem
- PR #285 (already implemented) added -NoProfile

### User Insight

> "The issue is also when you shell out to pwsh, like when you're calling the PowerShell skills for working with GitHub. The batch request in Issue 283 just papers over the problem."

---

## Multi-Agent Workflow

| Step | Agent | Purpose | Status |
|------|-------|---------|--------|
| 1 | analyst | Root cause analysis | COMPLETE |
| 2 | architect | Solution architecture | COMPLETE |
| 3 | independent-thinker | Challenge assumptions | COMPLETE |
| 4 | security | Risk assessment | COMPLETE |
| 5 | devops | Implementation feasibility | COMPLETE |
| 6 | orchestrator | Synthesis | COMPLETE |

---

## Key Context From Memories

### Skill-Perf-001 (from skills-powershell)
- Statement: ALWAYS use `pwsh -NoProfile` for non-interactive scripts
- Evidence: 1,199ms -> 316ms per spawn (73.6% reduction)
- Atomicity: 98%
- Already implemented in PR #285

### User Preference (from user-preference-no-bash-python)
- PowerShell is the standard for this project
- No bash or Python scripts allowed
- All GitHub skills are in PowerShell

### Skills Affected (from codebase structure)
20 PowerShell scripts in `.claude/skills/github/scripts/`:
- PR operations (Get-PRContext, Get-PRReviewComments, etc.)
- Issue operations (Get-IssueContext, Set-IssueLabels, etc.)
- Reaction operations (Add-CommentReaction)

---

## Decisions

### Root Cause Identified

Claude Code's Bash tool spawns a new process for each command (security feature). PowerShell engine initialization takes 183-416ms even with `-NoProfile`, and there is no native "server mode" in PowerShell.

### Solution Paths Evaluated (7 total)

1. **Named Pipe Daemon** - 80-95% reduction, medium complexity
2. **PowerShell MCP Server** - 95-99% reduction, very high complexity
3. **gh CLI Rewrite** - 50-70% reduction, low complexity [RECOMMENDED FIRST]
4. **Hybrid Approach** - 70-90% reduction, medium complexity [TARGET ARCHITECTURE]
5. **Batch Scripts** - 50-60% reduction, low complexity
6. **Runspace Pool** - 95-99% reduction, very high complexity (violates pwsh preference)
7. **PowerShell Host Process** - N/A (no native solution exists)

### Recommendations

| Timeframe | Action | Expected Impact |
|-----------|--------|-----------------|
| Short-term (1-2 weeks) | Convert simple skills to direct `gh` CLI | 50-70% latency reduction |
| Medium-term (4-6 weeks) | Implement PowerShell daemon with named pipe | 80-95% latency reduction |
| Long-term | Evaluate PowerShell MCP Server | 95-99% latency reduction |

### Immediate Next Step

Benchmark `gh pr view --json` vs current Get-PRContext.ps1 to validate expected improvement.

---

## Session End Checklist

- [x] All agent consultations complete
- [x] Strategic analysis document created (`.agents/analysis/claude-pwsh-performance-strategic.md`)
- [x] Memory updated with findings (`claude-pwsh-performance-strategy`)
- [x] HANDOFF.md not modified (read-only)
- [x] Markdownlint passed
- [ ] Changes committed

---

## Artifacts Created

1. **Strategic Analysis**: `.agents/analysis/claude-pwsh-performance-strategic.md` (476 lines)
2. **Serena Memory**: `claude-pwsh-performance-strategy`

## Key Findings Summary

| Finding | Impact |
|---------|--------|
| Process spawn is unavoidable in current architecture | Root cause confirmed |
| PowerShell has no native server mode | Architectural constraint |
| gh CLI can replace 6+ skills | 50-70% latency reduction possible |
| Named pipe daemon feasible | 80-95% reduction for complex ops |
| MCP server is long-term solution | Blocked by missing SDK |

## Recommended Priority

1. **Immediate**: Benchmark gh CLI vs PowerShell skills
2. **Week 1-2**: Implement gh CLI skill variants
3. **Week 3-4**: Named pipe daemon proof-of-concept
4. **Future**: Evaluate MCP ecosystem

---

*Session complete: 2025-12-23*
