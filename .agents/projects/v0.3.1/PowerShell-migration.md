# PowerShell-to-Python Migration Plan

**Version**: v0.3.1
**Authority**: ADR-042 (Accepted 2026-01-17)
**Supersedes**: ADR-005 (PowerShell-Only Scripting, status: Superseded)
**Date**: 2026-02-07

## Executive Summary

ADR-042 established Python as the primary scripting language, superseding ADR-005.
This plan provides a prioritized, phased migration of PowerShell scripts to Python with pytest.

After dead code removal, the migration scope is approximately **~136 non-test scripts**,
**14 modules**, and **~107 Pester test files**. 21 workflows reference PowerShell.

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deprecation period | None (delete immediately) | Internal tooling project, single consumer (AI agents) |
| Dead code | Delete before migrating | Reduces scope by ~3 scripts and associated tests |
| High-traffic skills | Promote to Phase 1 | Post-IssueComment.ps1 referenced by 7 workflows |
| Validate-SessionJson.ps1 | Include in Phase 0 | Python version exists with pytest coverage |

### Current State

| Category | .ps1 (non-test) | .psm1 | .Tests.ps1 | .py (already migrated) |
|----------|-----------------|-------|------------|------------------------|
| `scripts/` | 24 | 2 | 8 | 7 |
| `.claude/skills/github/` | 23 | 1 | 10 | 0 |
| `.claude/skills/memory/` | 4 | 3 | 1 | 0 |
| `.claude/skills/` (other) | 12 | 0 | 2 | ~20 |
| `.claude/hooks/` | 13 | 1 | 0 | 1 |
| `.github/scripts/` | 2 | 3 | 3 | 0 |
| `build/` | 6 | 1 | 4 | 0 |
| `.codeql/scripts/` | 6 | 0 | 0 | 0 |
| Other | 8 | 3 | 5 | 0 |
| **Total** | **~142** | **14** | **~110** | **~28** |

### Already Migrated (Dual Existence)

These scripts have both `.ps1` and `.py` versions. Remove the PowerShell version
after verifying callers point to Python:

| PowerShell | Python | pytest |
|-----------|--------|--------|
| `scripts/Detect-SkillViolation.ps1` | `scripts/detect_skill_violation.py` | `tests/test_detect_skill_violation.py` |
| `scripts/Check-SkillExists.ps1` | `scripts/check_skill_exists.py` | `tests/test_check_skill_exists.py` |
| `scripts/Validate-SessionJson.ps1` | `scripts/validate_session_json.py` | `tests/test_validate_session_json.py` |
| `.claude/skills/security-detection/detect-infrastructure.ps1` | `detect_infrastructure.py` | (in skill) |
| `.claude/skills/metrics/collect-metrics.ps1` | `collect_metrics.py` | (in skill) |
| `.claude/skills/fix-markdown-fences/fix_fences.ps1` | `fix_fences.py` | (in skill) |

---

## Prioritization Criteria

Scripts are prioritized by four factors:

1. **Modification frequency**: High-churn files benefit most from migration
2. **Workflow coupling**: Scripts called by CI workflows require coordinated updates
3. **Size/complexity**: Larger files yield more value
4. **Dependency depth**: Shared modules (.psm1) must migrate before their consumers

### Priority Tiers

| Tier | Criteria | Timeline |
|------|----------|----------|
| **P0 - Cleanup** | Delete dead code + remove already-migrated duplicates | Immediate |
| **P1 - High Traffic** | Shared modules + high-churn scripts + workflow-coupled skills | Months 1-3 |
| **P2 - CI Infrastructure** | Build system + validation scripts + workflow updates | Months 3-6 |
| **P3 - Skills** | Remaining skills (memory, session, merge-resolver, etc.) | Months 6-9 |
| **P4 - Long Tail** | CodeQL, traceability, hooks, remaining utilities | Months 9-12+ |

---

## Phase 0: Cleanup (Immediate)

### 0.1 Delete dead code

These scripts have zero active references (confirmed via codebase audit):

