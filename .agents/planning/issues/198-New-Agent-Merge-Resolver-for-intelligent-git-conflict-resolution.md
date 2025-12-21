---
number: 198
title: "New Agent: Merge Resolver for intelligent git conflict resolution"
state: OPEN
created_at: 12/20/2025 14:17:20
author: rjmurillo-bot
labels: ["enhancement", "agent-implementer", "area-prompts", "priority:P2"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/198
---

# New Agent: Merge Resolver for intelligent git conflict resolution

## Overview

Create a specialized **Merge Resolver** agent that intelligently resolves git merge conflicts by analyzing code intent, commit history, and metadata.

## Problem Statement

Manual merge conflict resolution is time-consuming and error-prone. Developers must understand:
- Why conflicting changes were made (intent)
- Which changes take precedence (bugfix vs feature)
- How to combine non-conflicting parts intelligently

A specialized agent can automate this by leveraging git history and commit metadata.

## Core Capabilities

1. **Conflict Analysis**
   - Analyze PR merge conflicts using `git blame` and commit history
   - Identify conflicting hunks and their source commits
   - Map conflicts to specific code sections

2. **Intent Understanding**
   - Parse commit messages for keywords (fix, feat, refactor, etc.)
   - Examine diffs to understand code changes semantically
   - Correlate changes with associated tests or documentation

3. **Intelligent Resolution**
   - Apply heuristic-based conflict resolution strategies
   - Prioritize changes based on intent metadata
   - Combine non-conflicting changes when appropriate
   - Preserve semantic correctness

4. **Context Gathering**
   - Fetch PR information (title, description, labels) via GitHub CLI
   - Use `git blame` to understand line-level history
   - Analyze commit metadata and authorship

5. **Conflict Staging**
   - Stage resolved files automatically
   - Prepare detailed commit message explaining resolution rationale
   - Support interactive review before committing

## Workflow

```text
1. Receive PR number as input
2. Fetch PR metadata (gh pr view)
3. Identify merge conflicts (git status --porcelain)
4. For each conflicting file:
   a. Extract conflict markers
   b. Run git blame on conflicting regions
   c. Fetch commit messages for both sides
   d. Apply resolution heuristics
   e. Generate resolved content
5. Stage resolved files (git add)
6. Prepare commit message with resolution rationale
```

## Resolution Heuristics

Priority rules for conflict resolution:

| Priority | Change Type | Rationale |
|----------|-------------|-----------|
| 1 | Security patches | Always take security fixes |
| 2 | Bugfixes | Fixes take precedence over features |
| 3 | Breaking changes | Must preserve API contracts |
| 4 | Changes with tests | More complete/verified changes |
| 5 | Recent changes | Newer code often more relevant |
| 6 | Formatting/style | Lowest priority |

**Combination Rules**:
- If changes affect different logical sections, combine both
- If one change is a superset of the other, use the superset
- If changes are semantically equivalent, prefer more recent

## Required Tools

**Git Commands**:
- `git status --porcelain` - Identify conflicting files
- `git blame -L <start>,<end> <file>` - Trace line history
- `git log --oneline -p <commit>` - Examine commit details
- `git add <file>` - Stage resolved files
- `git show <commit>:<file>` - View file at specific commit

**GitHub CLI**:
- `gh pr view <number>` - Fetch PR metadata
- `gh pr checkout <number>` - Checkout PR branch
- `gh pr diff <number>` - View PR changes

**File Operations**:
- Read conflicting files
- Edit files to apply resolutions
- Write resolved content

## Agent Configuration

**Activation Keywords**: Merge, Conflict, Resolve, Rebase, Integration

**Read-Only Mode**: No (requires write access to resolve conflicts)

**Handoff Protocol**:
- **From**: orchestrator, implementer, qa
- **To**: implementer (for manual review), qa (for verification)

**Memory Protocol**:
- Store resolution patterns learned from successful merges
- Track heuristic effectiveness over time

## Output Format

**Resolution Report** (`.agents/merge-resolver/resolution-<PR>.md`):

```markdown
## Merge Resolution Report: PR #<number>

### PR Context
- **Title**: [PR title]
- **Description**: [PR description summary]
- **Base Branch**: [branch]
- **Head Branch**: [branch]

### Conflicts Identified
[List of conflicting files]

### Resolution Strategy
| File | Conflict Type | Strategy Applied | Confidence |
|------|---------------|------------------|------------|
| [file] | [type] | [strategy] | [High/Medium/Low] |

### Resolution Details

#### [File 1]
**Conflict**: [Description of conflict]
**Analysis**:
- Base commit: [commit hash] - [message]
- Head commit: [commit hash] - [message]
**Decision**: [Rationale]
**Confidence**: [High/Medium/Low]

### Manual Review Required
[List any conflicts requiring human judgment]

### Commit Message
[Prepared commit message with resolution rationale]
```

## Implementation Notes

1. **Start Simple**: Begin with basic heuristics (recency, commit type keywords)
2. **Expand Gradually**: Add semantic analysis, test correlation, API compatibility checks
3. **Human-in-the-Loop**: Always provide resolution report for review before committing
4. **Safety First**: Flag complex conflicts for manual resolution when confidence is low

## Success Criteria

- [ ] Agent can identify merge conflicts in PR
- [ ] Agent can analyze commit history for conflicting lines
- [ ] Agent applies heuristic-based resolution strategies
- [ ] Agent generates resolution report with rationale
- [ ] Agent stages resolved files correctly
- [ ] Agent prepares commit message explaining resolution
- [ ] Agent flags low-confidence resolutions for manual review

## Related Issues

- Consider integration with `pr-comment-responder` for addressing merge conflict feedback
- May leverage `analyst` agent for investigating complex conflict scenarios
- Could integrate with `qa` agent to verify resolved code compiles/tests pass

## References

- Git documentation: https://git-scm.com/docs/git-blame
- GitHub CLI: https://cli.github.com/manual/
- Conventional Commits: https://www.conventionalcommits.org/

