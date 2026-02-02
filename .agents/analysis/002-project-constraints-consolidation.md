# Analysis: PROJECT-CONSTRAINTS.md Consolidation

## Value Statement

Consolidating scattered project constraints into a single, authoritative document would reduce agent violations by providing a clear, verifiable checkpoint in the session protocol. This analysis evaluates whether consolidation addresses the root cause of constraint violations seen in Session 15.

## Business Objectives

1. **Reduce rework**: Prevent 5+ user interventions per session due to constraint violations
2. **Increase velocity**: Eliminate 30-45 minutes of rework from language, skill usage, and commit violations
3. **Improve quality**: Shift constraint checking left to session start rather than catching violations post-implementation
4. **Enable automation**: Create verifiable checkpoints for protocol compliance

## Context

### Problem Statement

During Session 15, agents violated established constraints 5+ times despite having documentation available:

1. **Skill usage violations** (3+): Used raw `gh` commands instead of `.claude/skills/github/`
2. **Language violations** (2+): Created bash scripts despite PowerShell-only preference
3. **Workflow pattern violations**: Placed complex logic in YAML instead of modules
4. **Commit discipline violations**: Bundled 16 unrelated files in single commit

**Root cause identified**: No BLOCKING gate for constraint validation in session protocol. Documentation exists but isn't enforced through verification-based checkpoints.

### Session 15 Evidence

From `.serena/memories/retrospective-2025-12-18-session-15-pr-60.md`:

```
Session 15 successfully delivered P0-P1 security fixes and high-quality ADRs,
but required 5+ user interventions for violations of established patterns.

Root Cause: Missing BLOCKING gates for constraint validation in session protocol.
Trust-based compliance ineffective.
```

**Key insight**: "Documentation existed (memories, ADRs), but violations occurred repeatedly until user intervened."

## Methodology

### Data Collection

1. **Constraint inventory**: Catalogued all mandatory rules from ADRs, governance docs, memories, and session protocol
2. **Source analysis**: Mapped where constraints are documented and their authority levels
3. **Violation analysis**: Reviewed Session 15 retrospective for patterns
4. **Industry research**: Surveyed SSOT best practices and documentation drift prevention strategies
5. **GitHub patterns**: Examined CONTRIBUTING.md and constraint enforcement in open-source projects

### Research Tools Used

- Repository search (Glob, Grep) for constraint sources
- Web research on SSOT architecture and documentation drift prevention
- Analysis of ADR-005, ADR-006, SESSION-PROTOCOL.md, and Serena memories
- Review of Session 15 retrospective and session log

## Findings

### Facts (Verified)

#### Finding 1: Constraints Are Scattered Across 12+ Locations

**Evidence**: Mandatory constraints documented in:

| Source | Type | Constraints | Authority |
|--------|------|-------------|-----------|
| `ADR-005-powershell-only-scripting.md` | Architecture Decision | PowerShell-only, no bash/Python | HIGH |
| `ADR-006-thin-workflows-testable-modules.md` | Architecture Decision | Logic in modules, workflows <100 lines | HIGH |
| `.serena/memories/skill-usage-mandatory.md` | User Preference | Use skills, not raw `gh` | MEDIUM |
| `.serena/memories/user-preference-no-bash-python.md` | User Preference | No bash/Python scripts | MEDIUM |
| `SESSION-PROTOCOL.md` | Process Protocol | Serena init, HANDOFF read, session log | HIGH |
| `.agents/governance/naming-conventions.md` | Governance | EPIC-NNN, ADR-NNN patterns | MEDIUM |
| `.agents/governance/consistency-protocol.md` | Governance | Cross-reference validation | MEDIUM |
| `.gemini/styleguide.md` | Code Standards | PowerShell conventions, markdown style | LOW |
| `.serena/memories/task-completion-checklist.md` | Process | Atomic commits, markdown linting | MEDIUM |
| `.serena/memories/code-style-conventions.md` | Code Standards | Commit message format | LOW |
| `.serena/memories/retrospective-2025-12-18-session-15-pr-60.md` | Retrospective | Lessons from violations | LOW |
| Agent definitions (various) | Agent-specific | Tool selection, handoff patterns | MEDIUM |

**Analysis**: 12+ distinct locations containing constraints. No single source of truth.

#### Finding 2: Enforcement Gap Between Documentation and Compliance

**Evidence from Session 15**:

