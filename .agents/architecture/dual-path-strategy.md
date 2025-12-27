# Dual-Path GitHub Operations Strategy

**Date**: 2025-12-23
**Principle**: Por qué no los dos?

---

## Platform Capabilities Matrix

| Platform | Skills Support | MCP Support | Best Implementation |
|----------|---------------|-------------|---------------------|
| **Claude Code (CLI)** | ✅ Yes | ✅ Yes | GitHub MCP Skill (5-20ms) |
| **VS Code Agents** | ✅ Yes | ✅ Yes | GitHub MCP Skill (5-20ms) |
| **Copilot CLI** | ❌ No | ⚠️ Limited | gh CLI wrappers (50-80ms) |

---

## Strategy: Both Implementations

### Path A: GitHub MCP Skill (Primary)

**For**: Claude Code, VS Code Agents

```
.claude/skills/github/
├── SKILL.md              # allowed-tools: mcp__github__*
├── README.md             # Usage guide
└── docs/
    ├── pr-operations.md
    ├── issue-operations.md
    └── reactions.md
```

**Performance**: 5-20ms overhead + API time
**Maintenance**: Low (official GitHub MCP)
**Coverage**: ~90% (validate reactions/threads)

### Path B: Native Tool Wrappers (Fallback)

**For**: Copilot CLI, bash environments

```
.claude/skills/github/scripts/
├── gh-native/
│   ├── get-pr-context.sh
│   ├── set-issue-labels.sh
│   ├── post-issue-comment.sh
│   └── add-comment-reaction.sh
└── README.md
```

**Performance**: 50-80ms overhead + API time
**Maintenance**: Medium (bash scripts)
**Coverage**: 100% (gh CLI + graphql)

---

## Routing Logic

### Automatic Detection

```markdown
## Usage

The github skill automatically selects the best implementation:

1. **Skills-aware platforms** (Claude Code, VS Code):
   - Uses GitHub MCP skill directly
   - Latency: 5-20ms overhead

2. **Skills-unaware platforms** (Copilot CLI):
   - Uses gh CLI bash wrappers
   - Latency: 50-80ms overhead

No configuration needed - the skill detects capabilities.
```

### Implementation

```bash
# In skill invocation
if command -v claude-code &> /dev/null || [[ -n "$VSCODE_AGENT" ]]; then
    # Use MCP path
    use_mcp_tool "github__pr_read" "$@"
else
    # Use bash path
    gh pr view "$@" --json title,body,author
fi
```

---

## Updated Issue Priority

| Issue | Original Scope | New Scope | Priority |
|-------|---------------|-----------|----------|
| **#286** | Replace PowerShell with gh CLI | **Copilot CLI path** | P1 |
| **#287** | PowerShell daemon | **OBSOLETE** | ❌ |
| **#288** | Hybrid architecture ADR | **Document dual-path** | P1 |
| **NEW** | GitHub MCP skill | **Claude Code + VS Code path** | P0 |

### Why Both Are Valuable

**Issue #286** (gh CLI rewrite):
- ✅ **KEEP** - Provides Copilot CLI support
- ✅ **KEEP** - Fallback when MCP unavailable
- ✅ **KEEP** - Simpler for bash-only environments
- **Target**: 50-80ms overhead (vs 183ms PowerShell)

**NEW** (GitHub MCP skill):
- ✅ **ADD** - Best performance for Claude Code
- ✅ **ADD** - Best performance for VS Code
- ✅ **ADD** - Lowest maintenance (official MCP)
- **Target**: 5-20ms overhead (vs 50-80ms bash)

**Issue #287** (Daemon):
- ❌ **OBSOLETE** - MCP provides better performance without complexity

---

## Phased Implementation

### Phase 1: Copilot CLI Path (Issue #286) - Week 1-2

**Goal**: Ensure Copilot CLI works with native tools

**Tasks**:
- [ ] Create `.claude/skills/github/scripts/gh-native/`
- [ ] Implement 4 high-frequency operations:
  - [ ] `get-pr-context.sh` (replaces Get-PRContext.ps1)
  - [ ] `set-issue-labels.sh` (replaces Set-IssueLabels.ps1)
  - [ ] `post-issue-comment.sh` (replaces Post-IssueComment.ps1)
  - [ ] `add-comment-reaction.sh` (replaces Add-CommentReaction.ps1)
