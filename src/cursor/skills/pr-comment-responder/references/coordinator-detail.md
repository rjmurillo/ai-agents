# Coordinator Detail

Detail that `SKILL.md` keeps out of the loaded body. Each section names the step that loads it. Read this file only when that step runs.

## Triage detail

Read this when you apply the Quick Fix criteria or route a fix to `qa`.

### Workflow paths

The orchestrator picks the path. You pass context and never add routing logic of your own.

| Path | Workers | Triage signal |
|------|---------|---------------|
| Quick Fix | `implementer`, then `qa` | You can explain the fix in one sentence |
| Standard | `analyst`, `milestone-planner`, `implementer`, `qa` | Needs investigation first |
| Strategic | `independent-thinker`, `high-level-advisor`, `task-decomposer` | The question is whether, not how |

### Quick Fix Path Criteria

For atomic bugs that meet ALL of these criteria, delegate directly to `implementer` (bypassing orchestrator) for efficiency:

| Criterion | Description | Example |
|-----------|-------------|---------|
| **Single-file** | Fix affects only one file | Adding BeforeEach to one test file |
| **Single-function** | Change is within one function/block | Converting PathInfo to string |
| **Clear fix** | Can explain the fix in one sentence | "Add .Path to extract string from PathInfo" |
| **No architectural impact** | Doesn't change interfaces or patterns | Bug fix, not refactoring |

**When to bypass orchestrator:**

```text
/agent implementer
Fix: [one-sentence description]...
```

For Standard/Strategic paths, still use orchestrator:

```text
/agent orchestrator
Analyze and implement...
```

Invocation forms. Claude Code: `Task(subagent_type="implementer", prompt="Fix: [one-sentence description]...")` and `Task(subagent_type="orchestrator", prompt="Analyze and implement...")`. Copilot CLI: `/agent implementer` and `/agent orchestrator`. VS Code: `#runSubagent` with the matching `subagentType`.

### QA Integration Requirement

**MUST**: Run the `qa` worker after ALL implementer work, regardless of perceived fix complexity.

| Fix Type | QA Required | Rationale |
|----------|-------------|-----------|
| Quick Fix | Yes | May need regression tests (PathInfo example) |
| Standard | Yes | Full test coverage verification |
| Strategic | Yes | Architectural impact assessment |

Evidence: QA agent added a regression test for a "simple" PathInfo bug that would have otherwise gone untested.

```text
/agent qa
Verify fix and assess regression test needs...
```

Invoke `qa` the same way: Claude Code `Task(subagent_type="qa", prompt="Verify fix and assess regression test needs...")`, Copilot CLI `/agent qa`.

## Step 3.1 context template

Read this when you build the first orchestrator context object.

For each comment, build a context object:

```markdown
## PR Comment Analysis Request

### PR Context
- **PR**: #[number] - [title]
- **Branch**: [head] → [base]
- **Author**: @[pr_author]

### Comment Details
- **Comment ID**: [id]
- **Reviewer**: @[author]
- **Type**: [review/issue]
- **Path**: [path]
- **Line**: [line]
- **Created**: [timestamp]

### Code Context
\`\`\`diff
[diff_hunk - surrounding code]
\`\`\`

### Comment Body
> [full comment body]

### Thread Context (if reply)
[Previous comments in thread]

### Request
Analyze this PR comment and determine:
1. Classification (Quick Fix / Standard / Strategic)
2. Priority (Critical / Major / Minor / Won't Fix / Question)
3. Required action
4. Implementation plan (if applicable)
```

## Phase 4 task list template

Read this when you write `tasks.md`. Write each implementation row exactly as `- [ ] **TASK-[id]**: [description]`: Gate 3 matches that shape.

```markdown
# PR #[number] Task List

**Generated**: [YYYY-MM-DD HH:MM:SS]
**Total Tasks**: [N]

## Priority Summary

| Priority | Count | Action |
|----------|-------|--------|
| Critical | [N] | Implement immediately |
| Major | [N] | Implement in order |
| Minor | [N] | Implement if time permits |
| Won't Fix | [N] | Reply with rationale |
| Question | [N] | Reply and wait for response |

## Immediate Replies (Phase 5)

These comments require immediate response before implementation:

| Comment ID | Author | Reason | Response Draft |
|------------|--------|--------|----------------|
| [id] | @[author] | Won't Fix / Question / Clarification | [draft] |

## Implementation Tasks (Phase 6)

### Critical Priority

- [ ] **TASK-[id]**: [description]
  - Comment: [comment_id] by @[author]
  - File: [path]
  - Plan: `.project-toolkit/pr-comments/PR-[number]/[comment_id]-plan.md`

### Major Priority

- [ ] **TASK-[id]**: [description]
  ...

### Minor Priority

- [ ] **TASK-[id]**: [description]
  ...

## Dependency Graph

[If tasks have dependencies, document here]
```