- Skill usage memory existed: Agent violated 3+ times
- PowerShell-only ADR existed: Agent created bash scripts
- Thin workflows pattern existed: Agent put logic in YAML
- Atomic commit guidance existed: Agent bundled 16 files

**Pattern**: Trust-based compliance ("agent will remember") fails. Verification-based compliance (tool output required) succeeds.

**Counter-evidence**: Serena initialization has BLOCKING gate in SESSION-PROTOCOL.md Phase 1:
- Requirement: "MUST call `mcp__serena__activate_project` before any other action"
- Verification: "Tool output appears in session transcript"
- **Result**: NEVER violated (100% compliance)

**Conclusion**: Documentation alone insufficient. Enforcement requires verification gates.

#### Finding 3: Constraint Categories Map to Workflow Phases

**Mapped constraint types**:

| Category | Phase | Verification Method | Current Enforcement |
|----------|-------|---------------------|---------------------|
| Session initialization | Pre-work | Tool output (Serena calls) | ✅ BLOCKING gate exists |
| Project constraints | Pre-work | File read (constraints doc) | ❌ No gate |
| Skill availability | Pre-implementation | Directory listing, script check | ❌ No gate |
| Code standards | Implementation | Linter output | ⚠️ Pre-commit hook (passive) |
| Commit discipline | Pre-commit | File count, subject parse | ❌ No gate |
| Documentation quality | Pre-commit | Markdownlint output | ✅ Pre-commit hook |

**Gap**: Pre-work and pre-implementation phases lack verification gates.

#### Finding 4: Industry Best Practices Support Consolidation with Caveats

**Single Source of Truth (SSOT) benefits** (from web research):

- Eliminates ambiguity: Everyone accesses same information
- Reduces errors: No conflicting documentation
- Simplifies maintenance: Update once, reflect everywhere
- Enables automation: Clear reference for validation

**SSOT challenges** (from web research):

- **Documentation drift**: "SSOT requires continuous maintenance to remain effective. Regular updates, data quality checks, and system optimizations can be resource-intensive."
- **Synchronization complexity**: "Integration complexity when connecting data from multiple systems with incompatible formats or mapping errors."
- **Scalability**: "If not designed for future growth, may struggle to manage increasing amounts of data."

**Key insight from DRY principle research**:

> "Every piece of knowledge must have a single, unambiguous, authoritative representation within a system."
>
> — Hunt & Thomas, *The Pragmatic Programmer*

**Applied to this context**: The principle supports consolidation, BUT "single representation" doesn't necessarily mean "single file." It means **single authoritative source** with derived views.

#### Finding 5: ADRs Are Canonical Sources, Not Derived Documents

**Analysis**: ADR-005 and ADR-006 are:

- **Authoritative**: Contain decision rationale, context, and alternatives
- **Immutable**: Should not be edited post-acceptance (only amended)
- **Rich**: Include detailed analysis beyond simple rules

**Problem with consolidation**: If PROJECT-CONSTRAINTS.md duplicates ADR content:

- Violates DRY principle (knowledge duplicated)
- Creates drift risk (ADR updated but constraints doc not, or vice versa)
- Loses context (constraints doc shows rule but not rationale)

**Alternative**: Constraints doc as **index/reference** pointing to authoritative sources, not duplication.

#### Finding 6: Session 15 Proposed PROJECT-CONSTRAINTS.md as P0 Action

**Evidence from retrospective**:

```
| Priority | Action | Impact | Effort | ROI |
|----------|--------|--------|--------|-----|
| P0 | Create PROJECT-CONSTRAINTS.md | Prevents 5+ violations | 30 min | 10x |
```

**Context from retrospective**:

> Create `.agents/governance/PROJECT-CONSTRAINTS.md` consolidating: no bash/Python,
> use skills not raw commands, atomic commits, thin workflows. Add to SESSION-PROTOCOL
> Phase 1 requirements.

**Rationale**: "5+ user interventions for violations of scattered preferences across multiple memories."

#### Finding 7: Verification-Based Gates More Effective Than Documentation

**Evidence from SESSION-PROTOCOL.md**:

```
Protocol Enforcement Model: Trust-Based vs Verification-Based

This protocol uses verification-based enforcement. Protocol compliance is verified through:
1. Technical controls that block work until requirements are met
2. Observable checkpoints that produce verifiable evidence
3. Validation tooling that detects violations automatically
```

**Effectiveness comparison**:

| Enforcement Type | Example | Violation Rate |
|-----------------|---------|----------------|
| Trust-based | "Agent should check preferences" | High (3+ violations in Session 15) |
| Verification-based (tool output) | Serena initialization gate | Zero (never violated) |
| Verification-based (file read) | HANDOFF.md read requirement | Low (occasionally skipped if file missing) |

**Conclusion**: Gate effectiveness depends on verification mechanism, not just documentation.

### Hypotheses (Unverified)

#### Hypothesis 1: Consolidation Without Gates Won't Prevent Violations

**Reasoning**: Session 15 showed agents violate constraints even when documented. Creating PROJECT-CONSTRAINTS.md without adding verification gate to SESSION-PROTOCOL.md would likely result in:

- File created but not read by agents
- Continued violations despite consolidation
- False sense of improvement

**Test needed**: Implement consolidation WITH Phase 1.5 gate requiring file read and verify violation rate.

#### Hypothesis 2: Index-Style Doc More Maintainable Than Duplication

**Reasoning**: PROJECT-CONSTRAINTS.md as **index** pointing to authoritative sources:

```markdown
## Language Constraints

**Rule**: All scripts MUST be PowerShell (.ps1, .psm1). NO bash (.sh) or Python (.py).

**Authority**: ADR-005-powershell-only-scripting.md
**Enforcement**: Pre-implementation check, code review
**Exceptions**: None

**Why this rule exists**: See ADR-005 for full rationale (token efficiency, testing consistency, cross-platform support).
```

**Benefits**:
- No duplication: Points to ADR as authoritative source
- Low drift risk: Rule extracted from ADR, but rationale stays in ADR
- Maintainable: Update ADR → re-derive constraint summary

**Test needed**: Implement index-style doc and measure maintenance burden over 10 sessions.

#### Hypothesis 3: Tiered Constraint Structure Improves Discoverability

**Reasoning**: Not all constraints equally important. Proposed tiers:

| Tier | Label | Examples | Enforcement |
|------|-------|----------|-------------|
| MUST | Blocking | PowerShell-only, use skills, Serena init | BLOCKING gates |
| SHOULD | Strong recommendation | Atomic commits, thin workflows | Code review |
| MAY | Optional guidance | Commit message format details | Linter |

**Benefits**:
- Clear priority: Agents know what's non-negotiable
- Graduated enforcement: MUST gets gates, SHOULD gets review, MAY gets linting
- Reduces cognitive load: Focus on MUST constraints first

**Test needed**: Create tiered structure and measure agent compliance per tier.

#### Hypothesis 4: Automated Constraint Validation Reduces Violations

**Reasoning**: Session 15 retrospective proposed:

```
P0: Create Check-SkillExists.ps1 | Enables automation | 20 min | 8x ROI
P1: Create commit-msg hook for atomicity | Prevents non-atomic commits | 45 min | 5x ROI
```

**Hypothesis**: Constraints with automated checks have higher compliance than manual checks.

**Test needed**: Implement `Check-SkillExists.ps1` and commit-msg hook, measure violation rate before/after.

## Consolidation Options Analysis

### Option 1: Full Consolidation (Single File, All Constraints)

**Structure**: Create `.agents/governance/PROJECT-CONSTRAINTS.md` containing ALL constraints with full text.

**Pros**:
- Single location to read
- Clear authority
- Easy to add to session protocol gate

**Cons**:
- ❌ **Duplicates ADR content** (violates DRY principle)
- ❌ **High drift risk** (ADRs updated but constraints doc not synced)
- ❌ **Loses context** (rationale stays in ADRs, constraints doc shows only rules)
- ❌ **Large file** (50+ constraints across categories)
- ❌ **Maintenance burden** (must update ADR AND constraints doc for every change)

**Verdict**: NOT RECOMMENDED due to DRY violation and drift risk.

### Option 2: Index-Style Reference (RECOMMENDED)

**Structure**: Create `.agents/governance/PROJECT-CONSTRAINTS.md` as **index** pointing to authoritative sources.

**Content format**:

