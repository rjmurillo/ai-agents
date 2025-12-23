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

1. The agent MUST read `.agents/HANDOFF.md` for previous session context
2. The agent MUST read task-specific memories before starting ANY task (see Task-Specific Memory Requirements below)
3. The agent MUST read relevant memories before agent handoffs (see Agent Handoff Memory Requirements below)
4. The agent SHOULD read `.agents/planning/enhancement-PROJECT-PLAN.md` if working on enhancement project
5. The agent MAY read additional context files based on task requirements

**Verification:**

- File contents appear in session context
- Agent references prior decisions from HANDOFF.md
- Agent does not ask questions answered in HANDOFF.md
- Task-specific memories loaded in context before work begins
- Handoff memories loaded before delegating to specialist agent

**Rationale:** Agents are expert amnesiacs. Without reading HANDOFF.md and relevant memories, they will repeat completed work, contradict prior decisions, and ignore established patterns.

#### Task-Specific Memory Requirements

The agent MUST read these memories based on task type **before** starting work:

| Task Type | REQUIRED Memories | When to Read |
|-----------|------------------|--------------|
| **PR comment response** | `skill-usage-mandatory`, `pr-comment-responder-skills`, `skills-pr-review` | Before fetching PR context |
| **GitHub operations** | `skill-usage-mandatory`, `skills-github-cli` | Before any `gh` command or GitHub skill usage |
| **PowerShell scripting** | `skills-pester-testing`, `powershell-testing-patterns` (if tests), `user-preference-no-bash-python` | Before writing PowerShell code |
| **Git hook work** | `git-hook-patterns`, `pattern-git-hooks-grep-patterns`, `pre-commit-hook-design` | Before modifying hooks |
| **CI/CD workflow** | `pattern-thin-workflows`, `skills-github-workflow-patterns` | Before editing `.github/workflows/` |
| **Security review** | `skills-security`, `pr-52-symlink-retrospective` | Before reviewing security-sensitive code |
| **Codebase architecture** | `codebase-structure`, `code-style-conventions` | Before proposing architectural changes |
| **Agent implementation** | `pattern-agent-generation-three-platforms` | Before creating/modifying agent definitions |
| **Planning tasks** | `skills-planning`, `skill-planning-001-checkbox-manifest` | Before creating PRDs or plans |
| **Documentation** | `skills-documentation`, `user-preference-no-auto-headers` | Before writing markdown docs |

**Verification:**

- Memory content appears in session context BEFORE task execution
- Agent cites specific skills/patterns from memories in reasoning
- Agent does not violate patterns documented in memories

**Example (PR Comment Response)**:

```markdown
### Phase 2 Completion Evidence

Memories loaded:
- ✅ `skill-usage-mandatory` - Read at [timestamp]
- ✅ `pr-comment-responder-skills` - Read at [timestamp]
- ✅ `skills-pr-review` - Read at [timestamp]

Key patterns identified:
- Skill-PR-001: Enumerate reviewers before triage
- Skill-PR-Review-003: Use GraphQL for thread resolution
```

#### Agent Handoff Memory Requirements

When delegating to a specialist agent, the delegating agent MUST read these memories **before** the handoff:

| Target Agent | REQUIRED Memories | Purpose |
|-------------|------------------|---------|
| **implementer** | `skills-implementation`, `code-style-conventions`, `codebase-structure` | Ensure code follows project patterns |
| **analyst** | `skills-analysis`, `skills-github-cli` (if GitHub research) | Provide research strategy context |
| **qa** | `skills-qa`, `skills-pester-testing`, `powershell-testing-patterns` | Ensure test coverage expectations |
| **planner** | `skills-planning`, `skill-planning-001-checkbox-manifest` | Provide planning structure requirements |
| **critic** | `skills-critique` | Ensure plan review criteria known |
| **architect** | `skills-architecture`, `codebase-structure` | Provide architectural constraints |
| **security** | `skills-security`, `pr-52-symlink-retrospective` | Provide known vulnerability patterns |
| **devops** | `skills-ci-infrastructure`, `pattern-thin-workflows` | Ensure CI/CD best practices |
| **pr-comment-responder** | `skill-usage-mandatory`, `pr-comment-responder-skills`, `skills-pr-review` | Provide PR review workflow |