- [ ] `scripts/Fix-PR964-Validation.ps1` (one-off PR fix, never called)
- [ ] `.agents/benchmarks/test-parent-shell-impact.ps1` (abandoned benchmark)
- [ ] `.agents/retrospective/analyze-compliance.ps1` (one-off 2025-12-20 analysis)

### 0.2 Remove already-migrated PowerShell duplicates

For each pair, verify the Python version is the active caller, then delete the `.ps1`:

- [ ] Verify `scripts/detect_skill_violation.py` is wired up, delete `Detect-SkillViolation.ps1` + `Detect-SkillViolation.Tests.ps1`
- [ ] Verify `scripts/check_skill_exists.py` is wired up, delete `Check-SkillExists.ps1` + `Check-SkillExists.Tests.ps1`
- [ ] Verify `.claude/skills/security-detection/detect_infrastructure.py` is wired up, delete `detect-infrastructure.ps1`
- [ ] Verify `.claude/skills/metrics/collect_metrics.py` is wired up, delete `collect-metrics.ps1`
- [ ] Verify `.claude/skills/fix-markdown-fences/fix_fences.py` is wired up, delete `fix_fences.ps1`

### 0.3 Validate-SessionJson.ps1

This script is referenced in SESSION-PROTOCOL.md, CLAUDE.md, CRITICAL-CONTEXT.md,
and 3 workflows (`ai-session-protocol.yml` primarily). The Python equivalent
`validate_session_json.py` exists with `test_validate_session_json.py`.

- [ ] Compare output format: both must produce identical JSON validation results
- [ ] Update `ai-session-protocol.yml` to call `python scripts/validate_session_json.py`
- [ ] Update SESSION-PROTOCOL.md, CLAUDE.md, CRITICAL-CONTEXT.md references
- [ ] Delete `scripts/Validate-SessionJson.ps1` + `tests/Validate-SessionJson.Tests.ps1`

**Scope reduction**: Phase 0 removes ~9 PowerShell files and ~6 Pester test files.

---

## Phase 1: High-Traffic Scripts + Workflow-Coupled Skills (Months 1-3)

### 1.1 Shared Modules (migrate first, blocks consumers)

| Module | Lines | Consumers | Notes |
|--------|-------|-----------|-------|
| `.github/scripts/AIReviewCommon.psm1` | 1312 | AI quality gate, issue triage, spec validation | 9 modifications since Dec |
| `.claude/skills/github/modules/GitHubCore.psm1` | 1394 | All 23 GitHub skill scripts | Largest module, critical path |
| `.github/scripts/PRMaintenanceModule.psm1` | ~200 | pr-maintenance workflow | |
| `.github/scripts/TestResultHelpers.psm1` | ~150 | Test workflows | |
| `.claude/hooks/Common/HookUtilities.psm1` | ~100 | All hook scripts | |

**Migration pattern**:

1. Create Python module (e.g., `scripts/lib/github_core.py`)
2. Write pytest equivalents for existing Pester tests
3. Update consumers to import the Python module
4. Delete the `.psm1` immediately after all consumers are switched

### 1.2 High-Churn Scripts

| Script | Modifications (since Dec) | Lines | Workflows |
|--------|--------------------------|-------|-----------|
| `scripts/Invoke-PRMaintenance.ps1` | 12 | 849 | pr-maintenance |
| `.claude/skills/github/scripts/pr/Detect-CopilotFollowUpPR.ps1` | 10 | ~300 | (hook) |
| `build/Generate-Agents.Common.psm1` | 6 | 589 | validate-generated-agents |

### 1.3 Workflow-Coupled GitHub Skills (promoted from Phase 3)

These GitHub skills are called by multiple workflows and have high modification counts.
They depend on GitHubCore.psm1 (1.1), so migrate them immediately after the module.

| Script | Modifications | Lines | Workflows |
|--------|--------------|-------|-----------|
| `.claude/skills/github/scripts/issue/Post-IssueComment.ps1` | 8 | ~200 | **7 workflows** |
| `.claude/skills/github/scripts/issue/Invoke-CopilotAssignment.ps1` | 6 | 736 | 3 workflows |
| `.claude/skills/github/scripts/milestone/Set-ItemMilestone.ps1` | N/A | ~200 | 2 workflows |
| `.claude/skills/github/scripts/pr/Invoke-PRCommentProcessing.ps1` | N/A | ~300 | 1 workflow |
| `.claude/skills/github/scripts/pr/Get-PRReviewComments.ps1` | 7 | 835 | (skill) |

