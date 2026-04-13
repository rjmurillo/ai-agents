# Claude Code Hooks Opportunity Analysis

> **Date**: 2026-01-04
> **Source**: <https://www.claude.com/blog/how-to-configure-hooks>
> **Related**: ADR-008 (Protocol Automation via Lifecycle Hooks)
> **Status**: Research Complete

## Executive Summary

Claude Code provides eight hook event types for automating workflows. The ai-agents project currently uses only two (SessionStart, UserPromptSubmit). Six hook types remain untapped, offering opportunities to automate protocol enforcement, quality gates, and developer experience improvements.

**Current State**:

- 2 of 8 hook types implemented (25%)
- SessionStart: Memory-first enforcement (ADR-007), ADR change detection
- UserPromptSubmit: Memory checks, PR validation reminders, skill usage guidance

**Gap Analysis**:

| Hook Type | Implemented | Opportunity |
|-----------|-------------|-------------|
| SessionStart | Yes | Extend with git state injection |
| UserPromptSubmit | Yes | Add context-aware validation |
| PreToolUse | No | Block dangerous operations |
| PermissionRequest | No | Auto-approve safe commands |
| PostToolUse | No | Auto-format after edits |
| PreCompact | No | Backup transcripts |
| Stop | No | Verify task completion |
| SubagentStop | No | Validate subagent output |

---

## Hook Types Reference

### 1. PreToolUse

**Trigger**: Fires before any tool execution.

**Capabilities**:

- Block dangerous commands (e.g., `rm -rf`, force push)
- Validate file paths against security patterns
- Modify tool parameters before execution
- Auto-approve known safe operations

**Output Format** (JSON):

```json
{
  "decision": "approve|block|allow",
  "reason": "Explanation for Claude's context",
  "updatedInput": { "modified": "parameters" }
}
```

**Exit Codes**:

- 0: Success, proceed with tool
- 2: Block tool execution

### 2. PermissionRequest

**Trigger**: Intercepts permission dialogs before they appear.

**Capabilities**:

- Auto-approve repeated safe commands
- Auto-deny sensitive file access
- Reduce permission fatigue for known patterns

**Best For**: Test commands, build commands, linting tools.

### 3. PostToolUse

**Trigger**: Executes after tool completion.

**Capabilities**:

- Run formatters (Prettier, Black, PSScriptAnalyzer)
- Trigger linters
- Audit logging
- Update cached state

**Matchers**:

- `Write|Edit`: Format files after modifications
- `Bash(npm*|pnpm*|yarn*)`: Update lockfile hashes
- `mcp__*`: Log MCP tool usage

### 4. PreCompact

**Trigger**: Before context window compaction (summarization).

**Capabilities**:

- Backup full transcript to file
- Extract key decisions before summarization
- Preserve context that would otherwise be lost