```markdown
# Project Constraints

Quick reference of MUST/SHOULD/MAY constraints. See linked documents for full rationale.

## MUST Constraints (Blocking)

### Language: PowerShell Only
- **Rule**: All scripts MUST be PowerShell (.ps1, .psm1). NO bash or Python.
- **Source**: [ADR-005](../architecture/ADR-005-powershell-only-scripting.md)
- **Verification**: Code review, skill check
- **Exceptions**: None

### GitHub Operations: Use Skills, Not Raw Commands
- **Rule**: MUST use `.claude/skills/github/` scripts. NEVER raw `gh` commands.
- **Source**: [skill-usage-mandatory.md](../../.serena/memories/skill-usage-mandatory.md)
- **Verification**: Pre-implementation skill check (Check-SkillExists.ps1)
- **Exceptions**: None

## SHOULD Constraints (Strong Recommendations)

### Commit Discipline: Atomic Commits
- **Rule**: One logical change per commit. Max 5 files OR single topic in subject.
- **Source**: [task-completion-checklist.md](../../.serena/memories/task-completion-checklist.md)
- **Verification**: commit-msg hook, code review
- **Exceptions**: Requires justification in commit body
```

**Pros**:
- ✅ **DRY compliant**: Points to authoritative source, doesn't duplicate
- ✅ **Low drift risk**: Rules derived from sources, context stays in source
- ✅ **Scannable**: Quick reference for agents during session start
- ✅ **Tiered**: Clear MUST/SHOULD/MAY hierarchy
- ✅ **Maintainable**: Update source → re-extract rule summary
- ✅ **Verifiable**: Can add to SESSION-PROTOCOL Phase 1.5 gate

**Cons**:
- ⚠️ **Extraction overhead**: Must manually sync when ADRs change
- ⚠️ **Two-hop lookup**: Agent reads constraint → clicks through to source for context
- ⚠️ **Initial effort**: Must extract and categorize all constraints

**Mitigation for extraction overhead**: Quarterly review process (align with agent consolidation review).

**Verdict**: RECOMMENDED. Balances consolidation benefits with DRY compliance.

### Option 3: Enhanced CONTRIBUTING.md

**Structure**: Extend repository root `CONTRIBUTING.md` with constraints section (common open-source pattern).

**Pros**:
- ✅ Familiar location (GitHub displays prominently)
- ✅ Standard pattern in open-source
- ✅ Human contributors see it too

**Cons**:
- ❌ **Not agent-focused**: CONTRIBUTING.md targets human contributors
- ❌ **Root clutter**: Project uses `.agents/` for agent governance
- ❌ **Mixed audience**: Human vs agent constraints different
- ❌ **SESSION-PROTOCOL integration**: Would need to reference non-agent file

**Verdict**: NOT RECOMMENDED for agent constraints (but useful for human contributors).

### Option 4: Status Quo + Improved Discoverability

**Structure**: Keep constraints scattered but improve cross-references and discoverability.

**Approach**:
- Add "See Also" sections to each ADR pointing to related constraints
- Update SESSION-PROTOCOL.md to list all constraint sources
- Enhance HANDOFF.md with constraint reminders

**Pros**:
- ✅ No consolidation overhead
- ✅ No drift risk (single sources remain)
- ✅ DRY compliant

**Cons**:
- ❌ **Doesn't address root cause**: Session 15 violations happened despite existing docs
- ❌ **No verification gate**: Still trust-based ("agent should read X, Y, Z")
- ❌ **Cognitive overload**: Agent must read 12+ docs to understand constraints

**Verdict**: NOT RECOMMENDED. Doesn't solve the problem that prompted this analysis.

### Option 5: Hybrid (Index + Automated Checks)

**Structure**: Combine Option 2 (index-style reference) with automated validation tools.

**Components**:

1. **PROJECT-CONSTRAINTS.md** (index-style, as in Option 2)
2. **Check-SkillExists.ps1** (validates skill availability before GitHub operations)
3. **commit-msg hook** (validates atomic commit rule)
4. **SESSION-PROTOCOL.md Phase 1.5** (BLOCKING gate requiring constraint review)

**Phase 1.5 gate requirements**:

```markdown
### Phase 1.5: Constraint Validation (BLOCKING)

1. Agent MUST read `.agents/governance/PROJECT-CONSTRAINTS.md`
2. Agent MUST run `Check-SkillExists.ps1 -Operation pr -Action comment` (example)
   before ANY GitHub operation
3. Agent MUST list `.claude/skills/github/scripts/` to verify skill structure

**Verification**:
- File contents appear in session context
- Tool outputs present in session transcript
- Agent references constraints when making decisions
```

**Pros**:
- ✅ **Strongest enforcement**: Combines documentation + verification + automation
- ✅ **Addresses root cause**: Creates blocking gates, not just documentation
- ✅ **DRY compliant**: Index points to sources
- ✅ **Measurable**: Tool outputs provide evidence of compliance
- ✅ **Graduated approach**: MUST constraints get gates, SHOULD get review

