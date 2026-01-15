# Codex Effectiveness Backlog

> **Epic**: #[Issue Number] - Codex Effectiveness Improvements
> **Goal**: Make Codex as effective as Claude Code through verification-based enforcement
> **Status**: In Progress
> **Owner**: Codex Platform Team

## Overview

This backlog implements the Codex effectiveness epic, bringing GitHub Copilot Pro+ (VS Code extension) to parity with Claude Code through:

1. **Verification-based protocol enforcement** - Technical controls that block work until prerequisites are met
2. **Memory-first workflows** - Load `memory-index` and task-relevant memories before any work
3. **Skill-first GitHub operations** - Use validated skills instead of raw `gh` commands
4. **Context optimization** - Progressive disclosure to reduce startup tokens by 10-15%

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Session protocol compliance | 100% | Zero session logs missing required evidence |
| Startup token reduction | 10-15% | `Measure-CodexContext.ps1` baseline comparison |
| Skill-first adoption | 100% | Zero raw `gh` usage when skills exist |
| Memory-first compliance | 100% | All sessions load memory-index + task memories first |

## Task Priorities

### P0: Blocking Requirements

These tasks are **REQUIRED** for Codex to be effective. Without these, Codex sessions will:
- Skip session protocol (no continuity between sessions)
- Miss critical memories (repeat solved problems)
- Use raw commands instead of validated skills (untested code paths)

#### 1. Codex Session-Start Gate (PowerShell)

**Objective**: Create verification script that blocks work until prerequisites are met.

**Acceptance Criteria**:
- [ ] Script exists at `scripts/Invoke-CodexSessionStartGate.ps1`
- [ ] Gate 1: Memory-First Verification
  - [ ] Checks if `.serena/memories/memory-index.md` has been read
  - [ ] Verifies task-relevant memories loaded based on keywords
  - [ ] Blocks execution until memory evidence exists
- [ ] Gate 2: Skill Availability Check
  - [ ] Reuses logic from `scripts/Check-SkillExists.ps1`
  - [ ] Lists available GitHub skills in `.claude/skills/github/scripts/`
  - [ ] Verifies usage-mandatory memory loaded
- [ ] Gate 3: Session Log Verification
  - [ ] Checks for today's session log in `.agents/sessions/`
  - [ ] Validates using `scripts/Validate-SessionJson.ps1` patterns
  - [ ] Blocks work until session log exists and validates
- [ ] Gate 4: Branch Verification
  - [ ] Executes `git branch --show-current`
  - [ ] Verifies not on main/master
  - [ ] Blocks commits on wrong branch
- [ ] Exit codes follow ADR-035 standard:
  - [ ] 0: All gates passed
  - [ ] 1: Logic error in gate script
  - [ ] 2: Gate condition not met (blocking)
  - [ ] 3: External dependency failure
- [ ] Pester tests exist at `scripts/tests/Invoke-CodexSessionStartGate.Tests.ps1`
- [ ] All tests pass

**Dependencies**: 
- ADR-005 (PowerShell-only scripting)
- ADR-035 (Exit code standardization)
- `scripts/Check-SkillExists.ps1`
- `scripts/Validate-SessionJson.ps1`

**Effort Estimate**: 5-8 hours

**References**:
- `.agents/SESSION-PROTOCOL.md` - Session protocol requirements
- `.agents/architecture/ADR-033-routing-level-enforcement-gates.md` - Gate architecture

---

#### 2. Memory-First Verification Enforcement

**Objective**: Ensure Codex loads relevant memories before any work.

**Acceptance Criteria**:
- [ ] Gate 1 in `Invoke-CodexSessionStartGate.ps1` blocks until:
  - [ ] `memory-index` has been read (evidence in transcript)
  - [ ] Task-relevant memories loaded based on keyword matching
  - [ ] Memory loading documented in session log Evidence column
- [ ] Gate outputs structured JSON with pass/fail status
- [ ] Actionable error messages when memory not loaded
- [ ] Exit code 2 (gate condition not met) when blocked

**Evidence**: From `.serena/memories/skills-session-init-index.md`:
> "30% session efficiency loss observed when memories not loaded first (skill-init-003-memory-first-monitoring-gate)"

**Dependencies**: 
- Task #1 (Session-start gate script)
- `.serena/memories/memory-index.md`

