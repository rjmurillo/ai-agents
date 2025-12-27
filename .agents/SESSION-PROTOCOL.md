# Session Protocol

> **Status**: Canonical Source of Truth
> **Last Updated**: 2025-12-18
> **RFC 2119**: This document uses RFC 2119 key words to indicate requirement levels.

This document is the **single canonical source** for session protocol requirements. All other documents (CLAUDE.md, AGENTS.md, AGENT-INSTRUCTIONS.md) MUST reference this document rather than duplicate its content.

---

## RFC 2119 Key Words

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

| Key Word | Meaning |
|----------|---------|
| **MUST** / **REQUIRED** / **SHALL** | Absolute requirement; violation is a protocol failure |
| **MUST NOT** / **SHALL NOT** | Absolute prohibition; violation is a protocol failure |
| **SHOULD** / **RECOMMENDED** | Strong recommendation; deviation requires documented justification |
| **SHOULD NOT** / **NOT RECOMMENDED** | Strong discouragement; use requires documented justification |
| **MAY** / **OPTIONAL** | Truly optional; no justification needed |

---

## Protocol Enforcement Model

### Trust-Based vs Verification-Based

This protocol uses **verification-based enforcement**. Protocol compliance is verified through:

1. **Technical controls** that block work until requirements are met
2. **Observable checkpoints** that produce verifiable evidence
3. **Validation tooling** that detects violations automatically

Labels like "MANDATORY" or "NON-NEGOTIABLE" are insufficient. Each requirement MUST have a verification mechanism.

### Verification Mechanisms

| Requirement Type | Verification Method |
|-----------------|---------------------|
| Tool calls | Tool output exists in session transcript |
| File reads | Content appears in session context |
| File writes | File exists with expected content |
| Git operations | Git log/status shows expected state |
| Checklist completion | Session log contains completed checklist |

---

## Session Start Protocol

### Phase 1: Serena Initialization (BLOCKING)

The agent MUST complete Serena initialization before any other action. This is a **blocking gate**.

**Requirements:**

1. The agent MUST call `mcp__serena__activate_project` with the project path as the first tool call
2. The agent MUST call `mcp__serena__initial_instructions` immediately after activation
3. The agent MUST NOT read files, search code, or respond to user requests until both calls succeed
4. If either call fails, the agent MUST report the failure and stop

**Verification:**

- Tool call outputs appear in session transcript
- Memories become available for reading
- Serena tools (find_symbol, etc.) become functional

**Rationale:** Without Serena initialization, agents lack access to project memories, semantic code tools, and historical context. This causes repeated mistakes and lost decisions.

### Phase 2: Context Retrieval (BLOCKING)

The agent MUST read context documents before starting work. This is a **blocking gate**.

**Requirements:**

1. The agent MUST read `.agents/HANDOFF.md` for previous session context (READ-ONLY reference)
2. The agent SHOULD read relevant Serena memories based on task topic
3. The agent SHOULD read `.agents/planning/enhancement-PROJECT-PLAN.md` if working on enhancement project
4. The agent MAY read additional context files based on task requirements

**Verification:**

- File contents appear in session context
- Agent references prior decisions from HANDOFF.md
- Agent does not ask questions answered in HANDOFF.md

**Rationale:** Agents are expert amnesiacs. Without reading HANDOFF.md, they will repeat completed work or contradict prior decisions. Note: HANDOFF.md is a read-only reference; do not modify it during sessions.

### Phase 1.5: Skill Validation (BLOCKING)

The agent MUST validate skill availability before starting work. This is a **blocking gate**.

**Requirements:**

1. The agent MUST verify `.claude/skills/` directory exists
2. The agent MUST list available GitHub skill scripts:

   ```powershell
   Get-ChildItem -Path ".claude/skills/github/scripts" -Recurse -Filter "*.ps1" | Select-Object -ExpandProperty Name
   ```

3. The agent MUST read the skill-usage-mandatory memory using `mcp__serena__read_memory` with `memory_file_name="skill-usage-mandatory"`
  - If the serena MCP is not available, then the agent MUST read `.serena/memories/skill-usage-mandatory.md`
4. The agent MUST read `.agents/governance/PROJECT-CONSTRAINTS.md`
5. The agent MUST document available skills in session log under "Skill Inventory"

**Verification:**

- Directory listing output appears in session transcript
- Memory content loaded in context
- Session log contains Skill Inventory section

**Rationale:** Session 15 had 5+ skill violations despite documentation. Trust-based compliance fails; verification-based enforcement (like Serena init) has 100% compliance.

### Phase 3: Session Log Creation (REQUIRED)

The agent MUST create a session log early in the session.

**Requirements:**

1. The agent MUST create a session log file at `.agents/sessions/YYYY-MM-DD-session-NN.md`
2. The session log SHOULD be created within the first 5 tool calls of the session
3. The session log MUST include the Protocol Compliance section (see template below)
4. The agent MUST NOT defer session log creation to the end of the session

