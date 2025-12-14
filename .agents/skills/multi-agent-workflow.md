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
