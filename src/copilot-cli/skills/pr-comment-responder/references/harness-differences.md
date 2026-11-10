# Harness Differences

Load this when a step names a command that your harness does not run as written. The workflow, gates, and status vocabulary are identical across Claude Code, Copilot CLI, and VS Code. Only the rows below differ. Each row was compared between the retired Claude body and the retired Copilot body of the `pr-comment-responder` agent.

| Concern | Claude Code | Copilot CLI | VS Code |
|---------|-------------|-------------|---------|
| Delegate to a worker | `agent_type: "project-toolkit:orchestrator"` with prompt "..." | `/agent orchestrator` then the prompt text | `#runSubagent` with the matching `subagentType` |
| Worker names | `orchestrator`, `implementer`, `qa` | same | same |
| Read a memory file | `Read` this checkout's `.serena/memories/<name>.md` | `mcp__serena__read_memory(memory_file_name="<name>")` | `mcp__serena__read_memory(memory_file_name="<name>")` |
| Edit a memory file | follow Phase 9 in [coordinator-detail.md](coordinator-detail.md), which carries the linked-worktree guard for both harnesses | same | same |
| Search memory | run the `memory` skill's `search_memory.py` with the topic (keyword match on file names, ADR-037) | the `mcp__serena__` memory tools | the `mcp__serena__` memory tools |
| Plan tracking | `TodoWrite` | the harness task list | the harness task list |
| Shell tool | `Bash` | `shell` | `execute` |
| Script root | `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts` | same expression | same expression |

## Delegation bounds

Claude Code carried these as `metadata.delegation` on the agent, checked by `check_agent_delegation.py`. A skill has no such frontmatter, so they apply as written here, in every harness.

| Bound | Value |
|-------|-------|
| Delegations per task | 15, where a task is one review comment. Only your direct delegations count. The orchestrator spends its own budget inside each one, so the bounds multiply across two levels. At the limit, leave the comment unresolved with a stated reason and move to the next comment. |
| Report schema | Each worker returns the orchestrator completion record: `artifacts`, `commands`, `deltas`, `residual_risks`, `confidence`, `acceptance_status`, `escalation_status`. |
| Acceptance owner | This skill. Verify a thread is addressed before you resolve it. |
| Retry limit | One retry of a failed delegation, and only after the approach or context changes. Never re-delegate unchanged work. |
| Stop condition | Every review thread is addressed and verified, or left unresolved with a stated reason. |
| Escalation owner | The user. |

## Script pairs

Both harnesses use the same `github` skill scripts. Use the thread-addressed helpers when you hold a `PRRT_` thread id, and the comment-addressed helper when you hold a numeric comment id:

| You hold | Reply | Resolve |
|----------|-------|---------|
| Thread id `PRRT_...` | `pr/add_pr_review_thread_reply.py --pull-request N --thread-id ID --body ...` | `pr/resolve_pr_review_thread.py --thread-id ID` |
| Numeric comment id | `pr/post_pr_comment_reply.py --pull-request N --comment-id ID --body ...` | look up the thread id first, then resolve by thread id |

`pr/get_pr_review_threads.py --pull-request N` lists threads with their ids. List every thread, following cursors to the last page.

## Where the Claude and Copilot bodies differed without a harness reason

These were drift, not harness differences. The skill keeps the Claude form for both harnesses.

- Claude carried commit-message etiquette, the `Action + Location + Reference` reply pattern, force-push wording, and the thread-resolution protocol. Copilot lacked them. They now live in [templates.md](templates.md) (Commit, Reply, and Resolve Conventions).
- Copilot carried the task-row shape and "both artifacts move or neither does" prose in Gate 3. [gates.md](gates.md) now carries it.
