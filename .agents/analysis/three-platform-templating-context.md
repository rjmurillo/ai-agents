# Three-Platform Templating System: Context for Agent Review

**Date**: 2025-12-15
**Purpose**: Provide context for independent-thinker and high-level-advisor review

---

## Background

### Previous Approach (FAILED)

The 2-variant agent consolidation approach was approved unanimously but fundamentally flawed:

1. **What was proposed**: Keep Claude agents (`src/claude/`) as source of truth, generate VS Code and Copilot CLI from templates
2. **What was approved**: 2-variant consolidation with drift detection to "collect data for 90 days"
3. **Why it failed**:
   - Data showed 2-12% similarity between Claude and templates (88-98% DIFFERENT)
   - The plan deferred full templating despite this data
   - Drift detection was designed to MEASURE drift, not prevent it
   - All specialists approved a half-measure

### Current State

| Platform | Source | File Count | Total Lines |
|----------|--------|------------|-------------|
| Claude | `src/claude/*.md` | 18 | 5,449 |
| VS Code | Generated from templates | 18 | ~5,500 |
| Copilot CLI | Generated from templates | 18 | ~5,500 |
| Templates | `templates/agents/*.shared.md` | 18 | 10,826 |

**Key Structural Differences**:

| Aspect | Claude Agents | Templates/Generated |
|--------|---------------|---------------------|
| Frontmatter model | `model: opus` | `model: Claude Opus 4.5 (anthropic)` |
| Tools section | `## Claude Code Tools` + prose | `tools:` array in frontmatter |
| Tool syntax | `mcp__cloudmcp-manager__*` | `cloudmcp-manager/` paths |
| Memory protocol | MCP function calls | Delegate to memory agent |
| Handoff syntax | Not standardized | `#runSubagent` or `/agent` |

---

## User's Directive

**Templates must be the source of truth. Generate ALL THREE platforms from templates:**

```text
templates/agents/*.shared.md (SOURCE OF TRUTH)
    |
    +---> src/claude/*.md (GENERATED)
    +---> src/vs-code-agents/*.agent.md (GENERATED)
    +---> src/copilot-cli/*.agent.md (GENERATED)
```

---

## Questions to Challenge

1. **Is 3-platform templating actually the right solution?**
   - Alternative: Runtime platform detection (no build step)
   - Alternative: Accept drift as intentional divergence
   - Alternative: Merge all three into a single universal agent format

2. **Can platform configs handle ALL differences?**
   - Claude needs MCP-style tool syntax
   - Claude needs `## Claude Code Tools` section (not just frontmatter tools)
   - Claude needs different memory protocol format

3. **What is the migration risk?**
   - 18 Claude agents must be "reverse-engineered" into template format
   - Some Claude-specific content may be lost
   - Some Claude agents have evolved differently

4. **Is "no drift by design" actually achievable?**
   - What if Claude genuinely needs different instructions?
   - What if platform-specific optimizations are necessary?

5. **What did we miss in the first approval?**
   - All agents approved the 2-variant approach
   - The data showed it was flawed
   - What cognitive bias allowed this?

---

## Evidence Summary

### Drift Data (from templates/README.md)

The drift detection script compares semantic content:
- 80% similarity threshold (current setting)
- If below threshold: DRIFT DETECTED

**Reported**: Claude vs VS Code showed 2-12% similarity on key sections

### Gap Analysis (from PR #43 review)

The agent capability gap analysis identified:
- 15 specific gaps across 9 agents
- Categories: Output Validation, Cross-Document Validation, Path Normalization, Naming Conventions, Post-Implementation Checkpoints

---

## Requested Analysis

### For Independent Thinker

1. Challenge the assumption that 3-platform templating is correct
2. Identify blind spots that led to prior approval of flawed 2-variant approach
3. Present evidence-based alternatives if they exist
4. Declare uncertainty rather than validate the proposal automatically

### For High-Level Advisor

1. Strategic direction: Confirm or reject 3-platform templating
2. Risk assessment: Is migration complexity justified?
3. Success criteria: How do we know this succeeds?
4. Failure modes: What could go wrong?

---

## Next Steps

After independent-thinker and high-level-advisor validate (or reject) direction:
1. Route to architect for platform config design (Claude-specific)
2. Route to planner for implementation work breakdown
3. Route to task-generator for atomic tasks
4. Route to critic for final validation