**Use Case**: Session checkpointing for pause/resume (Issue #174).

### 5. Stop

**Trigger**: When Claude finishes responding (before control returns to user).

**Capabilities**:

- Verify task completion criteria
- Run final tests
- Force continuation if incomplete
- Generate summaries

**Output Format**:

```json
{
  "continue": true,
  "reason": "Task not complete: tests failing"
}
```

### 6. SubagentStop

**Trigger**: When a subagent (Task tool) completes.

**Capabilities**:

- Validate subagent output quality
- Check for protocol compliance
- Aggregate results across agents

**Use Case**: Verify orchestrator-delegated tasks meet criteria.

### 7. SessionStart (Implemented)

**Current Implementation**:

- `Invoke-SessionStartMemoryFirst.ps1`: ADR-007 enforcement, MCP availability check
- `Invoke-ADRChangeDetection.ps1`: ADR change detection

**Enhancement Opportunities**:

- Inject git status and branch info
- Load TODO items for context
- Set session-specific environment variables

### 8. UserPromptSubmit (Implemented)

**Current Implementation**:

- `Invoke-UserPromptMemoryCheck.ps1`: Memory checks, PR validation, skill usage

**Enhancement Opportunities**:

- Inject sprint context from project management
- Validate prompts against scope creep patterns
- Add dynamic context based on prompt analysis

---

## Environment Variables

Claude Code hooks have access to:

| Variable | Description |
|----------|-------------|
| `CLAUDE_PROJECT_DIR` | Absolute path to project root |
| `CLAUDE_CODE_REMOTE` | Boolean for web environments |
| `CLAUDE_ENV_FILE` | Path for persisting session variables |
| `CLAUDE_TOOL_INPUT_*` | Tool-specific input parameters |

**Matcher-specific variables** (PreToolUse, PostToolUse):

- `CLAUDE_TOOL_INPUT_FILE_PATH`: For Write/Edit operations
- `CLAUDE_TOOL_INPUT_COMMAND`: For Bash operations

---

## Matcher Syntax

Matchers filter which tools trigger hooks (PreToolUse, PostToolUse, PermissionRequest only):

| Pattern | Matches | Example |
|---------|---------|---------|
| `"Write"` | Exact tool name | Write tool only |
| `"Write\|Edit"` | Multiple tools | Either tool |
| `"*"` or `""` | All tools | Any tool |
| `"Bash(npm test*)"` | Command prefix | npm test commands |
| `"mcp__memory__.*"` | MCP namespace | Memory MCP tools |

**Case Sensitivity**: Matchers are case-sensitive. Use exact tool names.

---

## Gap Analysis: ai-agents Project

### Currently Implemented

**SessionStart** (2 hooks):

1. **Invoke-SessionStartMemoryFirst.ps1**
   - Checks Forgetful MCP availability
   - Outputs ADR-007 blocking gate requirements
   - Provides fallback guidance if Forgetful unavailable

2. **Invoke-ADRChangeDetection.ps1**
   - Detects uncommitted ADR changes
   - Injects reminder to run adr-review skill

**UserPromptSubmit** (1 hook):

1. **Invoke-UserPromptMemoryCheck.ps1**
   - Detects planning/implementation keywords, injects memory-first reminder
   - Detects PR creation intent, injects pre-PR validation checklist
   - Detects GitHub CLI usage, injects skill usage guidance

### Not Implemented (Opportunities)

#### Priority 1: PreToolUse (HIGH)

**Rationale**: Direct enforcement of security and protocol constraints.

**Recommended Implementations**:

1. **Security Path Validator**
   - Matcher: `Write|Edit`
   - Block writes to protected paths (`.git/`, secrets files)
   - Pattern: `security-path-anchoring-pattern` memory

2. **Branch Protection Guard**
   - Matcher: `Bash(git push*|git commit*)`
   - Block commits to main/master without feature branch
   - Implements: SESSION-PROTOCOL Phase 4 (Branch Verification)

3. **Skill Enforcement Hook**
   - Matcher: `Bash(gh *)`
   - Block raw `gh` commands when skill alternative exists
   - Implements: `usage-mandatory` memory

4. **Dangerous Command Blocker**
   - Matcher: `Bash(*)`
   - Block `rm -rf`, `git push --force origin main`
   - Pattern: Allowlist-based (block by default, allow known safe)

#### Priority 2: PostToolUse (HIGH)

**Rationale**: Automates quality gates after file modifications.

**Recommended Implementations**:

1. **PowerShell Formatter**
   - Matcher: `Write|Edit`
   - Filter: `.ps1` files only
   - Action: Run PSScriptAnalyzer with autofix
   - Implements: `linting-autofix` memory

2. **Markdown Linter**
   - Matcher: `Write|Edit`
   - Filter: `.md` files only
   - Action: Run `npx markdownlint-cli2 --fix`
   - Warning: DO NOT run on `.ps1` files (corrupts comment terminators)

3. **Session Log Updater**
   - Matcher: `Write|Edit`
   - Filter: Source code files
   - Action: Append to session log "Files changed" section

4. **Memory Index Sync**
   - Matcher: `mcp__serena__write_memory`
   - Action: Check if `memory-index` needs update

#### Priority 3: Stop (MEDIUM)

**Rationale**: Enforcement at session/response end.

**Recommended Implementations**:

1. **Task Completion Verifier**
   - Check if stated task objectives met
   - Force continuation if incomplete
   - Pattern: `task-completion-checklist` memory

2. **Session Protocol Validator**
   - Verify session log exists
   - Check MUST requirements completed
   - Force continuation if protocol incomplete

3. **QA Gate Enforcer**
   - For feature implementation sessions
   - Force continuation until QA validation ran
   - Implements: SESSION-PROTOCOL Phase 2.5

#### Priority 4: PermissionRequest (MEDIUM)

**Rationale**: Reduce permission fatigue for safe operations.

**Recommended Implementations**:

1. **Test Command Auto-Approval**
   - Matcher: `Bash(Invoke-Pester*|npm test*|pytest*)`
   - Auto-approve test execution
   - Pattern: Known safe, read-only operations

2. **Lint Command Auto-Approval**
   - Matcher: `Bash(npx markdownlint*|pwsh -c Invoke-ScriptAnalyzer*)`
   - Auto-approve linting operations

3. **Git Read Operations**
   - Matcher: `Bash(git log*|git status*|git diff*|git branch*)`
   - Auto-approve read-only git operations

#### Priority 5: SubagentStop (MEDIUM)

**Rationale**: Quality gate for multi-agent workflows.

**Recommended Implementations**:

1. **QA Agent Validator**
   - Verify QA reports are complete
   - Check for critical unaddressed issues

2. **Critic Agent Validator**
   - Verify critique includes concrete improvements
   - Check for actionable feedback

3. **Orchestrator Handoff Validator**
   - Verify handoff documentation complete
   - Check session log updated

#### Priority 6: PreCompact (LOW)

**Rationale**: Context preservation for long sessions.

**Recommended Implementations**:

1. **Transcript Backup**
   - Save full transcript before compaction
   - Enable session recovery and debugging

2. **Decision Extractor**
   - Extract key decisions before summarization
   - Store in session log or memory

---

## Implementation Architecture

### File Organization

```text
.claude/hooks/
├── PreToolUse/
│   ├── Invoke-SecurityPathValidator.ps1
│   ├── Invoke-BranchProtectionGuard.ps1
│   ├── Invoke-SkillEnforcement.ps1
│   └── Invoke-DangerousCommandBlocker.ps1
├── PostToolUse/
│   ├── Invoke-PowerShellFormatter.ps1
│   ├── Invoke-MarkdownLinter.ps1
│   └── Invoke-SessionLogUpdater.ps1
├── Stop/
│   ├── Invoke-TaskCompletionVerifier.ps1
│   └── Invoke-QAGateEnforcer.ps1
├── PermissionRequest/
│   ├── Invoke-TestCommandAutoApproval.ps1
│   └── Invoke-ReadOnlyGitAutoApproval.ps1
└── SubagentStop/
    ├── Invoke-QAAgentValidator.ps1
    └── Invoke-OrchestratorHandoffValidator.ps1
```

### Configuration Pattern

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "pwsh -NoProfile -File \"$CLAUDE_PROJECT_DIR/.claude/hooks/PreToolUse/Invoke-SecurityPathValidator.ps1\"",
            "statusMessage": "Validating file path security"
          }
        ]
      },
      {
        "matcher": "Bash(git push*|git commit*)",
        "hooks": [
          {
            "type": "command",
            "command": "pwsh -NoProfile -File \"$CLAUDE_PROJECT_DIR/.claude/hooks/PreToolUse/Invoke-BranchProtectionGuard.ps1\"",
            "statusMessage": "Verifying branch protection"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "pwsh -NoProfile -File \"$CLAUDE_PROJECT_DIR/.claude/hooks/PostToolUse/Invoke-AutoFormatter.ps1\"",
            "statusMessage": "Running auto-formatter"
          }
        ]
      }
    ]
  }
}
```

### Hook Input/Output Protocol

**Input** (via stdin, JSON):

```json
{
  "session_id": "abc123",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/path/to/project",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/path/to/file.ps1",
    "content": "..."
  }
}
```

**Output** (PreToolUse blocking):

```json
{
  "decision": "block",
  "reason": "Cannot write to protected path: .git/config"
}
```

**Output** (Stop continuation):

```json
{
  "continue": true,
  "reason": "Session log incomplete - MUST requirements not met"
}
```

---

## Security Considerations

### Input Validation

All hooks MUST:

1. Validate JSON input before processing
2. Handle malformed input gracefully (exit 0, not 2)
3. Quote all variable expansions in shell commands
4. Use absolute paths for script references

### Exit Code Semantics

| Exit Code | Meaning | Use Case |
|-----------|---------|----------|
| 0 | Success | Normal operation, output added to context |
| 2 | Block | Security violation, stop tool execution |
| Other | Warning | Non-blocking issue, log and continue |

### Timeout Handling

- Default: 60 seconds per hook
- Long-running hooks should use async patterns
- Timeout failure should not block work

---

## Integration with Existing Architecture

### ADR-007: Memory-First Architecture

Current SessionStart hook enforces ADR-007. Proposed hooks extend this:

- PreToolUse: Block operations that skip memory retrieval
- PostToolUse: Update memories after significant changes
- Stop: Verify memory writes completed

### ADR-008: Protocol Automation via Lifecycle Hooks

This analysis directly addresses ADR-008's implementation notes:

| ADR-008 Hook | This Analysis Equivalent |
|--------------|-------------------------|
| `session.start` | SessionStart (implemented) |
| `session.end` | Stop (proposed) |
| `task.pre` | PreToolUse (proposed) |
| `task.post` | PostToolUse (proposed) |
| `file.modify` | PostToolUse with Write/Edit matcher |
| `commit.pre` | PreToolUse with Bash(git commit*) matcher |

### SESSION-PROTOCOL.md

Hooks automate MUST requirements:

| Requirement | Automation Hook |
|-------------|-----------------|
| Branch verification | PreToolUse (Bash git*) |
| QA validation | Stop (force continue) |
| Markdown lint | PostToolUse (Write/Edit) |
| Skill usage | PreToolUse (Bash gh*) |

---

## Risk Analysis

### Over-Automation Risk

**Risk**: Hooks become too restrictive, blocking legitimate work.

**Mitigation**:

- Default to warning, not blocking
- Provide bypass mechanism for exceptional cases
- Log all decisions for audit

### Performance Risk

**Risk**: Hooks add latency to every operation.

**Mitigation**:

- Keep hooks lightweight (<100ms)
- Use async where possible
- Cache expensive checks

### Debugging Complexity

**Risk**: Hook failures hard to diagnose.

**Mitigation**:

- Comprehensive logging to transcript
- Clear error messages with remediation steps
- Hook status in `/hooks` menu

### Configuration Drift

**Risk**: Project and user hooks conflict.

**Mitigation**:

- Document precedence (project > user > local)
- Use `.claude/settings.local.json` for personal overrides
- Regular hook audits in session protocol

---

## Implementation Roadmap

### Phase 1: Core Enforcement (Week 1-2)

1. PreToolUse: Branch protection guard
2. PreToolUse: Dangerous command blocker
3. PostToolUse: Markdown linter

### Phase 2: Quality Gates (Week 3-4)

1. Stop: Task completion verifier
2. SubagentStop: QA agent validator
3. PostToolUse: PowerShell formatter

### Phase 3: Permission Optimization (Week 5-6)

1. PermissionRequest: Test auto-approval
2. PermissionRequest: Read-only git auto-approval
3. PreToolUse: Skill enforcement

### Phase 4: Context Preservation (Week 7-8)

1. PreCompact: Transcript backup
2. PreCompact: Decision extractor
3. SessionStart: Enhanced git state injection

---

## Appendix: Existing Hook Scripts Analysis

### Invoke-SessionStartMemoryFirst.ps1

**Strengths**:

- Proper error handling with exit codes
- MCP availability check with graceful degradation
- Clear markdown output for Claude context

**Patterns to Replicate**:

- Read configuration from `.mcp.json`
- Non-blocking fallback mode
- Structured output with headers

### Invoke-UserPromptMemoryCheck.ps1

**Strengths**:

- JSON input parsing with fallback
- Keyword-based pattern matching
- Multiple concern detection (memory, PR, skills)

**Patterns to Replicate**:

- Pipeline input handling
- Multiple detection patterns in single hook
- Context-aware output injection

### Invoke-ADRChangeDetection.ps1

**Purpose**: Detect uncommitted ADR changes and remind to run adr-review.

**Pattern**: Git status parsing for specific file patterns.

---

## Conclusion

The ai-agents project has established a solid foundation with SessionStart and UserPromptSubmit hooks. Six additional hook types offer opportunities to:

1. **Enforce security** (PreToolUse blocking)
2. **Automate quality** (PostToolUse formatting)
3. **Reduce friction** (PermissionRequest auto-approval)
4. **Ensure completion** (Stop verification)
5. **Validate delegation** (SubagentStop validation)
6. **Preserve context** (PreCompact backup)

Implementation should prioritize enforcement hooks (PreToolUse, Stop) over convenience hooks (PermissionRequest, PreCompact). Each hook should follow established patterns from existing implementations: proper exit codes, graceful degradation, and clear context injection.

The gap between current state (2 hooks) and full utilization (8 hooks) represents significant automation opportunity. ADR-008 anticipated this work; this analysis provides the implementation blueprint.

---

## Applicability: Integration Points with ai-agents

### Immediate Opportunities (No ADR Required)

These hooks can be added directly to `.claude/settings.json`:

| Hook | File | Description | Effort |
|------|------|-------------|--------|
| PostToolUse:MarkdownLinter | `Invoke-MarkdownAutoLint.ps1` | Auto-lint .md files after Write/Edit | Low |
| PreToolUse:SkillEnforcement | `Invoke-SkillUsageCheck.ps1` | Block raw `gh` when skill exists | Medium |
| PermissionRequest:TestAuto | `Invoke-TestAutoApproval.ps1` | Auto-approve Pester/npm test | Low |

### Medium-Term Opportunities (ADR Review Recommended)

| Hook | Description | Dependency |
|------|-------------|------------|
| Stop:SessionValidator | Verify session log complete before stopping | ADR-008 extension |
| SubagentStop:QAValidator | Verify QA reports from qa agent | Multi-agent workflow |
| PreCompact:TranscriptBackup | Save transcript before summarization | Storage decision |

### Long-Term Opportunities (Architectural Change)

| Opportunity | Description | Complexity |
|-------------|-------------|------------|
| State Machine | Implement Daem0n-style Communed/Counseled states | High |
| Preflight Tokens | Timestamp-based context freshness validation | Medium |
| Failed Memory Boosting | Query failed approaches first | Memory schema change |
| Pending Decision Tracking | Block commits with stale ADR decisions | Git hook extension |

### Priority Matrix

```text
                    HIGH IMPACT
                        │
    PostToolUse:Lint    │   Stop:SessionValidator
    PermissionRequest   │   SubagentStop:QA
                        │
