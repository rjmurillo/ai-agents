# Multi-Agent Workflow Skills

Category: Agent Coordination and Workflow Patterns

## Skill-Workflow-001: Full Pipeline for Large Changes

- **Statement**: Use full agent pipeline (analyst -> architect -> planner -> critic -> implementer -> qa) for changes touching 10+ files
- **Context**: Large-scale codebase modifications
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - markdown linting used full pipeline for 59-file change, zero rollbacks needed
- **Impact**: Comprehensive coverage prevents rework
- **Tags**: helpful, coordination

**Pipeline Sequence**:

1. **Analyst**: Research and violation discovery (1363 violations found)
2. **Architect**: Technical decision documentation (ADR-001)
3. **Planner**: Detailed implementation plan (6 milestones)
4. **Critic**: Plan validation (3 minor issues found)
5. **Implementer**: Execute fixes (5 atomic commits)
6. **QA**: Verify results (99.8% success rate)
7. **Retrospective**: Extract learnings (this document)

---

## Skill-Workflow-002: Artifact Chain Documentation

- **Statement**: Each agent produces artifacts that become inputs for the next agent in the chain
- **Context**: Agent handoff protocol
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - analysis -> ADR -> plan -> critique -> commits -> QA report -> retrospective
- **Impact**: Creates audit trail and enables handoff verification
- **Tags**: helpful, traceability

**Artifact Chain**:

```text
.agents/analysis/    -> Analyst findings
.agents/architecture/ -> ADR documents
.agents/planning/    -> Implementation plans
.agents/critique/    -> Plan validations
[commits]            -> Implementation evidence
.agents/qa/          -> Verification reports
.agents/retrospective/ -> Learning extraction
.agents/skills/      -> Extracted skills
```

---

## Skill-Workflow-003: Pre-Implementation Validation

- **Statement**: Always run critic validation on plans before implementation begins
- **Context**: Risk reduction for complex changes
- **Atomicity**: 92%
- **Evidence**: 2025-12-13 - critic review caught 3 minor issues before implementation
- **Impact**: Prevents costly mid-implementation corrections
- **Tags**: helpful, quality-gate

**Validation Criteria**:

- Completeness: All requirements addressed
- Feasibility: Technical approach is sound
- Scope: Not too broad, not too narrow
- Timeline: Realistic estimates
- Risks: Identified and mitigated

---

## Skill-Workflow-004: Atomic Commit Strategy

- **Statement**: Create atomic commits per logical unit (config, then each directory batch) for complex changes
- **Context**: Multi-directory modifications
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - 5 atomic commits enabled targeted review and potential rollback
- **Impact**: Enables selective rollback without reverting unrelated changes
- **Tags**: helpful, git-workflow

**Commit Sequence**:

1. `docs: add configuration and requirements` (foundational)
2. `fix(scope1): resolve violations in first scope`
3. `fix(scope2): resolve violations in second scope`
4. `fix(scope3): resolve violations in third scope`
5. `fix(docs): resolve violations in documentation`

---

## Skill-Workflow-005: Retrospective Extraction Timing

- **Statement**: Run retrospective immediately after QA completes while context is fresh
- **Context**: Learning extraction from completed work
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - retrospective captured specific details (800+ auto-fixes, 3 false positives)
- **Impact**: Captures tactical details that would be lost if delayed
- **Tags**: helpful, learning

**Extraction Focus**:

1. What strategies contributed to success
2. What caused problems or delays
3. What nearly failed but recovered
4. What patterns are reusable

---

## Skill-Workflow-006: Batch Verification Pattern

- **Statement**: Verify each batch of changes before proceeding to the next batch
- **Context**: Incremental validation during implementation
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - linting verified after each directory before moving to next
- **Impact**: Catches issues early, prevents error propagation
- **Tags**: helpful, quality

**Pattern**:

```bash
# After each batch
npx markdownlint-cli2 "directory/**/*.md"
# If pass, commit and proceed
# If fail, fix before continuing
```

---

## Skill-Workflow-007: Agent-Appropriate Scope Selection

