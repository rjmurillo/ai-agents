# PR Comment Responder Workflow

Full phase-by-phase workflow for PR comment response.

## Phase -1: Context Inference (BLOCKING)

Extract PR number and repository context from the user prompt before any API calls.

**Principle**: Infer discoverable context from the prompt. Never prompt for information already provided.

### Step -1.1: Extract GitHub Context

```bash
# Extract PR numbers, issue numbers, owner/repo from user prompt
python3 .claude/skills/github/scripts/utils/extract_github_context.py --text "[user_prompt]" --require-pr

# Result JSON contains:
# - pr_numbers: Array of PR numbers found
# - issue_numbers: Array of issue numbers found
# - owner: Repository owner (from URL)
# - repo: Repository name (from URL)
# - urls: Structured URL data
# - raw_matches: Original matched text
```

### Step -1.2: Validate Context

```bash
context=$(python3 .claude/skills/github/scripts/utils/extract_github_context.py --text "[user_prompt]" --require-pr)
# Exit code 1 if no PR found (fail fast, no user prompt)

# Use first PR number (most common case is single PR)
pr_number=$(echo "$context" | jq -r '.pr_numbers[0]')

# Use URL-derived owner/repo if available, otherwise infer from git remote
owner=$(echo "$context" | jq -r '.owner // empty')
repo=$(echo "$context" | jq -r '.repo // empty')
if [ -z "$owner" ]; then
    owner=$(gh repo view --json owner -q '.owner.login')
    repo=$(gh repo view --json name -q '.name')
fi
```

### Supported Patterns

| Pattern Type | Examples | Extracted |
|--------------|----------|-----------|
| Text: "PR N" | `PR 806`, `PR #806`, `pr 123` | PRNumbers: [806] or [123] |
| Text: "pull request" | `pull request 123`, `Pull Request #456` | PRNumbers: [123] or [456] |
| Text: "#N" | `#806` (standalone) | PRNumbers: [806] |
| Text: "issue N" | `issue 45`, `issue #45` | IssueNumbers: [45] |
| URL: PR | `github.com/owner/repo/pull/123` | PRNumbers: [123], Owner, Repo |
| URL: Issue | `github.com/owner/repo/issues/456` | IssueNumbers: [456], Owner, Repo |

### Autonomous Execution Mode

When running autonomously (no user interaction possible):

- Use `-RequirePR` flag to fail fast if PR cannot be inferred
- Never prompt for clarification
- Error message must be actionable: include what patterns are supported

```bash
# Autonomous execution - fail if context missing
python3 .claude/skills/github/scripts/utils/extract_github_context.py --text "[prompt]" --require-pr

# Exit code 1 if no PR found:
# "Cannot extract PR number from prompt. Provide explicit PR number or URL."
```

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
  CURRENT_COMMENTS=$(python3 .claude/skills/github/scripts/pr/get_pr_review_comments.py --pull-request [number] --include-issue-comments | jq '.TotalComments')

  if [ "$CURRENT_COMMENTS" -gt "$PREVIOUS_COMMENTS" ]; then
    echo "[NEW COMMENTS] $((CURRENT_COMMENTS - PREVIOUS_COMMENTS)) new comments"
  fi
fi
```

### Step 1.1: Fetch PR Metadata

```bash
python3 .claude/skills/github/scripts/pr/get_pr_context.py --pull-request [number]
```

### Step 1.2: Enumerate All Reviewers

```bash
python3 .claude/skills/github/scripts/pr/get_pr_reviewers.py --pull-request [number]
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

```bash
# IMPORTANT: Use --include-issue-comments to capture AI Quality Gate, CodeRabbit summaries
python3 .claude/skills/github/scripts/pr/get_pr_review_comments.py --pull-request [number] --include-issue-comments
```

## Phase 2: Comment Map Generation

### Step 2.1: Acknowledge All Comments (Batch)

```bash
# Get all comment IDs
comments=$(python3 .claude/skills/github/scripts/pr/get_pr_review_comments.py --pull-request [number] --include-issue-comments)
ids=$(echo "$comments" | jq -r '.Comments[].id')

# Batch acknowledge with eyes reaction
python3 .claude/skills/github/scripts/reactions/add_comment_reaction.py --comment-id $ids --reaction eyes
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

```bash
# In-thread reply
python3 .claude/skills/github/scripts/pr/post_pr_comment_reply.py --pull-request [number] --comment-id [id] --body "[response]"
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
