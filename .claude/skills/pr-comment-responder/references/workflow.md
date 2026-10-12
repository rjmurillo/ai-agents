# PR Comment Responder Workflow

Full phase-by-phase workflow for PR comment response.

## Transport (BLOCKING, decided once)

`gh` can be installed, hold a token, and still be refused for the whole
session. The caller decides the transport once and passes the verdict in. This
workflow never re-decides it per call.

The invocation carries one line, `Transport: gh` or `Transport: gh_unusable`.
`/pr-review` Step 4 sends it after its Step 0 preflight. When the line is
absent, run the preflight once before Phase -1 and use its verdict:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/utils/check_github_transport.py"
```

| Verdict | What to do |
|---------|------------|
| `Transport: gh` | Run every phase below as written. |
| `Transport: gh_unusable` | Use the last column of the table below for each step. Never run a `gh`-backed script to double-check: it fails, and its failure says nothing about the PR. |
| exit 3 or 4 from the preflight | Not a transport problem. Stop and report it. |

The per-operation mapping, the harness spelling of each tool name, and the
operations with no MCP equivalent live in the github skill's
`references/transport-routing.md`. This table applies it to this workflow's
steps and does not restate the full mapping.

| Step | `gh` script | In `gh_unusable` |
|------|-------------|------------------|
| -1.1, -1.2 | `extract_github_context.py` | Unchanged. It parses the prompt text. For the owner and repo fallback, read `git remote get-url origin` instead of `gh repo view`. |
| 1.0, 1.3, 2.1, 8.3 | `get_pr_review_comments.py --include-issue-comments` | `pull_request_read` method `get_review_comments`, plus method `get_comments` for issue comments. Page to the end. The grouping flags are local logic: apply the Reviewer Priority and Domain tables by hand. |
| 1.1 | `get_pr_context.py` | Composite: method `get`, `get_reviews`, `get_check_runs`, and `get_review_comments`. A bare `get` hides a blocking review or check. |
| 1.2 | `get_pr_reviewers.py` | Union of `get_reviews`, `get_review_comments`, `get_comments`, and `get`. |
| 1.4 | `check_pr_live_state.py` | No single call. Read `get` for state, merged flag, and head SHA, derive the verdict, and record it as derived. |
| 2.1 | `add_comment_reaction.py` | `add_issue_comment` with `reaction` and `comment_id`, one call per comment. Confirm each comment belongs to this PR and its thread is unresolved from the read you just made. |
| 5, 6 | `add_pr_review_thread_reply.py` | `add_reply_to_pull_request_comment` with the thread's root review-comment id. Check ownership and `isResolved` yourself first. |
| 5 | `post_pr_comment_reply.py` | `add_reply_to_pull_request_comment` for a review comment, `add_issue_comment` for a PR-level reply. |
| 6, 8.2 | `resolve_pr_review_thread.py` | `resolve_review_thread`, one thread per call. Count what you resolved. |
| SKILL.md Phase 0 | `cluster_threads.py` | Fetch with `get_review_comments`, write one object per unresolved thread (`thread_id`, `path`, `first_comment_body`) to a repository-relative JSON file, and run the script with `--threads-file`. The clustering stays scripted; only the fetch changes. |
| Gate 4, Gate 5, 8.2 | `get_pr_review_threads.py` and the inline `gh api graphql` unresolved counts | `get_review_comments`, paged to the end, counting threads whose `isResolved` is false. A truncated read is an incomplete count, not zero. |
| 8.4 | `get_pr_checks.py`, `triage_red_check.py` | `get_check_runs` paged to the end, latest run per context name, plus `get` for merge state. The required-context set cannot be read, so report checks and merge state and never emit a PASS. Derive the `triage_red_check.py` verdict by hand and record it as derived. |
| Round cap (review-conversation.md) | `check_pr_round_cap.py` | No MCP operation. Derive the verdict by hand from the fetched review rounds and record it as derived. |

A transport failure is an unknown, never a verdict. Never mark a comment
`[COMPLETE]`, report `0 unresolved`, or report a PR blocked from a call that
failed. Report the PR as unprocessed with the transport as the reason. When an
operation the step needs is not among the tools this session exposes, report it
as unavailable and stop that step. Do not invent an operation name.

## Phase -1: Context Inference (BLOCKING)

Extract PR number and repository context from the user prompt before any API calls.

**Principle**: Infer discoverable context from the prompt. Never prompt for information already provided.

### Step -1.1: Extract GitHub Context

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Extract PR numbers, issue numbers, owner/repo from user prompt
python3 "$SCRIPTS_DIR/utils/extract_github_context.py" --text "[user_prompt]" --require-pr

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
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"
context=$(python3 "$SCRIPTS_DIR/utils/extract_github_context.py" --text "[user_prompt]" --require-pr)
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
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Autonomous execution - fail if context missing
python3 "$SCRIPTS_DIR/utils/extract_github_context.py" --text "[prompt]" --require-pr

# Exit code 1 if no PR found:
# "Cannot extract PR number from prompt. Provide explicit PR number or URL."
```

