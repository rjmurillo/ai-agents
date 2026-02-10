# Session Protocol

> **Status**: Canonical Source of Truth
> **Last Updated**: 2026-02-07
> **Protocol Version**: 2.1
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

### Phase 0: Get oriented (BLOCKING)

The agent MUST check recent commits and current branch

1. The agent MUST run `git branch --show-current` to verify correct branch
2. The agent MUST verify the branch matches the intended work context (issue, PR, feature)
3. The agent MUST NOT proceed with work if on `main` or `master` branch (create feature branch first)
4. The agent MUST check recent commits `git log --oneline -5`

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
2. The agent MUST read the `memory-index` Serena memory to identify task-relevant memories
3. The agent MUST read memories from `memory-index` that match the task keywords before modifying code or files
4. The agent SHOULD read `.agents/planning/enhancement-PROJECT-PLAN.md` if working on enhancement project
5. The agent MAY read additional context files based on task requirements
6. **PR Review Comments**: If responding to PR comments, the agent MUST classify by type (CWE/style/docs) and route to appropriate skill BEFORE manual fixes

### Retrieval-Led Reasoning (CRITICAL)

**Before proceeding with task, internalize this principle**:

You have two information sources:
1. **Pre-training**: Static, potentially outdated, no project context
2. **Retrieval**: Current, accurate, project-specific

**Always prefer retrieval.** Specifically:

- Session protocol → THIS DOCUMENT (SESSION-PROTOCOL.md)
- Project constraints → PROJECT-CONSTRAINTS.md
- Learned patterns → Serena memories via memory-index
- Architecture → ADRs in .agents/architecture/
- Framework/library APIs → Context7, DeepWiki, official docs

**Common failure**: Using outdated framework knowledge from pre-training when current docs are available.
**Correct approach**: Read memory-index, identify relevant memories, load them BEFORE reasoning.

**Memory Loading Protocol:**

The `memory-index` maps task keywords to essential memories. Example workflow:

```text
1. Identify task keywords (e.g., "pr review", "powershell", "github cli")
2. Read memory-index, find matching rows
3. Load listed memories (e.g., skills-pr-review-index, skills-powershell-index)
4. Apply learned patterns from memories before proceeding
```

**Evidence**: 30% session efficiency loss observed when memories not loaded first (skill-init-003-memory-first-monitoring-gate).

**Verification:**

- File contents appear in session context
- Agent references prior decisions from HANDOFF.md
- Agent does not ask questions answered in HANDOFF.md
- Session log Protocol Compliance section lists memories read (in Evidence column)

**Rationale:** Agents are expert amnesiacs. Without reading HANDOFF.md, they will repeat completed work or contradict prior decisions. Note: HANDOFF.md is a read-only reference; do not modify it during sessions. Without loading relevant memories, agents repeat solved problems or miss established patterns.

### Phase 3: Import Shared Memories (RECOMMENDED)

The agent SHOULD import shared memories at session start.

**Requirements:**

1. The agent SHOULD run the import script:

   ```bash
   pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1
   ```

2. The agent SHOULD document import count in session log
3. The agent MAY skip if no memory files present

**Verification:**

- Import script executed in session transcript
- Import count documented in session log

**Rationale:** Shared memory exports enable team collaboration, onboarding, and cross-session knowledge transfer. Script is idempotent with automatic duplicate prevention.

**Detailed Workflow**: See [.claude-mem/memories/AGENTS.md](../.claude-mem/memories/AGENTS.md) and [MEMORY-MANAGEMENT.md](governance/MEMORY-MANAGEMENT.md)

### Phase 4: Skill Validation (BLOCKING)

The agent MUST validate skill availability before starting work. This is a **blocking gate**.

**Requirements:**

1. The agent MUST verify `.claude/skills/` directory exists
2. The agent MUST list available GitHub skill scripts:

   ```powershell
   Get-ChildItem -Path ".claude/skills/github/scripts" -Recurse -Filter "*.ps1" | Select-Object -ExpandProperty Name
   ```

3. The agent MUST read the usage-mandatory memory using `mcp__serena__read_memory` with `memory_file_name="usage-mandatory"`
  - If the serena MCP is not available, then the agent MUST read `.serena/memories/usage-mandatory.md`
4. The agent MUST read `.agents/governance/PROJECT-CONSTRAINTS.md`
5. The agent MUST document available skills in session log under "Skill Inventory"