- [ ] Test in Copilot CLI environment
- [ ] Document usage patterns

**Success Criteria**: Copilot CLI works with 50-80ms overhead (vs 183ms)

### Phase 2: GitHub MCP Skill (NEW) - Week 2-3

**Goal**: Optimize Claude Code and VS Code Agents

**Tasks**:
- [ ] Install GitHub MCP server
- [ ] Create `.claude/skills/github/SKILL.md` with `allowed-tools`
- [ ] Validate reactions and thread resolution support
- [ ] Document MCP tool equivalents for all 20 operations
- [ ] Test in Claude Code and VS Code
- [ ] Implement platform detection and routing

**Success Criteria**: Claude Code and VS Code use 5-20ms MCP path

### Phase 3: Documentation (Issue #288) - Week 3-4

**Goal**: Document dual-path strategy and usage

**Tasks**:
- [ ] Update ADR-016 with dual-path decision
- [ ] Create platform capability matrix
- [ ] Document routing logic
- [ ] Update skill documentation with platform notes
- [ ] Create troubleshooting guide

**Success Criteria**: Clear documentation for all three platforms

### Phase 4: Migration & Cleanup - Week 4+

**Goal**: Deprecate PowerShell wrappers

**Tasks**:
- [ ] Update pr-comment-responder to use skill (auto-routing)
- [ ] Migrate all GitHub operations to dual-path
- [ ] Deprecate PowerShell scripts (keep for reference)
- [ ] Archive ADR-005 (PowerShell-only) with platform exceptions
- [ ] Performance benchmarks on all platforms

**Success Criteria**: All platforms work optimally with their best path

---

## Expected Outcomes

### Performance Improvements

| Platform | Current | After Phase 1 | After Phase 2 | Improvement |
|----------|---------|---------------|---------------|-------------|
| **Copilot CLI** | 183ms | 50-80ms | N/A | **56-72%** |
| **Claude Code** | 183ms | 50-80ms | 5-20ms | **89-97%** |
| **VS Code** | 183ms | 50-80ms | 5-20ms | **89-97%** |

### Maintenance Impact

| Implementation | Custom Code | Maintenance | Platform Support |
|---------------|-------------|-------------|------------------|
| **PowerShell** | High (20 scripts) | High | Windows-first |
| **gh CLI bash** | Medium (4-8 scripts) | Medium | Universal |
| **GitHub MCP** | Zero | Low | Universal |

---

## Optionality Benefits

### For Users

**Claude Code users**: Get best performance (5-20ms MCP)
**VS Code users**: Get best performance (5-20ms MCP)
**Copilot CLI users**: Get good performance (50-80ms bash) without skills dependency
**All users**: Fallback if MCP has issues

### For Maintainers

**Two simple implementations** instead of complex daemon
**Clear separation** by platform capability
**Independent evolution** - MCP improves without affecting bash path
**Reduced risk** - If MCP fails, bash path still works

---

## Decision Rationale

### Why Not Just MCP?

- Copilot CLI doesn't support skills → would leave platform unsupported
- Bash fallback provides resilience if MCP has issues
- Some environments may not have MCP configured

### Why Not Just Bash?

- Claude Code and VS Code can do better with MCP (5-20ms vs 50-80ms)
- Official GitHub MCP has lower maintenance than custom scripts
- MCP provides richer error handling and type safety

### Why Both is Optimal?

✅ **Best of both worlds** - Performance where possible, compatibility everywhere
✅ **Platform-appropriate** - Each platform uses its best implementation
✅ **Resilient** - Multiple working paths reduce single points of failure
✅ **Future-proof** - As MCP adoption grows, more platforms benefit

---

## Commitment

**We implement BOTH paths because each serves a valid use case.**

**Phase 1 (bash) is NOT wasted** - it's the Copilot CLI solution.
**Phase 2 (MCP) is NOT redundant** - it's the Claude Code + VS Code optimization.

Together, they provide **universal coverage with optimal performance** per platform.

---

**Por qué no los dos? Because we can, and we should.**