**Cons**:
- ⚠️ **Highest initial effort**: Must create index + scripts + protocol updates
- ⚠️ **Most invasive**: Adds Phase 1.5 to every session start
- ⚠️ **Maintenance burden**: More components to maintain

**Mitigation**: High ROI justifies effort. Session 15 retrospective estimated 10x ROI for constraints doc, 8x for Check-SkillExists.ps1.

**Verdict**: RECOMMENDED IF resources allow. Most comprehensive solution.

## Risk Analysis

### Risk 1: Documentation Drift

**Description**: PROJECT-CONSTRAINTS.md becomes stale as ADRs/memories updated but index not synced.

**Likelihood**: MEDIUM (depends on maintenance discipline)

**Impact**: HIGH (defeats purpose of consolidation)

**Mitigation**:
- Make PROJECT-CONSTRAINTS.md part of ADR acceptance criteria ("Update constraints index")
- Quarterly consistency review (align with agent consolidation review)
- Automated link validation (validate all Source: links point to existing files)
- Session end protocol: "If you modified ADR, update constraints index"

### Risk 2: Over-Engineering

**Description**: Creating elaborate infrastructure when simpler solution exists.

**Likelihood**: LOW (Session 15 evidence shows simple documentation insufficient)

**Impact**: MEDIUM (wasted effort)

**Mitigation**:
- Start with Option 2 (index-style) as MVP
- Add automation (Option 5) incrementally based on violation data
- Measure violation rate before/after to validate effectiveness

### Risk 3: Agent Ignores New File

**Description**: Agents don't read PROJECT-CONSTRAINTS.md despite creation.

**Likelihood**: HIGH if no gate added, LOW if Phase 1.5 gate enforced

**Impact**: HIGH (no benefit from consolidation)

**Mitigation**:
- MUST add Phase 1.5 gate to SESSION-PROTOCOL.md (verification-based enforcement)
- Track compliance: Session logs must show "Read PROJECT-CONSTRAINTS.md" completion
- First 5 sessions: Manually verify gate enforcement

### Risk 4: Constraint Proliferation

**Description**: PROJECT-CONSTRAINTS.md grows to 100+ rules, becomes overwhelming.

**Likelihood**: MEDIUM (project is mature, already has 50+ constraints)

**Impact**: MEDIUM (reduces effectiveness, cognitive overload)

**Mitigation**:
- Strict tiering: Only MUST and SHOULD in main doc, MAY in appendix
- Categorization: Group by phase (pre-work, implementation, pre-commit)
- Annual pruning: Remove constraints that haven't been violated in 12 months
- Focus: Core constraints only, detailed rationale stays in ADRs

### Risk 5: False Sense of Security

**Description**: Team believes consolidation solved problem, but violations continue.

**Likelihood**: HIGH if Option 2 alone, LOW if Option 5 (with automation)

**Impact**: HIGH (problem persists, improvement stalls)

**Mitigation**:
- Metrics: Track violation rate per session (baseline from Session 15: 5+ violations)
- Success criteria: <1 violation per session after 10 sessions
- Retrospective review: Monthly analysis of violation trends
- Continuous improvement: Add gates for frequently violated constraints

## Recommendations

### Primary Recommendation: Implement Option 5 (Hybrid Approach)

**Rationale**: Session 15 evidence shows documentation alone insufficient. Verification-based gates required.

**Implementation plan**:

#### Phase A: Create Index (Week 1)

1. Create `.agents/governance/PROJECT-CONSTRAINTS.md` using index-style format (Option 2)
2. Extract constraints from:
   - ADR-005, ADR-006
   - `.serena/memories/skill-usage-mandatory.md`
   - `.serena/memories/user-preference-no-bash-python.md`
   - `.serena/memories/task-completion-checklist.md`
3. Categorize as MUST/SHOULD/MAY
4. Link to authoritative sources (ADRs, memories)

**Effort**: 2-3 hours

#### Phase B: Add Verification Gate (Week 1)

1. Update `.agents/SESSION-PROTOCOL.md` with Phase 1.5:
   - MUST read PROJECT-CONSTRAINTS.md
   - Verification: File contents appear in context
2. Update session log template with Phase 1.5 checklist
3. Update CLAUDE.md to reference new phase

**Effort**: 1 hour

#### Phase C: Implement Automation (Week 2)

