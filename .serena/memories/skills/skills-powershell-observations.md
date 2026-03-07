# Skill Sidecar Learnings: PowerShell

**Last Updated**: 2026-01-18
**Sessions Analyzed**: 1 (batch 28)

## Constraints (HIGH confidence)

### Skill-Performance-008: Process Spawn Overhead Architectural Root Cause
**Pattern**: When optimizing subprocess calls, evaluate whether architectural change (daemon/MCP server) beats iterative parameter tuning. Claude Code Bash tool spawns new process for each command (security feature). PowerShell has no native server mode. Even with `-NoProfile` optimization (183ms), process initialization dominates simple operations. Root cause is architecture not configuration.

**Evidence**: Session 80 multi-agent strategic analysis identified 7 solution paths (2025-12-23):
- Current PowerShell wrappers: 183-1044ms per call
- gh CLI rewrite: 50-70% reduction (50ms)
- Named pipe daemon: 80-95% reduction (10-50ms)
- MCP server: 95-99% reduction (5-20ms)

**When Applied**: When performance profiling shows subprocess spawn overhead as bottleneck. Parameter optimization (like `-NoProfile`) provides 82.4% improvement (1,044ms → 183ms) but hits architectural ceiling.

**Anti-Pattern**: Iteratively optimizing process spawning parameters when server model (daemon or MCP) should replace subprocess architecture entirely.

**Session**: batch-28, 2026-01-18

---

## Preferences (MED confidence)

None yet.

## Edge Cases (MED confidence)

None yet.

## Notes for Review (LOW confidence)

None yet.

## Related

- [skills-agent-workflow-index](skills-agent-workflow-index.md)
- [skills-analysis-index](skills-analysis-index.md)
- [skills-architecture-index](skills-architecture-index.md)
- [skills-architecture-observations](skills-architecture-observations.md)
- [skills-autonomous-execution-index](skills-autonomous-execution-index.md)