---

## Phase 2: CI Infrastructure (Months 3-6)

### 2.1 Build System

| Script | Lines | Workflow |
|--------|-------|----------|
| `build/Generate-Agents.ps1` | ~200 | validate-generated-agents |
| `build/Generate-Skills.ps1` | ~200 | (build) |
| `build/scripts/Detect-AgentDrift.ps1` | ~300 | drift-detection |
| `build/scripts/Validate-PathNormalization.ps1` | ~200 | validate-paths |
| `build/scripts/Validate-PlanningArtifacts.ps1` | ~200 | validate-planning-artifacts |
| `build/scripts/Invoke-PesterTests.ps1` | 528 | pester-tests |

`Invoke-PesterTests.ps1` runs Pester. As scripts migrate to Python, this is
gradually replaced by the existing `pytest.yml` workflow. Remove the Pester
workflow once no Pester tests remain.

### 2.2 Validation Scripts (CI-coupled)

| Script | Lines | Workflow |
|--------|-------|----------|
| `scripts/Validate-PRDescription.ps1` | ~300 | pr-validation |
| `scripts/Validate-ActionSHAPinning.ps1` | ~200 | pr-validation |
| `scripts/Validate-Consistency.ps1` | 684 | (manual) |
| `scripts/Validate-PrePR.ps1` | 540 | (manual) |
| `scripts/Validate-TokenBudget.ps1` | ~200 | (manual) |
| `scripts/Validate-SkillFrontmatter.ps1` | 569 | slash-command-quality |
| `scripts/Validate-Traceability.ps1` | 599 | (manual) |
| `scripts/Validate-MemoryIndex.ps1` | 922 | memory-validation |

### 2.3 GitHub Actions Scripts

| Script | Lines | Workflow |
|--------|-------|----------|
| `.github/scripts/Test-RateLimitForWorkflow.ps1` | ~100 | pr-maintenance |
| `.github/scripts/Measure-WorkflowCoalescing.ps1` | 571 | workflow-coalescing-metrics |
| `scripts/Update-ReviewerSignalStats.ps1` | 709 | update-reviewer-stats |

### 2.4 Workflow Updates

Each migrated script requires a corresponding workflow update.
Change `pwsh` to `python` in the `run:` block and update the script path.

| Workflow | Scripts Referenced | Effort |
|----------|--------------------|--------|
| `ai-pr-quality-gate.yml` | Post-IssueComment.ps1 | Low (done in P1) |
| `ai-session-protocol.yml` | Validate-SessionJson.ps1, Convert-SessionToJson.ps1 | Low (done in P0) |
| `drift-detection.yml` | Detect-AgentDrift.ps1 | Low |
| `milestone-tracking.yml` | Set-ItemMilestone.ps1 | Low (done in P1) |
| `pester-tests.yml` | Invoke-PesterTests.ps1 | High (gradual retirement) |
| `powershell-lint.yml` | PSScriptAnalyzer | Retire (replace with ruff) |
| `pr-maintenance.yml` | Invoke-PRMaintenance.ps1, Test-RateLimitForWorkflow.ps1 | High |
| `pr-validation.yml` | Validate-PRDescription.ps1, Validate-ActionSHAPinning.ps1 | Medium |
| `slash-command-quality.yml` | Validate-SlashCommand.ps1 | Low |
| `validate-generated-agents.yml` | Generate-Agents.ps1 | Medium |
| `validate-paths.yml` | Validate-PathNormalization.ps1 | Low |
| `validate-planning-artifacts.yml` | Validate-PlanningArtifacts.ps1 | Low |
| `workflow-coalescing-metrics.yml` | Measure-WorkflowCoalescing.ps1 | Medium |

---

## Phase 3: Remaining Skills (Months 6-9)

### 3.1 GitHub Skills (remaining after Phase 1 promotions)

**Dependency**: GitHubCore.psm1 migrated in Phase 1.1.