1. Create `Check-SkillExists.ps1`:
   - Input: Operation type (pr, issue, reaction), Action (create, comment, label)
   - Output: Boolean + skill script path if exists
   - Tests: Pester tests for all skill categories
2. Create commit-msg hook:
   - Count staged files
   - Parse subject for multiple topics
   - Reject if >5 files AND >1 topic
   - Tests: Test against Session 15's 16-file commit
3. Update SESSION-PROTOCOL Phase 1.5 to require Check-SkillExists call

**Effort**: 4-5 hours

#### Phase D: Validate and Iterate (Week 3-4)

1. Run 5 sessions with new protocol
2. Measure violation rate per session
3. Collect feedback on gate effectiveness
4. Adjust based on data

**Success criteria**:
- <1 constraint violation per session (vs 5+ in Session 15)
- 100% gate compliance (all sessions complete Phase 1.5)
- No documentation drift detected in quarterly review

### Alternative Recommendation: Start with Option 2, Add Gates Incrementally

**If resources constrained**:

1. **Week 1**: Implement Option 2 (index-style doc) only
2. **Week 2**: Add Phase 1.5 file read gate
3. **Week 3**: Measure violation rate
4. **Week 4+**: Add automation (Check-SkillExists, commit-msg hook) only if violations persist

**Rationale**: Validates consolidation value before investing in automation.

## Open Questions

1. **Constraint granularity**: Should PROJECT-CONSTRAINTS.md include agent-specific constraints (e.g., "analyst agent MUST search memory before analysis")? Or only project-wide constraints?

   **Recommendation**: Project-wide only. Agent-specific constraints stay in agent definitions.

2. **Enforcement responsibility**: Should gates be enforced by agent (self-verification) or tooling (automated checks)?

   **Recommendation**: Hybrid. MUST constraints get automated checks where feasible, SHOULD get agent self-verification.

3. **Quarterly review process**: Who owns maintaining PROJECT-CONSTRAINTS.md? User? Orchestrator? Retrospective agent?

   **Recommendation**: Add to retrospective agent's quarterly review workflow (align with agent consolidation review).

4. **Exception handling**: How should agents request exceptions to MUST constraints?

   **Recommendation**: Document in commit message or session log with explicit justification. Example: "Violating PowerShell-only (ADR-005) because external tool requires bash. Approved by user in Session NN."

5. **Migration path**: Should existing violations be grandfathered (e.g., existing bash scripts) or refactored?

   **Recommendation**: Grandfather existing code. New code must comply. Add "Existing Violations" section to constraints doc listing known exceptions.

## Proposed Structure for PROJECT-CONSTRAINTS.md