**Effort Estimate**: 2-3 hours (integrated into Task #1)

---

#### 3. Skill-First GitHub Operations

**Objective**: Block raw `gh` commands when equivalent skills exist.

**Acceptance Criteria**:
- [ ] Enhanced `scripts/Detect-SkillViolation.ps1`:
  - [ ] Detects raw `gh` commands in Codex task descriptions
  - [ ] Checks for inline GitHub API calls vs skill usage
  - [ ] Scans for curl/wget when GitHub skills exist
  - [ ] Reports capability gaps with actionable remediation
  - [ ] Outputs JSON structure with violations array
- [ ] New `scripts/Validate-SkillFirst.ps1`:
  - [ ] Parses staged files for GitHub operations
  - [ ] Cross-references with available skills
  - [ ] Blocks commit if raw commands detected
  - [ ] Provides skill usage guidance
  - [ ] Exit code 0 (pass) or 1 (violations found)
- [ ] Pester tests exist:
  - [ ] `scripts/tests/Detect-SkillViolation.Tests.ps1` (enhance existing)
  - [ ] `scripts/tests/Validate-SkillFirst.Tests.ps1` (new)
- [ ] All tests pass

**Dependencies**: 
- `scripts/Detect-SkillViolation.ps1` (existing)
- `scripts/Check-SkillExists.ps1` (existing)
- `.claude/skills/github/scripts/` (existing skills)

**Effort Estimate**: 4-6 hours

**References**:
- `.serena/memories/usage-mandatory.md` - Skill-first requirement

---

#### 4. Protocol Checklist Alignment for Codex

**Objective**: Create Codex-specific protocol documentation.

**Acceptance Criteria**:
- [ ] New document at `.agents/CODEX-PROTOCOL.md`:
  - [ ] Session Start Checklist (Codex-specific)
  - [ ] Session End Checklist (Codex-specific)
  - [ ] Differences from Claude Code documented
  - [ ] Manual gate execution workflow
  - [ ] References to validation scripts
- [ ] `AGENTS.md` updated with Codex section:
  - [ ] Links to `.agents/CODEX-PROTOCOL.md`
  - [ ] Quick-start commands for Codex users
  - [ ] Highlights differences from Claude Code automation
- [ ] All markdown passes `markdownlint-cli2`

**Dependencies**: 
- Task #1 (Session-start gate script)
- `.agents/SESSION-PROTOCOL.md` (existing)

**Effort Estimate**: 3-4 hours

---

### P1: Optimization Work

These tasks **IMPROVE** Codex effectiveness but are not blocking. They provide:
- Reduced startup context (faster sessions, lower token costs)
- Better discoverability (progressive disclosure)
- Token budget tracking (measure improvements)

#### 5. Progressive Disclosure for Codex Skills and Docs

**Objective**: Reduce upfront context by 40-50% per skill through lazy loading.

**Acceptance Criteria**:
- [ ] GitHub skills restructured:
  - [ ] Main `SKILL.md`: 200-300 tokens (overview, triggers, quick examples)
  - [ ] Detailed docs moved to `references/` subdirectory
  - [ ] References pattern: "See references/pr-operations.md for details"
- [ ] Directory structure:
  ```
  .claude/skills/github/
  ├── SKILL.md (overview only)
  ├── references/
  │   ├── pr-operations.md
  │   ├── issue-operations.md
  │   ├── api-patterns.md
  │   └── error-handling.md
  └── scripts/ (existing)
  ```
- [ ] Token savings measured: 40-50% reduction per skill
- [ ] All markdown passes `markdownlint-cli2`

**Dependencies**: None (independent optimization)

**Effort Estimate**: 6-8 hours (restructure all GitHub skills)

**Token Savings**: ~2-3K tokens per skill × 10 skills = 20-30K tokens

---

#### 6. Context De-duplication

**Objective**: Eliminate redundant content between entry point documents.

**Acceptance Criteria**:
- [ ] `CLAUDE.md` optimized to ~50 lines (currently 80):
  - [ ] Remove session protocol details (link to `.agents/SESSION-PROTOCOL.md`)
  - [ ] Remove constraint details (link to `.agents/governance/PROJECT-CONSTRAINTS.md`)
  - [ ] Keep: Serena init commands, session log path, validation command
  - [ ] Add: Codex reference link
- [ ] `AGENTS.md` restructured:
  - [ ] Add progressive disclosure: "See references/..." pattern
  - [ ] Remove duplicated content from SESSION-PROTOCOL.md
  - [ ] Remove duplicated content from PROJECT-CONSTRAINTS.md
  - [ ] Keep: Agent catalog, workflow patterns, memory system overview
- [ ] `CRITICAL-CONTEXT.md` unchanged (verified as auto-loaded, no duplication)
- [ ] All markdown passes `markdownlint-cli2`

**Dependencies**: None (independent optimization)

**Effort Estimate**: 3-4 hours

**Token Savings**: ~1-2K tokens (30% reduction in CLAUDE.md)

---

#### 7. Token Budget Policy and Measurement

**Objective**: Track context usage and measure optimization impact.

**Acceptance Criteria**:
- [ ] New script at `scripts/Measure-CodexContext.ps1`:
  - [ ] Parses Codex session transcripts
  - [ ] Calculates token usage by category (docs, memories, skills, code)
  - [ ] Compares against baseline and target budgets
  - [ ] Generates optimization recommendations
  - [ ] Outputs JSON report for tracking
- [ ] Metrics defined:
  - [ ] Startup context tokens (target: 10-15% reduction)
  - [ ] Memory loading efficiency (tier 1 vs tier 2/3 ratio)
  - [ ] Skill documentation tokens (before/after progressive disclosure)
  - [ ] Session-to-session context growth rate
- [ ] Pester tests at `scripts/tests/Measure-CodexContext.Tests.ps1`
- [ ] Baseline measurement documented in `.agents/planning/codex-context-optimization-plan.md`

**Dependencies**: 
- Task #5 (Progressive disclosure - to measure improvement)
- Task #6 (Context de-duplication - to measure improvement)

**Effort Estimate**: 4-5 hours

**References**:
- `scripts/Validate-TokenBudget.ps1` (existing token validation patterns)

---

### P2: Future Enhancements

These tasks are **NICE-TO-HAVE** improvements that can be deferred:

#### 8. Direct SQLite Export Parity for Memory Backups

**Objective**: Enable direct SQLite export from Serena memory system.

**Status**: Deferred to future sprint

**Rationale**: Requires Serena MCP enhancement, not Codex-specific. Current file-based export sufficient for initial Codex effectiveness.

---

#### 9. Environment Preflight Checks

**Objective**: Verify required tools (sqlite3, pwsh, node) are available.

**Status**: Deferred to future sprint

**Rationale**: Environment setup is one-time cost. Focus P0/P1 on per-session effectiveness.

**Acceptance Criteria** (when implemented):
- [ ] Script at `scripts/Test-CodexEnvironment.ps1`
- [ ] Checks: sqlite3, pwsh, node, gh, git
- [ ] Outputs JSON with missing tools
- [ ] Exit code 0 (all present) or 2 (missing tools)

---

#### 10. Command vs Skill Taxonomy Enforcement

**Objective**: Create authoritative taxonomy of when to use raw commands vs skills.

**Status**: Deferred to future sprint

**Rationale**: Task #3 (Skill-first enforcement) addresses immediate need. Taxonomy is documentation enhancement.

**Acceptance Criteria** (when implemented):
- [ ] Document at `.agents/governance/COMMAND-VS-SKILL-TAXONOMY.md`
- [ ] Decision tree: When raw commands are acceptable
- [ ] Exceptions documented (e.g., git porcelain commands)
- [ ] Referenced in CODEX-PROTOCOL.md

---

## Implementation Order

**Sprint 1 (P0 - Week 1)**:
1. Task #1: Session-start gate script
2. Task #2: Memory-first enforcement (integrated with #1)
3. Task #4: Protocol documentation

**Sprint 2 (P0 - Week 2)**:
4. Task #3: Skill-first enforcement

**Sprint 3 (P1 - Week 3)**:
5. Task #5: Progressive disclosure
6. Task #6: Context de-duplication

**Sprint 4 (P1 - Week 4)**:
7. Task #7: Token budget tracking

**Backlog (P2)**:
- Tasks #8-10 deferred to future sprints

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| **Codex bypasses manual gates** | Document in CODEX-PROTOCOL.md that gates are BLOCKING; provide clear error messages |
| **Token measurement inaccurate** | Use existing `Validate-TokenBudget.ps1` patterns; validate against known baselines |
| **Skill-first breaks workflows** | Start with warnings (non-blocking) in Task #3; gather feedback before making blocking |
| **Progressive disclosure reduces utility** | Keep full docs in references/; ensure discoverability through clear links |

---

## Dependencies

### External Dependencies
- Serena MCP: Memory system must be functional
- GitHub CLI: Required for skill validation
- PowerShell 7+: Required for all scripts

### Internal Dependencies
- ADR-005: PowerShell-only scripting
- ADR-035: Exit code standardization
- SESSION-PROTOCOL.md: Session protocol requirements
- Existing validation scripts: `Validate-SessionJson.ps1`, `Check-SkillExists.ps1`

---

## Out of Scope

Per epic definition:
- Cross-repo policy changes outside ai-agents
- Large refactors not tied to Codex workflow effectiveness
- Claude Code-specific optimizations (this is Codex-focused)
- Serena MCP architecture changes (use existing capabilities)

---

## Related Documents

- `.agents/SESSION-PROTOCOL.md` - Session protocol (canonical source)
- `.agents/planning/codex-context-optimization-plan.md` - Token budget strategy
- `.agents/architecture/ADR-033-routing-level-enforcement-gates.md` - Gate architecture
- `.agents/architecture/ADR-035-exit-code-standardization.md` - Exit code standard
- `.serena/memories/memory-index.md` - Memory loading guidance