LOW ────────────────────┼──────────────────── HIGH
EFFORT                  │                    EFFORT
                        │
    PreToolUse:Branch   │   State Machine
    PreToolUse:Skill    │   Preflight Tokens
                        │
                    LOW IMPACT
```

### Recommended First Implementation

Based on gap analysis and existing patterns:

1. **PostToolUse: Markdown Linter**
   - Matcher: `Write|Edit`
   - Filter: `.md` files only
   - Command: `npx markdownlint-cli2 --fix "$CLAUDE_TOOL_INPUT_FILE_PATH"`
   - Rationale: Low risk, immediate quality improvement

2. **PreToolUse: Branch Guard**
   - Matcher: `Bash(git commit*|git push*)`
   - Block: If on main/master branch
   - Rationale: Directly implements SESSION-PROTOCOL Phase 4

3. **Stop: Session Log Check**
   - Matcher: (all)
   - Validate: Session log exists with required sections
   - Continue: Force continuation if incomplete
   - Rationale: Prevents incomplete sessions

---

## Appendix: Daem0n-MCP Patterns Analysis

### Source

- Repository: <https://github.com/DasBluEyedDevil/Daem0n-MCP>
- Documentation: <https://deepwiki.com/DasBluEyedDevil/Daem0n-MCP>

### Sacred Covenant Protocol

Daem0n-MCP implements a **mandatory enforcement mechanism** through a state machine that controls tool access:

| State | Triggered By | Allowed Tools |
|-------|-------------|---------------|
| NotStarted | Session start | `get_briefing()`, `health()` only |
| Communed | `get_briefing()` called | Read-only tools |
| Counseled | `context_check()` called | All tools including mutations |
| CounselExpired | 5 min timeout | Reverts to Communed |

**Key Insight**: This maps directly to ADR-007 memory-first architecture. The ai-agents project could implement similar states:

- **NotStarted** → Before Serena init
- **Communed** → After `mcp__serena__activate_project` + `initial_instructions`
- **Counseled** → After reading HANDOFF.md and memory-index

### Decorator-Based Enforcement

Daem0n uses Python decorators to enforce covenant compliance:

```python
@requires_communion  # Blocks if get_briefing() not called
def scan_todos():
    pass