```markdown
# Project Constraints

**Purpose**: Quick reference of mandatory (MUST), recommended (SHOULD), and optional (MAY) constraints for this repository.

**Authority**: This is an INDEX pointing to authoritative sources (ADRs, memories, protocols). When in doubt, consult the linked source.

**Last Updated**: YYYY-MM-DD
**Review Cadence**: Quarterly (align with retrospective agent review)

---

## How to Use This Document

1. **Session start**: Read this document as part of SESSION-PROTOCOL Phase 1.5
2. **Pre-implementation**: Verify your approach complies with MUST constraints
3. **Pre-commit**: Check commit discipline constraints
4. **When in doubt**: Click through to Source document for full context and rationale

---

## MUST Constraints (Blocking - Non-Negotiable)

### 1. Session Initialization

**Constraint**: MUST initialize Serena before any other action.

**Details**:
- Call `mcp__serena__activate_project` with project path
- Call `mcp__serena__initial_instructions`
- Verification: Tool outputs in session transcript

**Source**: [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md#phase-1-serena-initialization)
**Enforcement**: BLOCKING gate (Phase 1)
**Exceptions**: None

### 2. Language: PowerShell Only

**Constraint**: All scripts MUST be PowerShell (.ps1, .psm1). NO bash (.sh) or Python (.py).

**Details**:
- Use `shell: pwsh` in GitHub Actions workflows
- All modules: .psm1 format
- All scripts: .ps1 format

**Source**: [ADR-005-powershell-only-scripting.md](../architecture/ADR-005-powershell-only-scripting.md)
**Rationale**: Consistency, testing (Pester), cross-platform PowerShell Core
**Enforcement**: Code review, pre-commit check
**Exceptions**: None

### 3. GitHub Operations: Use Skills, Not Raw Commands

**Constraint**: MUST use `.claude/skills/github/` scripts. NEVER use raw `gh` commands directly.

**Details**:
- Before any GitHub operation, check if skill exists
- Use `Check-SkillExists.ps1` to validate availability
- If skill missing, ADD to skill (don't write inline)

**Source**: [skill-usage-mandatory.md](../../.serena/memories/skill-usage-mandatory.md)
**Rationale**: Tested implementations, error handling, DRY principle
**Enforcement**: Phase 1.5 gate (Check-SkillExists.ps1)
**Exceptions**: None

### 4. Context Retrieval

**Constraint**: MUST read `.agents/HANDOFF.md` before starting work.

**Details**:
- Verification: Content appears in session context
- Reference prior decisions from HANDOFF.md
- Do not repeat completed work

**Source**: [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md#phase-2-context-retrieval)
**Enforcement**: BLOCKING gate (Phase 2)
**Exceptions**: None

### 5. Session Logging

**Constraint**: MUST create session log early in session at `.agents/sessions/YYYY-MM-DD-session-NN.json`.

**Details**:
- Create within first 5 tool calls
- Include Protocol Compliance section
- Update at session end with outcomes

**Source**: [SESSION-PROTOCOL.md](../SESSION-PROTOCOL.md#phase-3-session-log-creation)
**Enforcement**: Session template requirement
**Exceptions**: None

---

## SHOULD Constraints (Strong Recommendations)

### 1. Workflow Architecture: Thin Workflows, Testable Modules

**Constraint**: Workflows SHOULD be <100 lines, orchestration only. Logic SHOULD be in PowerShell modules.

**Details**:
- Extract business logic to .psm1 modules
- Create Pester tests for modules (80%+ coverage)
- Workflows call modules, don't duplicate logic

**Source**: [ADR-006-thin-workflows-testable-modules.md](../architecture/ADR-006-thin-workflows-testable-modules.md)
**Rationale**: Fast OODA loop (local testing), DRY, maintainability
**Enforcement**: Code review
**Exceptions**: Requires justification in PR description

### 2. Commit Discipline: Atomic Commits

**Constraint**: One logical change per commit. SHOULD be max 5 files OR single topic in subject.

**Details**:
- If >5 files, subject must describe single logical change
- Use conventional commit format: `type(scope): description`
- Reference issues: `fixes #123`

**Source**: [task-completion-checklist.md](../../.serena/memories/task-completion-checklist.md)
**Enforcement**: commit-msg hook (warning), code review
**Exceptions**: Requires justification in commit body

### 3. Naming Conventions

**Constraint**: Artifacts SHOULD follow naming patterns (EPIC-NNN, ADR-NNN, etc.).

**Details**:
- Sequential numbering with 3-digit zero-padding
- Kebab-case for file names
- See full pattern guide for details

**Source**: [naming-conventions.md](naming-conventions.md)
**Enforcement**: Consistency validation script
**Exceptions**: None

### 4. Cross-Reference Validation

**Constraint**: Cross-references SHOULD point to existing files.

**Details**:
- Validate links at consistency checkpoints
- Use relative paths within `.agents/`
- Update references when renaming files

**Source**: [consistency-protocol.md](consistency-protocol.md)
**Enforcement**: Quarterly validation script
**Exceptions**: Forward references to planned documents (mark as TODO)

---

## MAY Constraints (Optional Guidance)

### 1. Markdown Linting

**Constraint**: Markdown MAY be auto-fixed with markdownlint.

**Details**:
- Run `npx markdownlint-cli2 --fix "**/*.md"` before commit
- Pre-commit hook auto-fixes on commit
- Generic types wrapped in backticks: `List<T>`

**Source**: [ADR-001-markdown-linting.md](../architecture/ADR-001-markdown-linting.md)
**Enforcement**: Pre-commit hook (automatic)
**Exceptions**: Inline HTML for specific cases (br, kbd, sup, sub)

### 2. Commit Message Details

**Constraint**: Commit messages MAY include body and footer for complex changes.

**Details**:
- Subject: <50 chars, imperative mood
- Body: Detailed explanation (optional)
- Footer: Breaking changes, references (optional)

**Source**: [code-style-conventions.md](../../.serena/memories/code-style-conventions.md)
**Enforcement**: Linter (optional)
**Exceptions**: Simple changes don't require body

---

## Constraint Validation Checklist

Use this checklist during Phase 1.5 (Session Start):