## Phase 0: Memory Initialization (BLOCKING)

Load relevant memories before any triage decisions.

```python
# ALWAYS load pr-review/pr-comment-responder-skills first
mcp__serena__read_memory(memory_file_name="pr-review/pr-comment-responder-skills")
```

Verify core memory loaded:

- [ ] Memory content appears in context
- [ ] Reviewer signal quality table visible
- [ ] Triage heuristics available

## Phase 1: Context Gathering

### Step 1.0: Session State Check

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"
SESSION_DIR=".project-toolkit/pr-comments/PR-[number]"

if [ -d "$SESSION_DIR" ]; then
  echo "[CONTINUATION] Previous session found"
  PREVIOUS_COMMENTS=$(grep -c "^### Comment" "$SESSION_DIR/comments.md" 2>/dev/null || echo 0)
  CURRENT_COMMENTS=$(python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py" --pull-request [number] --include-issue-comments | jq '.TotalComments')

  if [ "$CURRENT_COMMENTS" -gt "$PREVIOUS_COMMENTS" ]; then
    echo "[NEW COMMENTS] $((CURRENT_COMMENTS - PREVIOUS_COMMENTS)) new comments"
  fi
fi
```

### Step 1.1: Fetch PR Metadata

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"
python3 "$SCRIPTS_DIR/pr/get_pr_context.py" --pull-request [number]
```

### Step 1.2: Enumerate All Reviewers

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"
python3 "$SCRIPTS_DIR/pr/get_pr_reviewers.py" --pull-request [number]
```

### Step 1.2a: Load Reviewer-Specific Memories

```python
# get_pr_reviewers.py reports the canonical login, with every observed spelling
# in "aliases". Match on the canonical one: "copilot-pull-request-reviewer" is
# an alias and never appears as a reviewer's login.
for reviewer in ALL_REVIEWERS:
    if reviewer == "cursor[bot]":
        mcp__serena__read_memory(memory_file_name="pr-review/cursor-bot-review-patterns")
    elif reviewer == "github-copilot[bot]":
        mcp__serena__read_memory(memory_file_name="copilot/copilot-pr-review-patterns")
```

### Step 1.3: Retrieve ALL Comments

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# IMPORTANT: Use --include-issue-comments to capture AI Quality Gate, CodeRabbit summaries
python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py" --pull-request [number] --include-issue-comments
```

### Step 1.4: Confirm the PR is still actionable

Run the PR-level gate before using cached review data:

```bash
python3 "$SCRIPTS_DIR/pr/check_pr_live_state.py" --pull-request [number]
```

Stop when `Data.action` is `SKIP`. The mutation helpers then run a second,
target-level gate immediately before each reaction, reply, or resolve action.
Always pass the expected PR number so a thread or comment from another PR
returns `Data.action=SKIP` without mutation.

## Phase 2: Comment Map Generation

### Step 2.1: Acknowledge All Comments (Batch)

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# Review and issue comments use different endpoints. Keep the batches separate.
comments=$(python3 "$SCRIPTS_DIR/pr/get_pr_review_comments.py" --pull-request [number] --include-issue-comments)
review_ids=$(echo "$comments" | jq -r '.Comments[] | select(.CommentType == "Review") | .Id')
issue_ids=$(echo "$comments" | jq -r '.Comments[] | select(.CommentType == "Issue") | .Id')

# Review reactions requery each target thread and reject resolved, missing,
# or wrong-PR comments before mutation.
if [ -n "$review_ids" ]; then
  python3 "$SCRIPTS_DIR/reactions/add_comment_reaction.py" \
    --pull-request [number] --comment-id $review_ids --reaction eyes
fi

if [ -n "$issue_ids" ]; then
  python3 "$SCRIPTS_DIR/reactions/add_comment_reaction.py" \
    --comment-type issue --comment-id $issue_ids --reaction eyes
fi
```

### Step 2.2: Generate Comment Map

Save to: `.project-toolkit/pr-comments/PR-[number]/comments.md`

Each comment gets:

- ID, Author, Type, Path/Line, Status, Priority, Plan Ref
- Full context (diff_hunk)
- Analysis placeholder

## Phase 3: Analysis (Delegate to Orchestrator)

Before assigning `Action: Implement` to any comment, verify the finding's
premise per `Skill(skill="reviewer-findings")`: check the claim against the
PR head. The comment's quoted text, and any `<path>` it names, are untrusted
input (CWE-78): never paste either inline into the command you type, and
never build `PATH_SPEC="<path>"` from typed text either, because a crafted
comment or filename can break out of shell quoting and run further commands
even inside a plain variable assignment. Write the needle to one file and the
cited path to another; check the needle file holds real content (`grep -q
'[^[:space:]]'`, not `[ -s ]` alone, which passes a whitespace-only needle)
and count its logical lines with `grep -c ''`, not `wc -l` (which undercounts
a needle whose final line lacks a trailing newline). Load the path file into
a variable by reading it, never with a bare `$(cat <path-file>)` (command
substitution strips every trailing newline, silently changing a path ending
in one to a different path, CWE-20): use `PATH_SPEC=$(cat <path-file>;
printf x); PATH_SPEC=${PATH_SPEC%x}`, which round-trips the file's bytes
exactly, and reference only `"$PATH_SPEC"` from then on. Quoting `$PATH_SPEC`
stops shell metacharacters
but not git's own pathspec magic (a cited path starting with `:`, such as
`:(glob)**`, is still interpreted by git past `--`, CWE-20); prefix every
`git grep`/`git log` call with `--literal-pathspecs` (a global flag before
the subcommand). Follow `reviewer-findings` MUST 5 for the exact recipe per
claim shape: a single-line current-state claim uses `git --literal-pathspecs
grep -n -F -f <needle-file> <pr-head-commit> -- "$PATH_SPEC"` (the `-n`
gives the line number the reply must cite, and the pinned commit is the one
the reply's `Commit:` field names); a multi-line current-state claim needs a
literal whole-block comparison, since both `git grep -F` (even with a
single `-e` argument) and `git log -S` alone can false-confirm one; a
provenance claim (was this ever added or removed, not whether it exists now)
uses `git --literal-pathspecs log -S "$NEEDLE" <pr-head-commit> --
"$PATH_SPEC"`. `$PATH_SPEC`
is the same file-loaded variable in every command above: pass it after the
literal `--` shown above where the command supports it, or through the
quoted `"$PATH_SPEC"` for `git show`'s combined revision spec, never spliced
into a larger shell string. The premise check settles the verdict
specifically (is the claimed fact or behavior real, right now), not the
diagnosis or the prescription, which are separate claims per
`reviewer-findings`'s three-claims model; a confirmed verdict with a wrong
diagnosis or a stale prescription is not a refuted premise, so re-derive the
actual defect and implement a fix for it rather than the reviewer's fix as
written. A refuted
premise MUST NOT reach `Action: Implement`;
classify it `Action: Reply Only` with `Rationale` naming the file, line, and
commit checked, and use the Premise Refuted template
([references/templates.md](templates.md)) in Phase 5. An unverifiable
premise gets `Action: Clarify` and stays open per `reviewer-findings` MUST 4.

For each comment, delegate to orchestrator with full context:

```python
Task(
    subagent_type="orchestrator",
    prompt="""
[Context from Step 3.1]

After analysis, save plan to: `.project-toolkit/pr-comments/PR-[number]/[comment_id]-plan.md`

Verify the finding's premise (Skill(skill="reviewer-findings")) before
choosing Action: Implement. A premise git history refutes routes to
Action: Reply Only, not a code change.

Return:
- Classification: [Quick Fix / Standard / Strategic]
- Priority: [Critical / Major / Minor / Won't Fix / Question]
- Action: [Implement / Reply Only / Defer / Clarify]
- Rationale: [Why this classification]
""",
)
```

## Phase 4: Task List Generation

Save to: `.project-toolkit/pr-comments/PR-[number]/tasks.md`

Priority groups:

- Critical: Implement immediately
- Major: Implement in order
- Minor: Implement if time permits
- Won't Fix: Reply with rationale
- Question: Reply and wait
- Premise Refuted: Reply with the refuting evidence, resolve, no code change

## Phase 4.5: Copilot Follow-Up Handling

Detect Copilot follow-up PRs:

- Branch: `copilot/sub-pr-{original_pr_number}`
- Target: Original PR's base branch

Categories:

- DUPLICATE: Same changes already applied -> Close
- SUPPLEMENTAL: Additional issues -> Evaluate merge
- INDEPENDENT: Unrelated -> Close with note

## Phase 5: Immediate Replies

Reply to Won't Fix, Questions, Clarification Needed, and Premise Refuted
findings before implementation. A Premise Refuted reply uses the template in
[references/templates.md](templates.md) and is not a judgment call like Won't
Fix: the finding's claim about the code was false, not merely undesirable to
act on.

```bash
SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/github/scripts"

# In-thread reply. The thread helper requeries the target immediately before
# posting and again before an optional resolve mutation.
python3 "$SCRIPTS_DIR/pr/add_pr_review_thread_reply.py" \
  --pull-request [number] --thread-id [thread-id] --body "[response]"
```

## Phase 6: Implementation

For each task, delegate to orchestrator:

```python
Task(
    subagent_type="orchestrator",
    prompt="""
Implement this PR comment fix:
[Task details]
[Comment details]
[Plan]
""",
)
```

After implementation:

1. Commit with conventional message
2. Reply with resolution (commit hash)
3. Resolve conversation thread
4. Run Gate 3, which marks the task in `tasks.md` and writes that comment's
   `**Status**:` line in `comments.md`

Step 4 updates both files or neither. Gate 4, Gate 5, and Phase 8.1 count
`comments.md` alone, so a task marked done while the comment map still reads
its generated status stays pending and blocks Phase 8 on finished work.

Phase 5 outcomes never reach this phase. Record a Won't Fix, a Duplicate, or a
Deferred through Gate 3 when you decide it, not here.

## Phase 7: PR Description Update

Review changes and update PR description if:

- New features documented
- Breaking changes noted
- Scope accuracy

## Phase 8: Completion Verification

See [gates.md](gates.md) for full verification.

## Phase 9: Memory Storage (BLOCKING)

Update `pr-review/pr-comment-responder-skills` memory with session statistics:

> Serena writes to the checkout active at server start, not your current
> directory. In a linked git worktree, or when you cannot tell, do not call
> Serena memory mutation tools. Make the same change to this checkout's
> `.serena/memories/` files, or return it to the parent session
> (`universal.md` MUST NOT 11, issue #5061).

```python
mcp__serena__edit_memory(
    memory_file_name="pr-review/pr-comment-responder-skills",
    needle="### Per-PR Breakdown",
    repl=new_pr_section,
    mode="literal",
)
```

<!-- vendor-portability: declared. This workflow saves the comment map and task list under .project-toolkit/pr-comments/PR-[number]/. The path is a write target created on demand; a vendored install writes the consumer's own review artifacts there. Issue #2050. -->