**Verification:**

- Session log file exists with correct naming pattern
- File contains Protocol Compliance section
- Timestamp shows early creation, not late

**Rationale:** Late session log creation reduces traceability and often results in incomplete documentation when sessions end unexpectedly.

### Phase 4: Git State Verification (RECOMMENDED)

The agent SHOULD verify git state before starting work.

**Requirements:**

1. The agent SHOULD run `git status` to understand current working state
2. The agent SHOULD run `git branch --show-current` to verify correct branch
3. The agent SHOULD run `git log --oneline -1` to note starting commit
4. The agent SHOULD document git state in session log

**Verification:**

- Session log contains git state information
- Agent is aware of uncommitted changes

**Rationale:** Understanding git state prevents confusion about what changes belong to the current session vs. prior work.

---

## Session Start Checklist

Copy this checklist to each session log and verify completion:

```markdown
## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [ ] | Tool output present |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [ ] | Tool output present |
| MUST | Read `.agents/HANDOFF.md` | [ ] | Content in context |
| MUST | Create this session log | [ ] | This file exists |
| MUST | List skill scripts in `.claude/skills/github/scripts/` | [ ] | Output documented below |
| MUST | Read skill-usage-mandatory memory | [ ] | Content in context |
| MUST | Read PROJECT-CONSTRAINTS.md | [ ] | Content in context |
| SHOULD | Search relevant Serena memories | [ ] | Memory results present |
| SHOULD | Verify git status | [ ] | Output documented below |
| SHOULD | Note starting commit | [ ] | SHA documented below |

### Skill Inventory

Available GitHub skills:

- [List from directory scan]

### Git State

- **Status**: [clean/dirty]
- **Branch**: [branch name]
- **Starting Commit**: [SHA]

### Work Blocked Until

All MUST requirements above are marked complete.
```

---

## Session End Protocol

### Phase 1: Documentation Update (REQUIRED)

The agent MUST update documentation before ending.

**Requirements:**

1. The agent MUST NOT update `.agents/HANDOFF.md` directly. Session context MUST go to:
   - Your session log at `.agents/sessions/YYYY-MM-DD-session-NN.md`
   - Serena memory for cross-session context (using `mcp__serena__write_memory` or equivalent)
   - `.agents/handoffs/{branch}/{session}.md` for branch-specific handoff (if on feature branch)
2. The agent MUST complete the session log with:
   - Tasks attempted and outcomes
   - Decisions made with rationale
   - Challenges encountered and resolutions
   - Link reference for next session handoff
3. The agent SHOULD update PROJECT-PLAN.md if tasks were completed
4. The agent MAY read `.agents/HANDOFF.md` for historical context (read-only reference)

**Verification:**

- Session log contains complete information
- Serena memory updated with relevant context
- PROJECT-PLAN.md checkboxes updated if applicable
- HANDOFF.md is NOT modified (unless explicitly approved by architect)

### Phase 2: Quality Checks (REQUIRED)

The agent MUST run quality checks before ending.

**Requirements:**

1. The agent MUST run `npx markdownlint-cli2 --fix "**/*.md"` to fix markdown issues
2. The agent SHOULD run validation scripts if available (e.g., `Validate-Consistency.ps1`)
3. The agent MUST NOT end session with known failing lints

**Verification:**

- Markdownlint output shows no errors
- Validation scripts pass or issues documented

### Phase 2.5: QA Validation (BLOCKING)

The agent MUST route to the qa agent after feature implementation. This is a **blocking gate**.

**Requirements:**

1. The agent MUST invoke the qa agent after completing feature implementation:

   ```python
   Task(subagent_type="qa", prompt="Validate [feature name]")
   ```

2. The agent MUST wait for QA validation to complete
3. The agent MUST NOT commit feature code without QA validation
4. The agent MAY skip QA validation only when all modified files are documentation files (e.g., Markdown), and changes are strictly editorial (spelling, grammar, or formatting) with no changes to code, configuration, tests, workflows, or code blocks of any kind

**Verification:**

- QA report exists in `.agents/qa/`
- QA agent confirms validation passed
- No critical issues remain unaddressed

**Rationale:** Untested code may contain bugs or security vulnerabilities. QA validation catches issues before they are committed to the repository.

### Phase 3: Git Operations (REQUIRED)

The agent MUST commit changes before ending.

**Requirements:**

1. The agent MUST stage all changed files including `.agents/` files
2. The agent MUST commit with conventional commit message format
3. The agent SHOULD verify clean git status after commit
4. The agent MAY push to remote if appropriate

**Verification:**

- `git status` shows clean state (or intentionally dirty with explanation)
- Commit exists with conventional format

### Phase 4: Retrospective (RECOMMENDED)

