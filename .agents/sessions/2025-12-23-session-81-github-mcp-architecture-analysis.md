# Session 81: GitHub MCP + Agent Isolation Architecture Analysis

**Date**: 2025-12-23
**Branch**: feat/skill-leverage
**Type**: Architecture Analysis
**Agent**: Architect

---

## Protocol Compliance

- [x] Phase 1: Serena initialized (`mcp__serena__initial_instructions`)
- [x] Phase 2: HANDOFF.md read (read-only reference)
- [x] Phase 3: Session log created (this file)
- [x] Relevant memories read: claude-pwsh-performance-strategy, skills-github-cli, skills-graphql, pr-comment-responder-skills, skills-architecture

---

## Objective

Conduct comprehensive architectural analysis comparing four approaches to GitHub operations in Claude Code:

1. **Option A**: PowerShell Wrappers (Current) - 183ms per call
2. **Option B**: gh CLI Rewrite (Issue #286) - 50ms per call
3. **Option C**: PowerShell Daemon (Issue #287) - 10-50ms after warmup
4. **Option D**: GitHub MCP + Agent Isolation (NEW) - 5-20ms via MCP protocol

Reference: https://raw.githubusercontent.com/obra/superpowers-chrome/refs/heads/main/agents/browser-user.md

---

## Research Findings

### GitHub MCP Server Capabilities

The official GitHub MCP server (github/github-mcp-server) exposes 40+ tools across toolsets:

**Pull Request Operations:**
- `create_pull_request` - Open new PR
- `update_pull_request` - Edit PR properties
- `merge_pull_request` - Merge PR
- `list_pull_requests` - List PRs with filtering
- `pull_request_read` - Get PR details (diff, status, files, review_comments, reviews, comments)
- `update_pull_request_branch` - Update branch
- `search_pull_requests` - Search PRs
- `pull_request_review_write` - Create/submit/delete reviews
- `add_comment_to_pending_review` - Add review comment
- `request_copilot_review` - Request Copilot review

**Issue Operations:**
- `issue_write` - Create/update issue
- `issue_read` - Get issue details (comments, sub_issues, labels)
- `list_issues` - List issues
- `add_issue_comment` - Add comment
- `search_issues` - Search issues
- `sub_issue_write` - Manage sub-issues
- `assign_copilot_to_issue` - Assign Copilot

**Labels:**
- `label_write` - Create/update/delete labels
- `get_label` - Get specific label
- `list_label` - List labels

**Milestones:**
- Supported via `issue_write` with `milestone` parameter

**GAPS IDENTIFIED:**
- No dedicated `add_reaction` tool
- No explicit GraphQL query passthrough
- Review thread resolution unclear (may require GraphQL)

### Agent Isolation Pattern (superpowers-chrome)

The pattern uses YAML frontmatter to declare agent-specific MCP servers:

```yaml
name: browser-user
description: Browser automation agent
tools: [mcp__plugin_superpowers-chrome_chrome__use_browser]
model: sonnet
permissionMode: default
skills: superpowers-chrome:browsing
```

Key principles:
1. **Declarative Tool Binding**: MCP servers attached per-agent, not globally
2. **Context Firewall**: 40 GitHub MCP tools visible only in GitHub agent context
3. **Delegation Pattern**: Main session delegates to specialized agent via Task tool
4. **Permission Isolation**: Read-only constraints enforced at agent level

### Claude Code Configuration

Current `.claude/settings.local.json` shows:
- `enableAllProjectMcpServers: true`
- Specific MCP servers enabled: `serena`, `deepwiki`
- No agent-specific MCP isolation pattern implemented

---

## Key Decisions

### Decision 1: ADR-016 Created

Created comprehensive ADR comparing all four approaches with:
- Quantified performance metrics
- Capability coverage analysis
- Reversibility assessment
- Migration path recommendations

### Decision 2: Phased Approach Recommended

1. **Phase 1** (1-2 weeks): gh CLI rewrite for simple operations
2. **Phase 2** (2-4 weeks): GitHub MCP + Agent Isolation prototype
3. **Phase 3** (4-6 weeks): Full GitHub MCP migration if prototype validates

### Decision 3: PowerShell Daemon Deprioritized

Named pipe daemon (Issue #287) deprioritized due to:
- High maintenance complexity
- Platform-specific implementation
- Security concerns with IPC
- GitHub MCP provides better long-term solution

---

## Artifacts Created

1. **ADR-016**: `.agents/architecture/ADR-016-github-mcp-agent-isolation.md`
2. **Session Log**: This file

---

## Session End

### Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Complete session log (all sections filled) | [x] | This file complete |
| MUST | Update Serena memory (cross-session context) | [x] | ADR-016 contains key decisions |
| MUST | Run markdown lint | [x] | Lint output clean |
| MUST | Route to qa agent (feature implementation) | [x] | `.agents/qa/pr-285-session-81-architecture.md` |
| MUST | Commit all changes (including .serena/memories) | [x] | Commit: a624f2f |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [x] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [x] | N/A - architecture session |
| SHOULD | Invoke retrospective (significant sessions) | [x] | N/A - will be part of larger retrospective |
| SHOULD | Verify clean git status | [x] | Clean after commit |

---

*Session complete: 2025-12-23*