- [ ] Read this document (PROJECT-CONSTRAINTS.md)
- [ ] For GitHub operations: Run `Check-SkillExists.ps1` to verify skill availability
- [ ] For new scripts: Verify PowerShell-only (no .sh or .py files)
- [ ] For workflow changes: Verify logic in modules, not YAML
- [ ] Before commit: Verify atomic commit rule (<5 files OR single topic)

---

## Existing Violations (Grandfathered)

None currently documented. Add here if legacy code violates constraints but is accepted.

---

## Maintenance

**Owner**: Retrospective agent (quarterly review)
**Update trigger**: When ADRs added/amended, new preferences documented
**Review cadence**: Quarterly (align with agent consolidation review)
**Validation**: Link checker (all Source: links valid), constraint coverage check

---

**Version**: 1.0
**Established**: 2025-12-18
**Related Issue**: Session 15 Retrospective
```

## Related Work

### Session 15 Retrospective

Full retrospective at `.agents/retrospective/2025-12-18-session-15-retrospective.md` and `.serena/memories/retrospective-2025-12-18-session-15-pr-60.md`.

**Key findings**:
- 5+ user interventions for constraint violations
- Root cause: Missing blocking gates for constraint validation
- Proposed actions: PROJECT-CONSTRAINTS.md (P0), Check-SkillExists.ps1 (P0), commit-msg hook (P1)

### SESSION-PROTOCOL.md

Canonical source for session start/end requirements. Uses RFC 2119 key words (MUST/SHOULD/MAY).

**Existing gates**:
- Phase 1: Serena initialization (BLOCKING, 100% compliance)
- Phase 2: Context retrieval (BLOCKING, high compliance)
- Phase 3: Session logging (REQUIRED, medium compliance)

**Gap**: No Phase 1.5 for project constraint validation.

### ADR-005 and ADR-006

Architecture decisions documenting PowerShell-only and thin workflows patterns.

**Status**: Accepted
**Authority**: High (canonical design decisions)
**Problem**: Agents violate despite ADR existence (Session 15 evidence)

## Sources

This analysis drew on the following research:

**Documentation Best Practices**:

- [Single Source of Truth - Atlassian](https://www.atlassian.com/work-management/knowledge-sharing/documentation/building-a-single-source-of-truth-ssot-for-your-team)
- [What is SSOT - Guru](https://www.getguru.com/reference/single-source-of-truth)
- [Technical Documentation Best Practices 2025 - DeepDocs](https://deepdocs.dev/technical-documentation-best-practices/)
- [Documentation Best Practices 2025 - Chatiant](https://www.chatiant.com/blog/documentation-best-practices)

**DRY Principle and ADRs**:

- [Architecture Decision Records - GitHub](https://github.com/joelparkerhenderson/architecture-decision-record)
- [ADR Best Practices - adr.github.io](https://adr.github.io/)
- [Creating ADRs - Ozimmer](https://ozimmer.ch/practices/2023/04/03/ADRCreation.html)
- [DRY Principle - Wikipedia](https://en.wikipedia.org/wiki/Don't_repeat_yourself)
- [ADR Maintenance - Microsoft Azure](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record)

**Documentation Drift Prevention**:

- [Configuration Drift Detection - Josys](https://www.josys.com/article/understanding-the-lifecycle-of-configuration-drift-detection-remediation-and-prevention)
- [API Drift Prevention - Wiz](https://www.wiz.io/academy/api-drift)
- [Configuration Drift Explained - Wiz](https://www.wiz.io/academy/configuration-drift)
- [Cloud Governance Best Practices - ControlMonkey](https://controlmonkey.io/blog/cloud-governance-best-practices-devops/)

**GitHub Contribution Guidelines**:

- [GitHub Repo Guidelines - Creative Commons](https://opensource.creativecommons.org/contributing-code/github-repo-guidelines/)
- [Setting Guidelines for Contributors - GitHub Docs](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors)
- [Open Source Checklist - GitHub Gist](https://gist.github.com/PurpleBooth/6f1ba788bf70fb501439)
- [Git Strict Flow Guidelines - GitHub Gist](https://gist.github.com/rsp/057481db4dbd999bb7077f211f53f212)
- [GitHub Rulesets Best Practices - GitHub Well-Architected](https://wellarchitected.github.com/library/governance/recommendations/managing-repositories-at-scale/rulesets-best-practices/)

---

**Analysis prepared by**: Analyst Agent
**Date**: 2025-12-18
**Session**: 19
**Estimated reading time**: 25 minutes