## Phase 9 detail

Read this when you run the Phase 9 memory update.

In a linked git worktree, skip the Serena memory mutation tools below: Serena writes to the checkout active at server start, so the edit lands in another checkout. Edit this checkout's `.serena/memories/` files or return the change to the parent session (`universal.md` MUST NOT 11).

### Step 9.1: Calculate Session Statistics

For each reviewer who commented on this PR:

```python
session_stats = {
    "pr_number": PR_NUMBER,
    "date": "YYYY-MM-DD",
    "reviewers": {
        "cursor[bot]": {"comments": N, "actionable": N, "rate": "100%"},
        "copilot-pull-request-reviewer": {"comments": N, "actionable": N, "rate": "XX%"},
        # ... other reviewers
    },
}
```

### Step 9.2: Update pr-review/pr-comment-responder-skills Memory

<!-- Formatter off: ruff would add trailing commas to the edit_memory calls in this block. -->
<!-- fmt:off -->
```python
# Read current memory to get existing statistics.
# Claude Code: Read this checkout's .serena/memories/pr-review/pr-comment-responder-skills.md
# Copilot CLI and VS Code: mcp__serena__read_memory(memory_file_name="pr-review/pr-comment-responder-skills")
# In a linked worktree every harness reads this checkout's file directly, because Serena serves another checkout.

# Calculate new cumulative totals from session_stats
# Example: If cursor[bot] had 9 comments (100%) and this PR adds 2 more (100%)
# New totals: 11 comments, 11 actionable, 100%

# Update Per-Reviewer Performance table with new totals
# Find the row for each reviewer and update their cumulative stats
mcp__serena__edit_memory(
    memory_file_name="pr-review/pr-comment-responder-skills",
    needle=r"\| cursor\[bot\] \| \d+ \| \d+ \| \*\*\d+%\*\* \|",
    repl=f"| cursor[bot] | {new_total_comments} | {new_actionable} | **{new_rate}%** |",
    mode="regex"
)

# Add new Per-PR Breakdown entry (prepend to existing entries)
new_pr_section = f"""### Per-PR Breakdown

#### PR #{PR_NUMBER} ({date})

| Reviewer | Comments | Actionable | Rate |
|----------|----------|------------|------|
| cursor[bot] | {cursor_comments} | {cursor_actionable} | {cursor_rate}% |
| copilot-pull-request-reviewer | {copilot_comments} | {copilot_actionable} | {copilot_rate}% |

"""

mcp__serena__edit_memory(
    memory_file_name="pr-review/pr-comment-responder-skills",
    needle="### Per-PR Breakdown",
    repl=new_pr_section,
    mode="literal"
)
```
<!-- fmt:on -->

### Step 9.3: Update Required Fields

The following MUST be updated in `pr-review/pr-comment-responder-skills`:

| Section | What to Update |
|---------|----------------|
| Per-Reviewer Performance | Add PR to PRs list, update totals |
| Per-PR Breakdown | Add new PR section with per-reviewer stats |
| Metrics | Update cumulative totals |

### Step 9.4: Verify Memory Updated

Confirm that the `pr-review/pr-comment-responder-skills` memory reflects the new PR:

- [ ] In **Per-Reviewer Performance (Cumulative)**, the PR appears in each relevant reviewer's PR list and their totals are updated
- [ ] In **Per-PR Breakdown**, a new section for this PR exists with per-reviewer stats populated
- [ ] In **Metrics**, cumulative totals (PR counts, comment counts, resolution stats) include this PR

**Verification Command**:

```text
# Read updated memory and verify new PR data appears.
# Claude Code: Read this checkout's .serena/memories/pr-review/pr-comment-responder-skills.md
# Copilot CLI and VS Code: mcp__serena__read_memory(memory_file_name="pr-review/pr-comment-responder-skills")
# In a linked worktree every harness reads this checkout's file directly.
```

## Output format

Read this when you write the final session summary.

```markdown
## PR Comment Response Summary

**PR**: #[number] - [title]
**Session**: [timestamp]

### Statistics

| Metric | Count |
|--------|-------|
| Total Comments | [N] |
| Quick Fix | [N] |
| Standard | [N] |
| Strategic | [N] |
| Won't Fix | [N] |
| Questions Pending | [N] |

### Commits Made

| Commit | Description | Comments Addressed |
|--------|-------------|--------------------|
| [hash] | [message] | [comment_ids] |

### Pending Items

| Comment ID | Author | Reason |
|------------|--------|--------|
| [id] | @[author] | Awaiting response to question |

### Files Modified

- [file]: [change type]

### PR Description Updated

[Yes / No] - [summary if yes]
```