| Directory | Remaining Scripts | Notes |
|-----------|-------------------|-------|
| `.claude/skills/github/scripts/pr/` | ~9 scripts | After P1 promotions |
| `.claude/skills/github/scripts/issue/` | ~5 scripts | After P1 promotions |
| `.claude/skills/github/scripts/reactions/` | 1 script | |
| `.claude/skills/github/scripts/utils/` | 1 script | |

### 3.2 Memory Skills

| Script | Lines | Notes |
|--------|-------|-------|
| `.claude/skills/memory/scripts/MemoryRouter.psm1` | 577 | Core routing module |
| `.claude/skills/memory/scripts/ReflexionMemory.psm1` | 996 | Largest module |
| `.claude/skills/memory/scripts/Search-Memory.ps1` | ~200 | |
| `.claude/skills/memory/scripts/Extract-SessionEpisode.ps1` | 530 | |
| `.claude/skills/memory/scripts/Measure-MemoryPerformance.ps1` | ~200 | |
| `.claude/skills/memory/scripts/Update-CausalGraph.ps1` | ~200 | |
| `.claude/skills/memory/modules/SchemaValidation.psm1` | ~200 | |

### 3.3 Other Skills

| Skill | Scripts | Notes |
|-------|---------|-------|
| `session-init` | 2 .ps1 + 2 .psm1 | New-SessionLogJson.ps1, GitHelpers.psm1 |
| `session-log-fixer` | 1 .ps1 | Get-ValidationErrors.ps1 |
| `session-migration` | 1 .ps1 | Convert-SessionToJson.ps1 |
| `session` | 1 .ps1 | Session scripts |
| `session-qa-eligibility` | 1 .ps1 | Eligibility check |
| `merge-resolver` | 1 .ps1 | Resolve-PRConflicts.ps1 |
| `steering-matcher` | 1 .ps1 | Get-ApplicableSteering.ps1 |
| `github-url-intercept` | 1 .ps1 | Test-UrlRouting.ps1 |
| `slashcommandcreator` | 2 .ps1 | Validate-SlashCommand.ps1 |
| `adr-review` | 1 .ps1 | ADR review scripts |
| `codeql-scan` | 1 .ps1 | CodeQL scan scripts |

---

## Phase 4: Long Tail (Months 9-12+)

### 4.1 CodeQL Scripts

| Script | Lines |
|--------|-------|
| `.codeql/scripts/Invoke-CodeQLScan.ps1` | 846 |
| `.codeql/scripts/Get-CodeQLDiagnostics.ps1` | 722 |
| `.codeql/scripts/Test-CodeQLConfig.ps1` | 559 |
| `.codeql/scripts/Test-CodeQLRollout.ps1` | 541 |
| `.codeql/scripts/Install-CodeQL.ps1` | ~200 |
| `.codeql/scripts/Install-CodeQLIntegration.ps1` | ~200 |

### 4.2 Traceability Scripts

| Script | Lines |
|--------|-------|
| `scripts/traceability/Resolve-OrphanedSpecs.ps1` | 698 |
| `scripts/traceability/Show-TraceabilityGraph.ps1` | 634 |
| `scripts/traceability/TraceabilityCache.psm1` | ~200 |

### 4.3 Remaining Utilities

| Script | Lines | Notes |
|--------|-------|-------|
| `scripts/Invoke-BatchPRReview.ps1` | ~300 | Batch operations |
| `scripts/New-ValidatedPR.ps1` | ~300 | PR creation |
| `scripts/Normalize-LineEndings.ps1` | ~100 | File utility |
| `scripts/Review-MemoryExportSecurity.ps1` | ~200 | Security gate (52+ references) |
| `scripts/Sync-McpConfig.ps1` | ~200 | MCP sync |
| `scripts/Split-BundledSkills.ps1` | ~200 | Skill management |
| `scripts/Invoke-SessionStartGate.ps1` | ~200 | Session gate (ADR-033) |
| `scripts/Convert-SessionToJson.ps1` | ~200 | Session conversion |
| `.serena/scripts/Import-ObservationsToForgetful.ps1` | 630 | Serena integration |
| `.claude-mem/scripts/` | 4 .ps1 | Claude-mem scripts |