@requires_counsel    # Blocks if context_check() expired (5 min TTL)
def add_rule():
    pass
```

**Applicable Pattern**: PowerShell hooks could implement similar gating:

```powershell
# In PreToolUse hook
if (-not (Test-SerenaBriefed)) {
    return @{ decision = "block"; reason = "COMMUNION_REQUIRED: Call mcp__serena__initial_instructions first" }
}
```

### Preflight Token System

After `context_check()`, Daem0n issues a **preflight token** as cryptographic proof of consultation, valid for 5 minutes. This prevents agents from claiming they checked context when they did not.

**Applicable Pattern**: Session start hooks could write a timestamp file; subsequent hooks verify recency:

```powershell
$briefingTimestamp = Get-Content "$CLAUDE_PROJECT_DIR/.claude/state/last-briefing.txt"
if ((Get-Date) - [DateTime]$briefingTimestamp -gt [TimeSpan]::FromMinutes(60)) {
    return @{ decision = "block"; reason = "COUNSEL_EXPIRED: Re-read context" }
}
```

### Memory Categories with Decay

Daem0n implements four memory categories with different persistence models:

| Category | Decay | Boost | ai-agents Equivalent |
|----------|-------|-------|---------------------|
| Decision | 30-day half-life | 1.5x if failed | ADR decisions |
| Pattern | Permanent | None | Serena memories |
| Warning | Permanent | 1.2x | Security patterns |
| Learning | 30-day half-life | None | Retrospective findings |

**Key Insight**: The `worked=False` boost (1.5x for failed approaches) is powerful. Memories about what NOT to do should surface more prominently.

**Applicable Pattern**: Add `outcome` field to Serena memories; query for failures when planning similar work.

### Git Pre-Commit Integration

Daem0n's pre-commit hook enforces:

1. **Pending Decision Validation**: Block commits if decisions older than 24 hours lack outcomes
2. **File-Level Validation**: Block if staged files have associated `worked=False` memories

**Applicable Pattern**: Extend existing git hooks to:

- Block commits if session log missing required sections
- Warn if modified files have associated warning memories

### Hook Configuration Example

From `hooks/settings.json.example`:

```json
{
  "SessionStart": [{
    "matcher": "startup|resume",
    "hooks": [{
      "type": "command",
      "command": "echo '[Daem0n awakens] Commune with me via get_briefing()...'"
    }]
  }],
  "PreToolUse": [{
    "matcher": "Edit|Write|NotebookEdit",
    "hooks": [{
      "type": "command",
      "command": "echo '[Daem0n whispers] Consult my memories before altering files...'"
    }]
  }],
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "echo '[Daem0n whispers] Consider recording this change with remember()...'"
    }]
  }],
  "Stop": [{
    "matcher": "",
    "hooks": [{
      "type": "command",
      "command": "python3 \"$HOME/Daem0nMCP/hooks/daem0n_stop_hook.py\""
    }]
  }]
}
```

**Key Insight**: Stop hooks run a Python script for complex validation. The ai-agents project should follow this pattern for Stop hooks rather than inline shell commands.

### Implementation Recommendations from Daem0n

| Daem0n Pattern | ai-agents Implementation |
|----------------|-------------------------|
| Sacred Covenant state machine | Session state tracking in `.claude/state/` |
| Preflight tokens | Timestamp-based session validation |
| Memory decay | Add `created_at` and `outcome` to memories |
| Failed decision boosting | Query `outcome=failed` memories first |
| Pre-commit blocking | Extend existing git hooks |
| Ritual naming ("Communion", "Counsel") | Clear naming for protocol phases |

### High-Value Opportunities from Daem0n

1. **PostToolUse for memory prompts**: After Write/Edit, prompt to record learnings
2. **Stop hook for outcome recording**: Remind to record decision outcomes
3. **Preflight token validation**: Verify context check freshness
4. **Failed memory surfacing**: Boost failed approaches in recall
5. **Pending decision tracking**: Block commits with stale decisions

---

## References

- Official Documentation: <https://www.claude.com/blog/how-to-configure-hooks>
- ADR-008: `.agents/architecture/ADR-008-protocol-automation-lifecycle-hooks.md`
- ADR-007: `.agents/architecture/ADR-007-memory-first-architecture.md`
- SESSION-PROTOCOL: `.agents/SESSION-PROTOCOL.md`
- Current Hooks: `.claude/hooks/`
- Daem0n-MCP: <https://github.com/DasBluEyedDevil/Daem0n-MCP>
- Daem0n DeepWiki: <https://deepwiki.com/DasBluEyedDevil/Daem0n-MCP>