The agent SHOULD invoke retrospective for significant sessions.

**Requirements:**

1. The agent SHOULD invoke retrospective agent for sessions with:
   - Multiple tasks completed
   - Significant challenges encountered
   - New patterns discovered
   - Process improvements identified
2. The agent MAY skip retrospective for trivial sessions (single file edits, documentation-only)

**Verification:**

- Retrospective document created (for significant sessions)
- Learnings extracted and documented

---

## Session End Checklist

Copy this checklist to each session log and verify completion:

```markdown
### Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Complete session log (all sections filled) | [ ] | File complete |
| MUST | Update Serena memory (cross-session context) | [ ] | Memory write confirmed |
| MUST | Run markdown lint | [ ] | Lint output clean |
| MUST | Route to qa agent (feature implementation) | [ ] | QA report: `.agents/qa/[report].md` |
| MUST | Commit all changes (including .serena/memories) | [ ] | Commit SHA: _______ |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [ ] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [ ] | Tasks checked off |
| SHOULD | Invoke retrospective (significant sessions) | [ ] | Doc: _______ |
| SHOULD | Verify clean git status | [ ] | `git status` output |
```

---

## Session Log Template

Create at: `.agents/sessions/YYYY-MM-DD-session-NN.md`

```markdown
# Session NN - YYYY-MM-DD

## Session Info

- **Date**: YYYY-MM-DD
- **Branch**: [branch name]
- **Starting Commit**: [SHA]
- **Objective**: [What this session aims to accomplish]

## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [ ] | Tool output present |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [ ] | Tool output present |
| MUST | Read `.agents/HANDOFF.md` | [ ] | Content in context |
| MUST | Create this session log | [ ] | This file exists |
| MUST | List skill scripts in `.claude/skills/github/scripts/` | [ ] | Output documented below |
| MUST | Read skill-usage-mandatory memory | [ ] | Content in context |
| MUST | Read PROJECT-CONSTRAINTS.md | [ ] | Content in context |
| SHOULD | Search relevant Serena memories | [ ] | Memory results present |
| SHOULD | Verify git status | [ ] | Output documented below |
| SHOULD | Note starting commit | [ ] | SHA documented below |

### Skill Inventory

Available GitHub skills:

- [List from directory scan]

### Git State

- **Status**: [clean/dirty]
- **Branch**: [branch name]
- **Starting Commit**: [SHA]

### Work Blocked Until

All MUST requirements above are marked complete.

---

## Work Log

### [Task/Topic]

**Status**: In Progress / Complete / Blocked

**What was done**:
- [Action taken]

**Decisions made**:
- [Decision]: [Rationale]

**Challenges**:
- [Challenge]: [Resolution]

**Files changed**:
- `[path]` - [What changed]

---

## Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Complete session log (all sections filled) | [ ] | File complete |
| MUST | Update Serena memory (cross-session context) | [ ] | Memory write confirmed |
| MUST | Run markdown lint | [ ] | Output below |
| MUST | Route to qa agent (feature implementation) | [ ] | QA report: `.agents/qa/[report].md` |
| MUST | Commit all changes (including .serena/memories) | [ ] | Commit SHA: _______ |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [ ] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [ ] | Tasks checked off |
| SHOULD | Invoke retrospective (significant sessions) | [ ] | Doc: _______ |
| SHOULD | Verify clean git status | [ ] | Output below |

### Lint Output

[Paste markdownlint output here]

### Final Git Status

[Paste git status output here]

### Commits This Session

- `[SHA]` - [message]

---

## Notes for Next Session

- [Important context]
- [Gotchas discovered]
- [Recommendations]
```

---

## Unattended Execution Protocol

When user indicates autonomous/unattended operation (e.g., "Drive this through to completion independently", "left unattended for several hours", "work autonomously"):

### Requirements (STRICTER than attended mode)

| Req | Requirement | Verification |
|-----|-------------|--------------|
| MUST | Create session log IMMEDIATELY (within first 3 tool calls) | Session log exists before any substantive work |
| MUST | Invoke orchestrator for task coordination | Orchestrator invoked in session transcript |
| MUST | Invoke critic before ANY merge or PR creation | Critic report exists in `.agents/critique/` |
| MUST | Invoke QA after ANY code change | QA report exists in `.agents/qa/` |
| MUST NOT | Mark security comments as "won't fix" without security agent review | Security agent approval documented |
| MUST NOT | Merge without explicit validation gate pass | All validations passed and documented |
| MUST | Document all "won't fix" decisions with rationale | Session log contains decision justification |
| MUST | Use skill scripts instead of raw commands | No raw `gh`, `curl`, or equivalent in automation |

### Rationale

Autonomous execution removes human oversight. This requires **stricter** guardrails, not looser ones. Agents under time pressure optimize for task completion over protocol compliance. Technical enforcement prevents this.