### 4.4 Hook Scripts

| Hook | Scripts | Notes |
|------|---------|-------|
| `PreToolUse/` | 4 .ps1 | Branch protection guards |
| `PostToolUse/` | 2 .ps1 | Post-tool processing |
| `Stop/` | 1 .ps1 | Session validator |
| `SubagentStop/` | 1 .ps1 | QA agent validator |
| `PermissionRequest/` | 1 .ps1 | Test auto-approval |
| `SessionStart/` | 2 .ps1 | Session start hooks |
| `UserPromptSubmit/` | 1 .ps1 | Prompt hooks |

---

## Phase 5: Test Migration and Workflow Retirement

### 5.1 Pester-to-pytest Migration

Each `.Tests.ps1` maps to a `test_*.py`. Migrate tests alongside their scripts.

**Current state**:

- 110 Pester test files (`.Tests.ps1`)
- 14 pytest test files (`test_*.py`) already exist

**Pattern**: When migrating `Foo.ps1` to `foo.py`, also create `test_foo.py`.

### 5.2 CI Workflow Retirement

Once all Pester tests are migrated:

- [ ] Remove `pester-tests.yml` workflow
- [ ] Remove `powershell-lint.yml` workflow (ruff covers Python linting)
- [ ] Remove `build/scripts/Invoke-PesterTests.ps1`
- [ ] Remove `tests/TestUtilities.psm1`

---

## Migration Checklist (per script)

No deprecation period. Delete PowerShell immediately after Python passes tests.

1. [ ] Create Python equivalent at matching location (`.ps1` -> `.py`, snake_case)
2. [ ] Migrate Pester tests to pytest with equivalent coverage
3. [ ] Verify identical behavior: run both against same inputs
4. [ ] Update all callers (workflows, SKILL.md, other scripts)
5. [ ] Delete PowerShell version (`.ps1` and `.Tests.ps1`)
6. [ ] Update any CLAUDE.md / SKILL.md / SKILL-QUICK-REF.md references

---

## Naming Convention

| PowerShell | Python |
|-----------|--------|
| `Verb-Noun.ps1` | `verb_noun.py` (snake_case) |
| `Module.psm1` | `module.py` or `module/` package |
| `Noun.Tests.ps1` | `test_noun.py` |
| Inline `Import-Module` | Python `import` |

---

## Dependencies and Risks

### Blocking Dependencies

| Dependency | Impact | Mitigation |
|-----------|--------|------------|
| GitHubCore.psm1 | Blocks all 23 GitHub skill migrations | Migrate first in Phase 1.1 |
| AIReviewCommon.psm1 | Blocks AI quality gate migrations | Migrate first in Phase 1.1 |
| HookUtilities.psm1 | Blocks hook migrations | Migrate first in Phase 1.1 |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Output format differences | Medium | High | Verify output compatibility before switching callers |
| Python 3.13 bugs | Low | Medium | Pin to 3.12 via `.python-version` (already done) |
| Workflow breakage | Medium | High | Expand-contract: add Python, verify, delete PS1 |
| Test coverage regression | Medium | Medium | Require pytest coverage >= Pester before deletion |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| PowerShell files remaining | 0 by end of migration |
| pytest coverage | >= Pester coverage for each migrated script |
| CI failures during migration | 0 (expand-contract prevents breakage) |
| Pester workflow | Retired after last .Tests.ps1 removed |
| PSScriptAnalyzer workflow | Retired after last .ps1 removed |

---

## ADR Status

- **ADR-005**: Status is `Superseded` (correctly marked, no changes needed)
- **ADR-042**: Status is `Accepted` (active, governs this migration)

Both ADRs have proper cross-references. No ADR status changes are required.

---

## References

- [ADR-042: Python Migration Strategy](../../.agents/architecture/ADR-042-python-migration-strategy.md)
- [ADR-005: PowerShell-Only Scripting](../../.agents/architecture/ADR-005-powershell-only-scripting.md) (Superseded)
- [ADR-006: Thin Workflows, Testable Modules](../../.agents/architecture/ADR-006-thin-workflows-testable-modules.md) (still active)