**Verification:**

- Directory listing output appears in session transcript
- Memory content loaded in context
- Session log contains Skill Inventory section

**Rationale:** Session 15 had 5+ skill violations despite documentation. Trust-based compliance fails; verification-based enforcement (like Serena init) has 100% compliance.

### Phase 5: Session Log Creation (REQUIRED)

The agent MUST create a session log early in the session.

**MUST Use session-init Skill**: Agents MUST use the session-init skill to create session logs with verification-based enforcement. This prevents recurring CI validation failures.

**Automated Creation** (Recommended):

```bash
# Using slash command (Claude Code)
/session-init

# Using PowerShell script
pwsh .claude/skills/session-init/scripts/New-SessionLog.ps1 -SessionNumber 375 -Objective "Implement feature X"
```

The script will:

1. Prompt for session number and objective (if not provided)
2. Auto-detect git state (branch, commit, date, status)
3. Load JSON schema from `.agents/schemas/session-log.schema.json`
4. Replace placeholders with actual values
5. Write session log with EXACT template format
6. Validate immediately with validate_session_json.py
7. Exit nonzero on validation failure

See: `.claude/skills/session-init/SKILL.md`

**Requirements:**

1. The agent MUST create a session log file at `.agents/sessions/YYYY-MM-DD-session-NN.json`
2. The session log SHOULD be created within the first 5 tool calls of the session
3. The session log MUST include the Protocol Compliance section (see template below)
4. The agent MUST NOT defer session log creation to the end of the session

**Verification:**

- Session log file exists with correct naming pattern
- File contains Protocol Compliance section
- Timestamp shows early creation, not late

**Rationale:** Late session log creation reduces traceability and often results in incomplete documentation when sessions end unexpectedly.

### Phase 4: Branch Verification (BLOCKING)

The agent MUST verify and declare the current branch before starting work. This is a **blocking gate**.

**Requirements:**

1. The agent MUST run `git branch --show-current` to verify correct branch
2. The agent MUST document the branch name in the session log header
3. The agent MUST verify the branch matches the intended work context (issue, PR, feature)
4. The agent MUST NOT proceed with work if on `main` or `master` branch (create feature branch first)
5. The agent SHOULD run `git status` to understand current working state
6. The agent SHOULD run `git log --oneline -1` to note starting commit

**Verification:**