### Validation

Pre-commit hooks and CI workflows enforce unattended protocol:

1. **Session log**: Blocked by pre-commit if missing
2. **Skill usage**: WARNING in pre-commit, FAIL in PR review
3. **QA validation**: Blocked by pre-commit if code changes without QA report
4. **Merge guards**: CI blocks merge if validation incomplete

### Recovery from Violations

If autonomous agent violates protocol:

1. **Stop work immediately**
2. **Create session log** if missing
3. **Invoke missing agents** (orchestrator, critic, QA)
4. **Document violation** in session log
5. **Complete all MUST requirements** before resuming

---

## Violation Handling

### What Constitutes a Protocol Violation

| Violation Type | Severity | Response |
|---------------|----------|----------|
| Skipping MUST requirement | Critical | Stop work, complete requirement |
| Skipping SHOULD requirement | Warning | Document justification, continue |
| Skipping MAY requirement | None | No action needed |
| Fabricating evidence | Critical | Session invalid, restart |

### Recovery from Violations

If a protocol violation is discovered mid-session:

1. **Acknowledge** the violation explicitly
2. **Complete** the missed requirement immediately
3. **Document** the violation in session log
4. **Continue** work only after requirement is satisfied

Example:

```markdown
### Protocol Violation Detected

**Requirement**: MUST read `.agents/HANDOFF.md`
**Status**: Skipped
**Recovery**: Reading now before continuing work
**Timestamp**: [When detected]
```

---

## Validation Tooling

### Automated Protocol Validation

The `Validate-SessionProtocol.ps1` script checks session protocol compliance:

```powershell
# Validate current session
.\scripts\Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/2025-12-17-session-01.md"

# Validate all recent sessions
.\scripts\Validate-SessionProtocol.ps1 -All

# CI mode (exit code on failure)
.\scripts\Validate-SessionProtocol.ps1 -All -CI
```

### What Validation Checks

| Check | Description | Severity |
|-------|-------------|----------|
| Session log exists | File at expected path | Critical |
| Protocol Compliance section | Contains start/end checklists | Critical |
| MUST items checked | All MUST requirements marked complete | Critical |
| QA validation ran | QA report exists in `.agents/qa/` (feature sessions) | Critical |
| HANDOFF.md updated | Modified within session timeframe | Warning |
| Git commit exists | Commit with matching date | Warning |
| Lint ran | Evidence of markdownlint execution | Warning |

---

## Cross-Reference: Other Documents

These documents reference this protocol but MUST NOT duplicate it:

| Document | What it Should Contain |
|----------|----------------------|
| `CLAUDE.md` | Brief reference with link to this document |
| `AGENTS.md` | Brief reference with link to this document |
| `AGENT-INSTRUCTIONS.md` | Detailed task execution protocol (not session protocol) |
| `SESSION-START-PROMPT.md` | Deprecated - replaced by this document |
| `SESSION-END-PROMPT.md` | Deprecated - replaced by this document |

---

## Rationale for RFC 2119

### Why Use Formal Requirement Language

1. **Eliminates ambiguity**: "MANDATORY" can be interpreted as "very important suggestion." "MUST" is unambiguous.
2. **Enables tooling**: Scripts can parse MUST/SHOULD/MAY and verify accordingly.
3. **Supports prioritization**: Agents know which requirements can be deferred under time pressure.
4. **Industry standard**: RFC 2119 is widely understood across engineering disciplines.

### Requirement Level Selection

| Use Level | When |
|-----------|------|
| MUST | Violation would cause session failure or data loss |
| SHOULD | Violation would degrade quality but not cause failure |
| MAY | Truly optional enhancement |

---

## Document History

| Version | Date | Changes |
|---------|------|---------|

| 1.4 | 2025-12-22 | Added Unattended Execution Protocol (Issue #230) |
| 1.5 | 2025-12-22 | Added Unattended Execution Protocol (Issue #230) |
| 1.4 | 2025-12-22 | P0: Changed HANDOFF.md from MUST update to MUST NOT update; agents use session logs and Serena memory |

| 1.3 | 2025-12-20 | Added Phase 2.5 QA Validation BLOCKING gate |
| 1.2 | 2025-12-18 | Added Phase 1.5 skill validation BLOCKING gate |
| 1.1 | 2025-12-17 | Added requirement to link session log in HANDOFF.md |
| 1.0 | 2025-12-17 | Initial canonical protocol with RFC 2119 requirements |

---

## Related Documents

- [AGENTS.md](../AGENTS.md) - Full agent catalog and workflows
- [CLAUDE.md](../CLAUDE.md) - Claude Code entry point
- [AGENT-INSTRUCTIONS.md](./AGENT-INSTRUCTIONS.md) - Task execution protocol
- [HANDOFF.md](./HANDOFF.md) - Session context