- **Statement**: Match agent to task scope - implementer for direct coding, full pipeline for systemic changes
- **Context**: Agent selection decisions
- **Atomicity**: 85%
- **Evidence**: 2025-12-13 - 59-file change used full pipeline; single-file fix would use implementer only
- **Impact**: Avoids overhead for small tasks, ensures coverage for large ones
- **Tags**: helpful, efficiency

**Selection Criteria**:

| Scope | Agent Path |
|-------|------------|
| 1-2 files, clear fix | implementer -> qa |
| 3-10 files, defined change | planner -> implementer -> qa |
| 10+ files or new standards | full pipeline |
| Strategic decision | independent-thinker -> high-level-advisor |

---

## Skill-Workflow-008: Configuration-First Approach

- **Statement**: Create configuration and documentation before implementation for consistency
- **Context**: New standards or tool introduction
- **Atomicity**: 90%
- **Evidence**: 2025-12-13 - config created first, ensured all fixes aligned with final standards
- **Impact**: Prevents inconsistent fixes that need rework
- **Tags**: helpful, sequence

**Order**:

1. Create tool configuration (`.markdownlint-cli2.yaml`)
2. Create requirements documentation (`docs/markdown-linting.md`)
3. Verify configuration works
4. Begin implementation

---

## Skill-Workflow-009: Known Exception Documentation

- **Statement**: Document known exceptions/false-positives explicitly with file locations
- **Context**: Unavoidable rule violations
- **Atomicity**: 92%
- **Evidence**: 2025-12-13 - 3 false positives documented in config comments and QA report
- **Impact**: Prevents future confusion and wasted investigation
- **Tags**: helpful, maintenance

**Documentation Pattern**:

```yaml
# In configuration:
# Note: 3 known false positives in nested template files:
# - retrospective.md:189 - closing fence of outer markdown template
# - roadmap.md:117 - closing fence of outer markdown template
# - copilot-cli/roadmap.agent.md:107 - same issue
```

---

## Skill-Workflow-010: Parallel Platform Synchronization

- **Statement**: Apply identical changes to parallel platform implementations (Claude, VS Code, Copilot CLI) together
- **Context**: Multi-platform agent repositories
- **Atomicity**: 88%
- **Evidence**: 2025-12-13 - all three platforms fixed with equivalent changes
- **Impact**: Maintains platform parity, prevents drift
- **Tags**: helpful, consistency

**Synchronization Pattern**:

1. Fix reference implementation (Claude)
2. Apply same patterns to VS Code agents
3. Apply same patterns to Copilot CLI agents
4. Verify all three pass validation
5. Commit each platform separately for review

---

## Skill-Workflow-011: HANDOFF.md Session History Merge

- **Statement**: Merge session histories chronologically when resolving HANDOFF.md conflicts, preserving parallel work streams
- **Context**: Merging feature branches with parallel session history
- **Atomicity**: 92%
- **Evidence**: 2025-12-21 PR #201 - initial conflict resolution discarded feature branch sessions 57-55, corrected by merging and sorting chronologically
- **Impact**: Preserves complete project history across parallel development streams
- **Tags**: helpful, merge-resolution

**Merge Protocol**:

1. **Identify Conflict**: Session History table has conflicts from parallel work
2. **Combine Sessions**: Include ALL sessions from both main and feature branches
3. **Sort Chronologically**: Descending by session number (most recent first)
4. **Preserve Parallel Work**: Sessions with same number but different PRs (e.g., Session 57 for #222 AND Session 57-PR201 for #201) are BOTH kept
5. **Expand Scope**: If needed, expand "Last 5" to "Last 10" to capture full parallel context

**Anti-Pattern**:

Discarding feature branch session history during merge conflict resolution loses important project context. HANDOFF.md tracks project-wide state - parallel work streams must be merged, not replaced.

**Example**:

```markdown
# WRONG: Taking only main's sessions
| Session | Date | Summary | PR/Issue |
|---------|------|---------|----------|
| Session 61 | 2025-12-21 | ... | #223 |
| Session 60 | 2025-12-20 | ... | #53 |
| Session 59 | 2025-12-19 | ... | #222 |
# Feature branch sessions 57-55 for PR #201 LOST

# CORRECT: Merged and sorted chronologically
| Session | Date | Summary | PR/Issue |
|---------|------|---------|----------|
| Session 61 | 2025-12-21 | ... | #223 |
| Session 60 | 2025-12-20 | ... | #53 |
| Session 59 | 2025-12-19 | ... | #222 |
| Session 57-PR201 | 2025-12-18 | ... | #201 |
| Session 57 | 2025-12-18 | ... | #222 |
| Session 56-PR201 | 2025-12-17 | ... | #201 |
| Session 56 | 2025-12-17 | ... | #222 |
| Session 55-PR201 | 2025-12-16 | ... | #201 |
# Both streams preserved, sorted chronologically
```

---

## Skill-Workflow-012: Branch Handoffs for Feature Branch Validator Compliance

- **Statement**: On feature branches, create branch handoffs at `.agents/handoffs/{branch}/{session}.md` to satisfy validator without updating HANDOFF.md
- **Context**: Session End validation on feature branches where HANDOFF.md is read-only (ADR-014)
- **Atomicity**: 95%
- **Evidence**: Session 92-93 - Validator requires HANDOFF.md reference but pre-commit hook blocks HANDOFF.md changes on feature branches
- **Impact**: Resolves circular dependency between validator and pre-commit enforcement
- **Tags**: helpful, protocol-compliance

**Protocol Conflict**:

Three authoritative sources contradict:

1. **HANDOFF.md**: Read-only on feature branches (ADR-014)
2. **Validator** (`Validate-SessionEnd.ps1` line 255): Requires HANDOFF.md to reference session log (E_HANDOFF_LINK_MISSING)
3. **Pre-commit Hook**: Blocks HANDOFF.md changes on feature branches

**Resolution**:

| Branch Type | Action | Rationale |
|-------------|--------|-----------|
| **Feature Branch** | Create branch handoff at `.agents/handoffs/{branch}/{session}.md` | Satisfies documentation requirement without modifying HANDOFF.md |
| **Main Branch** | Update HANDOFF.md "Last 5 Sessions" table | Canonical dashboard maintained on main only |

**Workaround Pattern**:

```bash
# On feature branch (e.g., feature/issue-123)
# Session log created as usual
.agents/sessions/2025-12-24-session-92.md

# Create branch handoff instead of updating HANDOFF.md
.agents/handoffs/feature/issue-123/2025-12-24-session-92.md

# Content: Reference to session log + key decisions
# Session End validator satisfied by session log existence
# Pre-commit hook does NOT block branch handoffs
```

**Validator Gap**:

The validator script (`Validate-SessionEnd.ps1`) was not updated after ADR-014. Future fix tracked in GitHub issue (to be filed).

**References**:

- ADR-014: Distributed Handoff Architecture (reason for HANDOFF.md read-only)
- Pre-commit hook output: "ERROR: BLOCKED: HANDOFF.md is read-only on feature branches"
- SESSION-PROTOCOL.md v1.4: Should clarify HANDOFF.md update policy

---

## Anti-Patterns

### Anti-Workflow-001: Skipping Critic Validation

- **Statement**: Never skip critic review for changes affecting more than 5 files
- **Atomicity**: 90%
- **Tags**: harmful, risk

**Prevention**: Critic review is a required gate in the pipeline for systemic changes.

### Anti-Workflow-002: Monolithic Commits

- **Statement**: Avoid single commits containing all changes across multiple directories
- **Atomicity**: 85%
- **Tags**: harmful, git-workflow

**Prevention**: Commit atomically by logical unit (config, then each directory).

### Anti-Workflow-003: Delayed Retrospective

- **Statement**: Avoid running retrospective days after completion when context is lost
- **Atomicity**: 85%
- **Tags**: harmful, learning

**Prevention**: Schedule retrospective immediately after QA verification.

---

## Metrics

| Metric | Value |
|--------|-------|
| Pipeline Stages Used | 7 |
| Artifacts Generated | 7 |
| Atomic Commits | 5 |
| Rollbacks Required | 0 |
| Known Exceptions | 3 |