- Session log contains branch name in Session Info section
- Branch matches conventional naming patterns (feat/*, fix/*, docs/*, etc.)
- Agent is not working on main/master (unless explicitly approved)

**Rationale:** PR #669 retrospective identified that 100% of wrong-branch commits were caused by lack of branch verification gates. Trust-based compliance fails; verification-based enforcement prevents cross-PR contamination.

**Exit Criteria:** Branch name documented in session log before any file modifications.

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
| MUST | Read usage-mandatory memory | [ ] | Content in context |
| MUST | Read PROJECT-CONSTRAINTS.md | [ ] | Content in context |
| MUST | Read memory-index, load task-relevant memories | [ ] | List memories loaded |
| SHOULD | Import shared memories: `pwsh .claude-mem/scripts/Import-ClaudeMemMemories.ps1` | [ ] | Import count: N (or "None") |
| MUST | Verify and declare current branch | [ ] | Branch documented below |
| MUST | Confirm not on main/master | [ ] | On feature branch |
| SHOULD | Verify git status | [ ] | Output documented below |
| SHOULD | Note starting commit | [ ] | SHA documented below |

### Skill Inventory

Available GitHub skills:

- [List from directory scan]

### Git State

- **Status**: [clean/dirty]
- **Branch**: [branch name - REQUIRED]
- **Starting Commit**: [SHA]

### Branch Verification

**Current Branch**: [output of `git branch --show-current`]
**Matches Expected Context**: [Yes/No - explain if No]

### Work Blocked Until

All MUST requirements above are marked complete.
```

---

## Session Mid Protocol

### Commit Count Monitoring (RECOMMENDED)

The agent SHOULD monitor commit count during extended sessions to avoid oversized PRs.

**Requirements:**

1. The agent SHOULD run the following command periodically during the session:

   ```bash
   git rev-list --count HEAD ^origin/main
   ```

2. The agent SHOULD warn when commit count reaches 15 or more
3. The agent MUST NOT exceed 20 commits without splitting into a new PR
4. When the limit is reached, the agent MUST:
   - Stop new work
   - Complete the current unit of work
   - Prepare for PR creation (proceed to Session End Protocol)
   - Create a follow-up issue or session for remaining work

**Thresholds:**

| Commit Count | Action |
|-------------|--------|
| < 15 | Continue working |
| 15-19 | WARNING: Plan to wrap up soon. Finish current task, avoid starting new tasks. |
| >= 20 | BLOCKED: Stop work. Complete current unit and proceed to Session End Protocol. |

**Verification:**

- Session log notes commit count checks during session
- No PR exceeds 20 commits without documented exception

**Rationale:** PR #908 retrospective identified that large PRs (20+ commits) are harder to review, more likely to contain co-mingled changes, and have higher revert risk. See `.agents/governance/PROJECT-CONSTRAINTS.md` for the canonical commit limit policy.

---

## Session End Protocol

### Phase 0.5: Export Session Memories (RECOMMENDED)

The agent SHOULD export memories created during the session for sharing and version control.

**Requirements:**

1. The agent SHOULD export memories using session-specific naming:

   ```bash
   pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "[query]" -SessionNumber NNN -Topic "topic"
   ```

2. The agent MUST perform security review before committing (BLOCKING):

   ```bash
   # Option 1: PowerShell security review script (recommended)
   pwsh scripts/Review-MemoryExportSecurity.ps1 -ExportFile [export-file].json

   # Option 2: Manual grep scan
   grep -iE "api[_-]?key|password|token|secret|credential|private[_-]?key" [export-file].json

   # If matches found: Review manually, redact/delete sensitive data, re-scan
   ```

3. The agent MUST NOT commit exports containing sensitive data
4. The agent SHOULD document export file path in session log
5. The agent MAY skip export for sessions without significant memory creation

**Security Review Checklist (MUST verify before commit):**

- [ ] No API keys, access tokens, or passwords
- [ ] No private file paths (e.g., `/home/username/`)
- [ ] No confidential business logic or proprietary algorithms
- [ ] No personal identifying information (PII)
- [ ] No database connection strings or credentials

**Verification:**

- Export file exists at `.claude-mem/memories/[file].json`
- Security scan completed (no sensitive patterns found)
- Export file path documented in session log

**Rationale:** Export files contain plain text memory data. Committing sensitive information to git creates permanent security risks. Security review is BLOCKING before commit.

**Detailed Workflow**: See [.claude-mem/memories/AGENTS.md](../.claude-mem/memories/AGENTS.md) and [MEMORY-MANAGEMENT.md](governance/MEMORY-MANAGEMENT.md)

### Phase 1: Documentation Update (REQUIRED)

The agent MUST update documentation before ending.

**Requirements:**

1. The agent MUST NOT update `.agents/HANDOFF.md` directly. Session context MUST go to:
   - Your session log at `.agents/sessions/YYYY-MM-DD-session-NN.json`
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

1. The agent MUST run scoped markdownlint on changed markdown files (per ADR-043):

   **Bash:**

   ```bash
   CHANGED_MD=$(git diff --name-only --diff-filter=d HEAD '*.md' 2>/dev/null)
   if [ -n "$CHANGED_MD" ]; then
     echo "$CHANGED_MD" | xargs npx markdownlint-cli2 --fix --no-globs
   fi
   ```

   **PowerShell:**

   ```powershell
   $ChangedMd = git diff --name-only --diff-filter=d HEAD '*.md' 2>$null
   if ($ChangedMd) {
       npx markdownlint-cli2 --fix --no-globs $ChangedMd
   }
   ```

   The agent MAY run repository-wide formatting (`npx markdownlint-cli2 --fix "**/*.md"`) only when:
   - Session objective explicitly includes "format all files"
   - Creating a dedicated formatting cleanup PR

2. The agent SHOULD run validation scripts if available (e.g., `Validate-Consistency.ps1`)
3. The agent SHOULD check memory sizes if `.serena/memories/` files were created or modified:

   ```bash
   python3 scripts/memory/validate_memory_sizes.py .serena/memories --pattern "*.md"
   ```

   - New memories over 10,000 characters (~2,500 tokens) need decomposition before commit
   - Modified memories over 8,000 characters should be flagged for future decomposition
   - See `.serena/memories/README.md` for decomposition guidelines

4. The agent MUST NOT end session with known failing lints

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
4. The agent MAY skip QA validation when:
   - **Docs-only**: All modified files are documentation files (e.g., Markdown), and changes are strictly editorial (spelling, grammar, or formatting) with no changes to code, configuration, tests, workflows, or code blocks of any kind. Use evidence: `SKIPPED: docs-only`
   - **Investigation-only**: Session is investigation-only (no code/config changes), with staged files limited to investigation artifacts: `.agents/sessions/`, `.agents/analysis/`, `.agents/retrospective/`, `.serena/memories/`, `.agents/security/`. Use evidence: `SKIPPED: investigation-only` (see ADR-034)

**Session Log Exemption:**

Session logs (`.agents/sessions/`), analysis artifacts (`.agents/analysis/`), and memory updates (`.serena/memories/`) are **audit trail, not implementation**. They are automatically filtered out when determining if QA validation is required. This allows session logs to be committed alongside implementation files without requiring separate commits or investigation-only skips.

**Testing Quality Checklist** (evidence-based, per `.agents/governance/TESTING-ANTI-PATTERNS.md`):

- [ ] Security-critical paths have 100% coverage (secret handling, input validation, command execution, path sanitization, auth checks)
- [ ] Tests verify behavior, not just execution (meaningful assertions)
- [ ] Coverage gaps exist only in low-risk code (read-only, documentation generation)
- [ ] No coverage theater (tests exist for evidence, not metrics)

**Verification:**

- QA report exists in `.agents/qa/`
- QA agent confirms validation passed
- No critical issues remain unaddressed
- Testing quality checklist items satisfied

**Rationale:** Untested code may contain bugs or security vulnerabilities. QA validation catches issues before they are committed to the repository. Testing should increase stakeholder confidence through evidence (Dan North), with 100% coverage required for security-critical code (Rico Mariani).

#### Investigation Session Examples

**Valid investigation sessions** (may use `SKIPPED: investigation-only`):

1. **Pure analysis** - Reading code, documenting findings in `.agents/analysis/`
2. **Memory updates** - Cross-session context updates in `.serena/memories/`
3. **CI debugging** - Investigating CI failures, documenting in session log
4. **Security assessments** - Writing security analysis to `.agents/security/`
5. **Retrospectives** - Extracting learnings to `.agents/retrospective/`

**Not investigation sessions** (require QA validation):

- Planning sessions that produce PRDs
- Architecture sessions that produce ADRs
- Implementation sessions that touch code
- Critique sessions that gate implementation

#### Mixed Session Recovery

When an investigation session discovers code changes are needed:

1. **Complete investigation artifacts** - Finish analysis docs and session log
2. **Commit investigation work** - Use `SKIPPED: investigation-only` evidence
3. **Start NEW session** - Create new session for code changes (with QA validation)
4. **Reference investigation session** - Link in Related Sessions section

**Branch Strategy**: Continue on SAME branch. The investigation commit clears staged investigation artifacts before the implementation session begins.

**Example Session Log Reference**:

```markdown
## Related Sessions

- Session 106: Investigation that discovered the issue
```

### Phase 2.7: Pre-PR Validation (REQUIRED)

The agent MUST run pre-PR validation before creating a pull request. This is a **blocking gate** for PR creation.

**Requirements:**

1. The agent MUST run the PR readiness validation script:

   ```bash
   pwsh .agents/scripts/Validate-PRReadiness.ps1
   ```

2. The script validates:
   - Commit count is within limit (< 20)
   - No BLOCKING synthesis issues detected
   - Session log exists and is valid
   - All required quality checks have passed
3. The agent MUST NOT create a PR if the validation script exits with a non-zero code
4. The agent MUST resolve all BLOCKING issues before proceeding
5. The agent SHOULD document validation results in the session log

**Verification Checklist:**

- [ ] `Validate-PRReadiness.ps1` executed and passed (exit code 0)
- [ ] No BLOCKING issues in validation output
- [ ] Commit count within limits
- [ ] Session log complete and valid

**Verification:**

- Validation script output appears in session transcript
- Exit code 0 confirms readiness
- Session log records validation pass

**Rationale:** PR #908 post-mortem revealed that PRs created without pre-validation contained co-mingled changes, missing QA reports, and exceeded commit limits. Automated validation catches these issues before PR creation, reducing review burden and revert risk.

### Phase 3: Git Operations (REQUIRED)

The agent MUST commit changes before ending.

**Requirements:**

1. The agent MUST re-verify current branch before EVERY commit:

   ```bash
   CURRENT_BRANCH=$(git branch --show-current)
   # Verify matches session log declaration
   ```

2. The agent MUST NOT commit if branch mismatch detected (stop and investigate)
3. The agent MUST stage all changed files including `.agents/` files
4. The agent MUST commit with conventional commit message format
5. The agent SHOULD verify clean git status after commit
6. The agent MAY push to remote if appropriate

**Verification:**

- Branch matches session log declaration before each commit
- `git status` shows clean state (or intentionally dirty with explanation)
- Commit exists with conventional format

**Branch Mismatch Recovery:**

If `git branch --show-current` differs from session log declaration:

1. **STOP** - Do not commit
2. **Document** the discrepancy in session log
3. **Investigate** - How did branch change?
4. **Resolve** - Either switch back or update session log with justification
5. **Resume** - Only after branch is confirmed correct

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
| SHOULD | Export session memories: `pwsh .claude-mem/scripts/Export-ClaudeMemMemories.ps1 -Query "[query]" -SessionNumber NNN -Topic "topic"` | [ ] | Export file: [path] (or "Skipped") |
| MUST | Security review export (if exported): `grep -iE "api[_-]?key|password|token|secret|credential|private[_-]?key" [file].json` | [ ] | Scan result: "Clean" or "Redacted" |
| MUST | Complete session log (all sections filled) | [ ] | File complete |
| MUST | Update Serena memory (cross-session context) | [ ] | Memory write confirmed |
| MUST | Run markdown lint | [ ] | Lint output clean |
| MUST | Route to qa agent (feature implementation) | [ ] | QA report: `.agents/qa/[report].md` OR `SKIPPED: investigation-only` |
| MUST | Run pre-PR validation: `pwsh .agents/scripts/Validate-PRReadiness.ps1` | [ ] | Exit code 0 |
| MUST | Commit all changes (including .serena/memories) | [ ] | Commit SHA: _______ |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [ ] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [ ] | Tasks checked off |
| SHOULD | Invoke retrospective (significant sessions) | [ ] | Doc: _______ |
| SHOULD | Check memory sizes (if memories modified) | [ ] | `python3 .claude/skills/memory/scripts/test_memory_size.py` |
| SHOULD | Verify clean git status | [ ] | `git status` output |

<!-- Investigation sessions may skip QA with evidence "SKIPPED: investigation-only"
     when only staging: .agents/sessions/, .agents/analysis/, .agents/retrospective/,
     .serena/memories/, .agents/security/
     See ADR-034 for details. -->
```

---

## Session Log Template

Session logs must be in JSON format. The JSON schema is at `.agents/schemas/session-log.schema.json`.

**Creation**:

```bash
pwsh .claude/skills/session-init/scripts/New-SessionLog.ps1
# Auto-increments session number, derives objective from branch
```

**Required top-level fields**:

- `schemaVersion` (string): "1.0"
- `session` (object): number, date, branch, startingCommit, objective
- `protocolCompliance` (object): sessionStart, sessionEnd checklists
- `workLog` (array): session activities
- `endingCommit` (string): final commit SHA
- `nextSteps` (array): follow-up actions

**Validation**:

```bash
# JSON schema validation (structural)
pwsh -Command "Test-Json -Json (Get-Content [session].json -Raw) -Schema (Get-Content .agents/schemas/session-log.schema.json -Raw)"

# Script validation (business rules)
python3 scripts/validate_session_json.py [session].json
```

For detailed schema structure, load `.agents/schemas/session-log.schema.json` when needed.

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

The `validate_session_json.py` script checks session protocol compliance:

```bash
# Validate current session
python3 scripts/validate_session_json.py .agents/sessions/2025-12-17-session-01.json
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

## Related Documents

- [AGENTS.md](../AGENTS.md) - Full agent catalog and workflows
- [CLAUDE.md](../CLAUDE.md) - Claude Code entry point
- [AGENT-INSTRUCTIONS.md](./AGENT-INSTRUCTIONS.md) - Task execution protocol
- [HANDOFF.md](./HANDOFF.md) - Session context
- [PROTOCOL-ANTIPATTERNS.md](./governance/PROTOCOL-ANTIPATTERNS.md) - Protocol design antipatterns and replacement patterns
