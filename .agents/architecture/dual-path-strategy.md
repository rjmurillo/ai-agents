# Dual-Path GitHub Operations Strategy

**Date**: 2025-12-23
**Principle**: Por qué no los dos?

---

## Platform Capabilities Matrix

| Platform | Skills Support | Hook Routing | Best Implementation |
|----------|---------------|-------------|---------------------|
| **Claude Code (CLI)** | ✅ Yes | ✅ Yes | Python scripts via hook (80-150ms) |
| **VS Code Agents** | ✅ Yes | ✅ Yes | Python scripts via hook (80-150ms) |
| **Copilot CLI** | ❌ No | ❌ No | gh-native shell scripts (50-80ms) |

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

### Path B: Python Scripts (Hook-Integrated, Primary for Claude Code)

**For**: Claude Code (enforced by `invoke_skill_first_guard.py` hook)

```
.claude/skills/github/scripts/
├── pr/                    # 27 Python scripts
│   ├── get_pr_context.py
│   ├── new_pr.py
│   ├── merge_pr.py
│   └── ...
├── issue/                 # 7 Python scripts
│   ├── get_issue_context.py
│   ├── set_issue_labels.py
│   └── ...
├── milestone/             # 2 Python scripts
└── reactions/             # 1 Python script
```

**Performance**: 80-150ms overhead + API time
**Maintenance**: Medium (Python scripts with validation, error handling)
**Coverage**: 100% (gh CLI + graphql, with rich error reporting)

### Path C: Native Shell Wrappers (Fallback)

**For**: Copilot CLI, bash environments

```
.claude/skills/github/scripts/
├── gh-native/
│   ├── get-pr-context.sh
│   ├── set-issue-labels.sh
│   ├── set-issue-milestone.sh
│   ├── post-issue-comment.sh
│   └── add-comment-reaction.sh
└── README.md
```

**Performance**: 50-80ms overhead + API time
**Maintenance**: Low (thin shell wrappers)
**Coverage**: 5 high-frequency operations

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

### Phase 1: Copilot CLI Path (Issue #286) - COMPLETE

**Goal**: Ensure Copilot CLI works with native tools

**Tasks**:
- [x] Create `.claude/skills/github/scripts/gh-native/`
- [x] Implement 5 high-frequency operations:
  - [x] `get-pr-context.sh` (replaces Get-PRContext.ps1)
  - [x] `set-issue-labels.sh` (replaces Set-IssueLabels.ps1)
  - [x] `post-issue-comment.sh` (replaces Post-IssueComment.ps1)
  - [x] `add-comment-reaction.sh` (replaces Add-CommentReaction.ps1)
  - [x] `set-issue-milestone.sh` (replaces Set-IssueMilestone.ps1)
- [x] Document usage patterns (gh-native/README.md)

**Status**: All 5 shell scripts implemented with structured JSON output and
ADR-035 exit codes. README documents usage, performance benchmarks, and
comparison with Python scripts. Original PowerShell scripts removed.

### Phase 2: Python Script Path with Hook Routing - COMPLETE

**Goal**: Provide validated, hook-enforced GitHub operations for Claude Code

**Tasks**:
- [x] Create `.claude/skills/github/SKILL.md` (v4.0.0)
- [x] Implement 37 Python scripts across pr/, issue/, milestone/, reactions/
- [x] Create `invoke_skill_first_guard.py` PreToolUse hook for routing
- [x] Hook maps raw `gh` commands to Python script equivalents
- [x] Validate reactions and thread resolution support (GraphQL)

**Status**: Python scripts are the primary path for Claude Code. The
PreToolUse hook blocks raw `gh` commands and redirects to validated
Python scripts with structured JSON output and error handling.

### Phase 3: Documentation (Issue #288) - Week 3-4

**Goal**: Document dual-path strategy and usage

**Tasks**:
- [ ] Update ADR-016 with dual-path decision
- [ ] Create platform capability matrix
- [ ] Document routing logic
- [ ] Update skill documentation with platform notes
- [ ] Create troubleshooting guide

**Success Criteria**: Clear documentation for all three platforms

### Phase 4: Migration & Cleanup - COMPLETE

**Goal**: Deprecate PowerShell wrappers

**Tasks**:
- [x] Update pr-comment-responder to use skill (auto-routing via hook)
- [x] Migrate all GitHub operations to Python scripts
- [x] Remove PowerShell scripts (original Get-PRContext.ps1 etc. deleted)
- [ ] Archive ADR-005 (PowerShell-only) with platform exceptions
- [x] Performance documented in gh-native/README.md

**Status**: All original PowerShell scripts removed. Python scripts
serve as primary path with hook enforcement. Shell scripts provide
Copilot CLI fallback.

---

## Expected Outcomes

### Performance Improvements

| Platform | Before (PowerShell) | Current Implementation | Improvement |
|----------|---------------------|----------------------|-------------|
| **Copilot CLI** | 183-416ms | 50-80ms (shell) | **56-80%** |
| **Claude Code** | 183-416ms | 80-150ms (Python) | **56-64%** |
| **VS Code** | 183-416ms | 80-150ms (Python) | **56-64%** |

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
