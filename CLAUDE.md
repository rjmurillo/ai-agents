# Claude Code Instructions

## BLOCKING GATE: Session Protocol

> **Canonical Source**: [.agents/SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md)
>
> This file uses RFC 2119 key words. MUST = required, SHOULD = recommended, MAY = optional.

### Phase 1: Serena Initialization (BLOCKING)

You MUST NOT proceed to any other action until both calls succeed:

```text
1. mcp__serena__activate_project  (with project path)
2. mcp__serena__initial_instructions
```

**Verification**: Tool output appears in session transcript.

**If skipped**: You lack project memories, semantic code tools, and historical context.

### Phase 2: Context Retrieval (BLOCKING)

You MUST read `.agents/HANDOFF.md` before starting work.

**Verification**: Content appears in session context; you reference prior decisions.

**If skipped**: You will repeat completed work or contradict prior decisions.

### Phase 3: Session Log (REQUIRED)

You MUST create session log at `.agents/sessions/YYYY-MM-DD-session-NN.md` early in session.

**Verification**: File exists with Protocol Compliance section.

### Session End (BLOCKING)

You CANNOT claim session completion until validation PASSES:

```bash
pwsh scripts/Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/[session-log].md"
```

Before running validator, you MUST:

1. Complete Session End checklist in session log (all `[x]` checked)
2. Update `.agents/HANDOFF.md` with session summary and session log link
3. Run `npx markdownlint-cli2 --fix "**/*.md"`
4. Commit all changes including `.agents/` files
5. Record commit SHA in Session End checklist Evidence column

**Verification**: Validator exits with code 0 (PASS).

**If validation fails**: Fix violations and re-run validator. Do NOT claim completion.

**Full protocol with RFC 2119 requirements**: [.agents/SESSION-PROTOCOL.md](.agents/SESSION-PROTOCOL.md)

---

Refer to [AGENTS.md](AGENTS.md) for complete project instructions.

This file exists for Claude Code's auto-load behavior. All canonical agent documentation is maintained in `AGENTS.md` to follow the DRY principle.

## Quick Reference

- **Agent invocation**: `Task(subagent_type="agent_name", prompt="...")`
- **Memory system**: `cloudmcp-manager` with Serena (tools prefixed with `mcp__serena__`: `write_memory`, `read_memory`, `list_memories`, `delete_memory`, `edit_memory`) fallback
- **Output directories**: `.agents/{analysis,architecture,planning,critique,qa,retrospective}/`

For full details on workflows, agent catalog, and best practices, see [AGENTS.md](AGENTS.md).

## GitHub Workflow Requirements (MUST)

### Issue Assignment

When starting work on a GitHub issue, you MUST assign it to yourself:

```bash
gh issue edit <number> --add-assignee @me
```

**When**: At the start of work, before making any changes.

**Why**: Prevents duplicate work and signals ownership.

### Pull Request Template

When creating a pull request, you MUST use the PR template:

1. Read the template: `cat .github/PULL_REQUEST_TEMPLATE.md`
2. Structure PR body to include ALL template sections:
   - Summary
   - Specification References (table)
   - Changes (bulleted list)
   - Type of Change (checkboxes)
   - Testing (checkboxes)
   - Agent Review (security + other reviews)
   - Checklist
   - Related Issues

**Do NOT** create PRs with custom descriptions that skip template sections.

## Default Behavior: Use Orchestrator Agent

When the user gives you any task, you MUST use the orchestrator agent rather than executing the task natively. The orchestrator will route to appropriate specialized agents.

**Exception**: Simple questions that don't require code changes or multi-step tasks can be answered directly.

```python
# For any non-trivial task, invoke orchestrator first
Task(subagent_type="orchestrator", prompt="[user's task description]")
```

This ensures proper agent coordination, memory management, and consistent workflows.