**Verification:**

- Handoff prompt includes context from required memories
- Delegating agent demonstrates knowledge of specialist's workflow
- Specialist agent does not ask basic questions answered in memories

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

1. The agent MUST update `.agents/HANDOFF.md` with:
   - Link to session log (e.g., `[Session NN](./sessions/YYYY-MM-DD-session-NN.md)`)
   - What was completed this session
   - What should happen next session
   - Any blockers or concerns
   - Files changed
2. The agent MUST complete the session log with:
   - Tasks attempted and outcomes
   - Decisions made with rationale
   - Challenges encountered and resolutions
3. The agent SHOULD update PROJECT-PLAN.md if tasks were completed

**Verification:**

- HANDOFF.md modified timestamp is current
- Session log contains complete information
- PROJECT-PLAN.md checkboxes updated if applicable

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

### Phase 4: Memory Persistence (REQUIRED)

The agent MUST write learnings to memory before ending the session.

**Requirements:**

1. The agent MUST review session log for learnings to persist
2. The agent MUST write new memories or update existing memories using `mcp__serena__write_memory` or `mcp__serena__edit_memory`
3. The agent MUST persist learnings in these categories:
   - **Skills**: Proven strategies (95%+ atomicity, 2+ validations)
   - **Patterns**: Recurring solutions or anti-patterns
   - **Constraints**: New project constraints discovered
   - **Retrospectives**: Session-specific learnings
4. The agent SHOULD use task-specific memory naming:
   - PR review learnings → `pr-comment-responder-skills` or `skills-pr-review`
   - GitHub operations → `skills-github-cli`
   - PowerShell patterns → `powershell-testing-patterns`
   - Planning insights → `skills-planning`

**Verification:**

- At least one memory written or updated
- Session log documents what was persisted
- Memory content is actionable and reusable

**Rationale:** Without memory persistence, learnings are lost between sessions. Memory persistence enables cross-session continuity and prevents repeated mistakes.

### Phase 5: Retrospective (RECOMMENDED)

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
| MUST | Update `.agents/HANDOFF.md` (include session log link) | [ ] | File modified |
| MUST | Complete session log | [ ] | All sections filled |
| MUST | Write memories for learnings | [ ] | Memory files updated |
| MUST | Run markdown lint | [ ] | Lint output clean |
| MUST | Route to qa agent (feature implementation) | [ ] | QA report: `.agents/qa/[report].md` |
| MUST | Commit all changes (including .serena/memories) | [ ] | Commit SHA: _______ |
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
| MUST | Update `.agents/HANDOFF.md` (include session log link) | [ ] | File modified |
| MUST | Complete session log | [ ] | All sections filled |
| MUST | Write memories for learnings | [ ] | Memory files updated |
| MUST | Run markdown lint | [ ] | Output below |
| MUST | Route to qa agent (feature implementation) | [ ] | QA report: `.agents/qa/[report].md` |
| MUST | Commit all changes | [ ] | Commit SHA: _______ |
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
| 1.3 | 2025-12-20 | Added explicit memory requirements for tasks and agent handoffs; added Phase 4 memory persistence REQUIRED gate; added Phase 2.5 QA Validation BLOCKING gate |
| 1.2 | 2025-12-18 | Added Phase 1.5 skill validation BLOCKING gate |
| 1.1 | 2025-12-17 | Added requirement to link session log in HANDOFF.md |
| 1.0 | 2025-12-17 | Initial canonical protocol with RFC 2119 requirements |

---

## Related Documents

- [AGENTS.md](../AGENTS.md) - Full agent catalog and workflows
- [CLAUDE.md](../CLAUDE.md) - Claude Code entry point
- [AGENT-INSTRUCTIONS.md](./AGENT-INSTRUCTIONS.md) - Task execution protocol
- [HANDOFF.md](./HANDOFF.md) - Session context
