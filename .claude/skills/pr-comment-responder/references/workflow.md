# PR Comment Responder Workflow

Full phase-by-phase workflow for PR comment response.

## Phase 0: Memory Initialization (BLOCKING)

Load relevant memories before any triage decisions.

```python
# ALWAYS load pr-comment-responder-skills first
mcp__serena__read_memory(memory_file_name="pr-comment-responder-skills")
```

Verify core memory loaded:

- [ ] Memory content appears in context
- [ ] Reviewer signal quality table visible
- [ ] Triage heuristics available

## Phase 1: Context Gathering

### Step 1.0: Session State Check

```bash
SESSION_DIR=".agents/pr-comments/PR-[number]"

if [ -d "$SESSION_DIR" ]; then
  echo "[CONTINUATION] Previous session found"
  PREVIOUS_COMMENTS=$(grep -c "^### Comment" "$SESSION_DIR/comments.md" 2>/dev/null || echo 0)
  CURRENT_COMMENTS=$(pwsh .claude/skills/github/scripts/pr/Get-PRReviewComments.ps1 -PullRequest [number] -IncludeIssueComments | jq '.TotalComments')

  if [ "$CURRENT_COMMENTS" -gt "$PREVIOUS_COMMENTS" ]; then
    echo "[NEW COMMENTS] $((CURRENT_COMMENTS - PREVIOUS_COMMENTS)) new comments"
  fi
fi
```

### Step 1.1: Fetch PR Metadata

```powershell
pwsh .claude/skills/github/scripts/pr/Get-PRContext.ps1 -PullRequest [number] -IncludeChangedFiles
```

### Step 1.2: Enumerate All Reviewers

```powershell
pwsh .claude/skills/github/scripts/pr/Get-PRReviewers.ps1 -PullRequest [number]
```

### Step 1.2a: Load Reviewer-Specific Memories

```python
for reviewer in ALL_REVIEWERS:
    if reviewer == "cursor[bot]":
        mcp__serena__read_memory(memory_file_name="cursor-bot-review-patterns")
    elif reviewer == "copilot-pull-request-reviewer":
        mcp__serena__read_memory(memory_file_name="copilot-pr-review-patterns")
```

### Step 1.3: Retrieve ALL Comments

```powershell
# IMPORTANT: Use -IncludeIssueComments to capture AI Quality Gate, CodeRabbit summaries
pwsh .claude/skills/github/scripts/pr/Get-PRReviewComments.ps1 -PullRequest [number] -IncludeIssueComments
```

## Phase 2: Comment Map Generation

### Step 2.1: Acknowledge All Comments (Batch)

```powershell
$comments = pwsh -NoProfile .claude/skills/github/scripts/pr/Get-PRReviewComments.ps1 -PullRequest [number] -IncludeIssueComments | ConvertFrom-Json
$ids = $comments.Comments | ForEach-Object { $_.id }

# Batch acknowledge - single process, all comments
$result = pwsh -NoProfile .claude/skills/github/scripts/reactions/Add-CommentReaction.ps1 -CommentId $ids -Reaction "eyes" | ConvertFrom-Json
```

### Step 2.2: Generate Comment Map

Save to: `.agents/pr-comments/PR-[number]/comments.md`

Each comment gets:

- ID, Author, Type, Path/Line, Status, Priority, Plan Ref
- Full context (diff_hunk)
- Analysis placeholder

## Phase 3: Analysis (Delegate to Orchestrator)

For each comment, delegate to orchestrator with full context:

```python
Task(subagent_type="orchestrator", prompt="""
[Context from Step 3.1]

After analysis, save plan to: `.agents/pr-comments/PR-[number]/[comment_id]-plan.md`

Return:
- Classification: [Quick Fix / Standard / Strategic]
- Priority: [Critical / Major / Minor / Won't Fix / Question]
- Action: [Implement / Reply Only / Defer / Clarify]
- Rationale: [Why this classification]
""")
```

## Phase 4: Task List Generation

Save to: `.agents/pr-comments/PR-[number]/tasks.md`

Priority groups:

- Critical: Implement immediately
- Major: Implement in order
- Minor: Implement if time permits
- Won't Fix: Reply with rationale
- Question: Reply and wait

## Phase 4.5: Copilot Follow-Up Handling

Detect Copilot follow-up PRs:

- Branch: `copilot/sub-pr-{original_pr_number}`
- Target: Original PR's base branch

Categories:

- DUPLICATE: Same changes already applied -> Close
- SUPPLEMENTAL: Additional issues -> Evaluate merge
- INDEPENDENT: Unrelated -> Close with note

## Phase 5: Immediate Replies

Reply to Won't Fix, Questions, Clarification Needed before implementation.

```powershell
# In-thread reply
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest [number] -CommentId [id] -Body "[response]"
```

## Phase 6: Implementation

For each task, delegate to orchestrator:

```python
Task(subagent_type="orchestrator", prompt="""
Implement this PR comment fix:
[Task details]
[Comment details]
[Plan]
""")
```

After implementation:

1. Commit with conventional message
2. Reply with resolution (commit hash)
3. Resolve conversation thread
4. Update task list

## Phase 7: PR Description Update

Review changes and update PR description if:

- New features documented
- Breaking changes noted
- Scope accuracy

## Phase 8: Completion Verification

See [gates.md](gates.md) for full verification.

## Phase 9: Memory Storage (BLOCKING)

Update `pr-comment-responder-skills` memory with session statistics:

```python
mcp__serena__edit_memory(
    memory_file_name="pr-comment-responder-skills",
    needle="### Per-PR Breakdown",
    repl=new_pr_section,
    mode="literal"
)
```
