# Plan Critique: ADR-045 Framework Extraction via Plugin Marketplace

## Verdict

**NEEDS REVISION** (P0 blocking issues identified)

**Confidence**: High (85%)

## Summary

ADR-045 proposes extracting the multi-agent framework from ai-agents into awesome-ai as a 4-plugin marketplace. The decision is directionally sound and well-researched, but contains critical gaps in planning, underestimated risks in execution, and insufficient alignment validation with existing constraints.

The 65/25/10 split (framework/domain/hybrid) inventory is directionally accurate but lacks verification methodology. The 4-plugin granularity is reasonable but path abstraction strategy has unvalidated failure modes. Prerequisites are correctly sequenced but completion criteria are undefined.

## Strengths

- **Strong research foundation**: Plugin marketplace analysis (session 1180) provides solid technical basis
- **Correct prerequisite sequencing**: v0.3.1 (Python migration) before extraction prevents double-migration waste
- **Appropriate granularity**: 4 plugins balance install flexibility vs maintenance burden
- **Clear namespace impact**: Breaking change acknowledged with mitigation strategy
- **Versioning alignment**: awesome-ai v0.4.0 aligns with ai-agents milestone for version truth

## Issues Found

### Critical (Must Fix)

#### C1: PowerShell-to-Python Migration Timeline Conflict

**Location**: Prerequisites section, ADR-045 line 35-36

**Issue**: v0.3.1 prerequisite completion date is 2027-01-25 (12-month timeline per PowerShell-migration.md). ADR-045 Gantt chart shows v0.4.0 starting 2026-02-10 with v0.3.1 completing 2027-01-25 but framework extraction phases starting before that date.

**Evidence**:
- v0.3.1 PowerShell-migration.md shows P5 retirement milestone on 2027-01-25
- ADR-045 Gantt shows "Phase 1: Core Agents" starting "after prereq2" which ends 2027-01-25
- v0.4.0 PLAN.md shows extraction phases spanning months 1-14

**Impact**: If v0.4.0 extraction begins before v0.3.1 completes, extracted code will be PowerShell that requires immediate re-migration in awesome-ai. This doubles effort and contradicts ADR-042 rationale.

**Recommendation**:
1. Update ADR-045 to explicitly state: "v0.4.0 extraction CANNOT begin until v0.3.1 P5 retirement milestone completes (2027-01-25)"
2. Add blocking gate: "All extracted code must be Python before moving to awesome-ai"
3. Revise Gantt chart to show Phase 0 starting no earlier than 2027-02-01

#### C2: Inventory Verification Methodology Missing

**Location**: Inventory Summary (ADR-045 lines 127-142)

**Issue**: No documented methodology for classifying 65% framework / 25% domain / 10% hybrid. Classification criteria exist (line 138-142) but no verification process.

**Evidence**:
- Classification criteria: "Framework: Generic multi-agent infrastructure, no project-specific references"
- No grep patterns, validation scripts, or audit trail
- Inventory numbers appear hand-counted without verification

**Impact**: Misclassified files could leak project-specific assumptions into framework, breaking consumers. Hybrid files (10%) are particularly risky for undetected hard-coded paths.

**Recommendation**:
1. Create `scripts/verify-framework-inventory.py` that:
   - Greps for hard-coded paths (`.agents/`, `.serena/`, project-specific terms)
   - Validates all framework files have no domain references
   - Outputs classification report with violations
2. Add to Phase 0 deliverables: "Run inventory verification, resolve all violations"
3. Document methodology in ADR-045 under "Inventory Verification" section

#### C3: Path Abstraction Failure Mode Unmitigated

**Location**: Path Abstraction Contract (v0.4.0 PLAN.md lines 232-241)

**Issue**: `${CLAUDE_PLUGIN_ROOT}` is documented but failure mode when variable unset is undefined. Env var defaults may fail silently in consumers with different directory structures.

**Evidence**:
- Path contract defines env vars with defaults (e.g., `AWESOME_AI_SESSIONS_DIR` defaults to `.agents/sessions`)
- No validation that consumer project has matching directory structure
- Plugin cache isolation may prevent file writes even if paths resolve

**Impact**: Skills that write to consumer paths (e.g., session-log-fixer) may fail silently or write to wrong locations. CI environments may not have `.agents/sessions/` directory.

**Recommendation**:
1. Add path validation to framework scripts:
   ```python
   SESSION_DIR = os.environ.get("AWESOME_AI_SESSIONS_DIR", ".agents/sessions")
   if not os.path.exists(SESSION_DIR):
       raise ValueError(f"Session directory not found: {SESSION_DIR}. Set AWESOME_AI_SESSIONS_DIR or create .agents/sessions/")
   ```
2. Document consumer setup requirements: "Projects using session-protocol must create `.agents/sessions/` or set AWESOME_AI_SESSIONS_DIR"
3. Add Phase 0 deliverable: "Path validation integration test with non-standard consumer structure"

#### C4: Breaking Change Migration Plan Incomplete

**Location**: Namespace Impact (ADR-045 lines 75-84)

**Issue**: Namespace migration from `/skill-name` to `/awesome-ai:skill-name` is acknowledged but migration verification is deferred to Phase 4 "automated grep sweep" with no grep patterns defined.

**Evidence**:
- 41 skills in current inventory (28 framework, 13 domain)
- References in SKILL.md, AGENTS.md, CLAUDE.md, agent prompts, CI workflows
- No exhaustive list of files to update
- "Automated grep sweep" suggests search-and-replace without verification

**Impact**: Missed namespace references will cause runtime failures when framework skills are invoked with old names. Agent prompts with `/planner` will fail to invoke `/awesome-ai:planner`.

**Recommendation**:
1. Create `scripts/find-skill-references.py` that:
   - Searches for all `/skill-name` patterns in codebase
   - Outputs file path, line number, context for each match
   - Distinguishes framework vs domain skill references
2. Add Phase 4 acceptance criteria: "Zero references to framework skills with bare names (must be namespaced)"
3. Add migration verification test: "Invoke each framework skill with new namespace, verify no 404s"

### Important (Should Fix)

#### I1: Plugin Marketplace Format Evolution Risk

**Location**: Risks table (v0.4.0 PLAN.md line 486)

**Issue**: Risk "Plugin marketplace format evolves" has mitigation "Pin to documented schema, version lock awesome-ai" but no monitoring strategy for schema changes.

**Evidence**:
- Claude Code plugin system is relatively new (researched session 1180, Feb 2026)
- No changelog subscription or schema version detection
- Breaking changes could silently fail after extraction

**Impact**: Schema evolution could break awesome-ai installations without warning. Consumer projects may be unable to install or update.

**Recommendation**:
1. Add to awesome-ai repo: `.github/workflows/schema-validation.yml` that periodically validates marketplace.json against published schema
2. Subscribe to Claude Code changelog (if available) or monitor GitHub discussions
3. Add Phase 5 deliverable: "Document schema monitoring process in awesome-ai CONTRIBUTING.md"

#### I2: Copilot CLI Investigation Scope Undefined

**Location**: Phase 0 deliverables (v0.4.0 PLAN.md line 153), Phase 5 Copilot CLI (line 443)

**Issue**: github/awesome-copilot#629 investigation planned in Phase 0 but action based on findings is vague ("If Copilot CLI supports plugins: Add platform support").

**Evidence**:
- No blocking criteria if Copilot CLI lacks plugin support
- "Add platform support" effort undefined (could be 1 day or 4 weeks)
- Phase 5 shows Copilot CLI as 3-day task without knowing scope

**Impact**: If Copilot CLI integration is critical, undefined scope could delay v0.4.0 completion. If not critical, investigation is wasted effort.

**Recommendation**:
1. Clarify decision criteria: "If Copilot CLI supports plugins AND effort < 1 week, integrate. Otherwise document gap and defer to v0.5.0"
2. Add Phase 0 output: "Copilot CLI integration decision (GO/NO-GO) with effort estimate"
3. Make Phase 5 Copilot work conditional: "If Phase 0 decision was GO, integrate. Otherwise document limitation."

#### I3: Prerequisite Completion Criteria Missing

**Location**: Prerequisites (ADR-045 lines 33-36)

**Issue**: "v0.3.0 (memory enhancement)" and "v0.3.1 (PowerShell-to-Python migration)" are prerequisites but completion criteria are not defined in ADR-045.

**Evidence**:
- v0.3.0 README.md shows 6 chains across 5 weeks but no "milestone complete" definition
- v0.3.1 shows P5 retirement milestone but no acceptance test
- ADR-045 assumes prerequisite completion but doesn't link to verification

**Impact**: v0.4.0 could start prematurely with incomplete prerequisites, leading to rework or incompatible extracted code.

**Recommendation**:
1. Add to ADR-045 "Prerequisites" section:
   - "v0.3.0 complete when: All 6 chains merged, memory router benchmarks pass ADR-037 targets"
   - "v0.3.1 complete when: Pester + PSScriptAnalyzer workflows retired, zero .ps1 files in scripts/"
2. Add Phase 0 pre-start gate: "Verify prerequisite completion before creating awesome-ai repo"

#### I4: Test Migration Strategy Undefined

**Location**: Phase 2 (v0.4.0 PLAN.md lines 328-331)

**Issue**: "Each skill passes its pytest suite from plugin location" assumes tests exist and migrate cleanly, but test data paths may break in plugin cache.

**Evidence**:
- Skills currently have relative imports and test data paths
- Plugin cache isolation changes working directory
- No plan for test data bundling or path resolution

**Impact**: Test suites may fail from plugin location even if code works, blocking verification.

**Recommendation**:
1. Add to Phase 2: "Audit all pytest test data paths, convert to package_resources or explicit bundling"
2. Add Phase 2 acceptance criteria: "All framework skills pytest suites pass when invoked from simulated plugin cache location"
3. Document test data bundling requirements in migration checklist

### Minor (Consider)

#### M1: 4-Plugin Granularity Lacks Usage Analysis

**Location**: Decision table (v0.4.0 PLAN.md line 117)

**Issue**: 4-plugin split (core-agents, framework-skills, session-protocol, quality-gates) is asserted as "balanced granularity" but no analysis of which combinations consumers need.

**Evidence**:
- No user story: "I want core-agents but not session-protocol"
- No analysis: "80% of consumers use all 4 plugins"
- Single plugin alternative rejected without usage data

**Impact**: Granularity may be too fine (forcing 4 installs when 1 would do) or too coarse (bundling unwanted components).

**Recommendation**:
1. Add usage analysis to ADR-045: "For ai-agents use case, all 4 plugins are required. For external consumers, [assumption about which subsets are useful]"
2. Defer optimization: "If usage patterns show 90%+ install all 4, consider consolidation in v0.5.0"
3. Document in awesome-ai README: "Typical installation installs all 4 plugins. Advanced users can cherry-pick."

#### M2: Namespace Collision Risk with Future Plugins

**Location**: Namespace Impact (ADR-045 line 119)

**Issue**: `/awesome-ai:skill-name` namespace is safe for current 28 framework skills but no reservation strategy for future external plugins using similar names.

**Evidence**:
- Claude Code plugin marketplace is public
- Another user could publish `awesome-ai` plugin with different skills
- Namespace collision undefined (does last install win? error?)

**Impact**: Low (project-specific namespace unlikely to collide) but could confuse users if collision occurs.

**Recommendation**:
1. Research Claude Code namespace conflict behavior (Phase 0 investigation)
2. If collisions are possible, consider namespace: `/rjmurillo-awesome-ai:skill-name` for uniqueness
3. Document in awesome-ai README: "Namespace chosen for clarity; collision unlikely but possible"

#### M3: Memory Router Extraction Not Addressed

**Location**: v0.4.0 PLAN.md Phase 2 (skills extraction)

**Issue**: ADR-037 Memory Router is Serena-first with Forgetful augmentation. Serena is Git-synced (framework), Forgetful is local (domain). Unclear if Memory Router skills belong in framework or hybrid.

**Evidence**:
- ADR-037 implementation uses `scripts/MemoryRouter.psm1` (will become Python post v0.3.1)
- Memory Router references `.serena/memories/` (consumer path)
- Forgetful endpoint from `.mcp.json` (consumer config)

**Impact**: Memory skills may fail if extracted as framework without proper path abstraction. Could be classified as hybrid requiring parameterization.

**Recommendation**:
1. Add to Phase 2 moderate-coupling skills: "Memory Router skills require AWESOME_AI_MEMORY_DIR env var"
2. Validate Memory Router works from plugin cache with parameterized paths
3. Document Forgetful MCP requirement in awesome-ai README (optional augmentation)

## Questions for Planner

1. What is the verified scope reduction of v0.4.0 if v0.3.1 does not complete until 2027-01-25? Should v0.4.0 milestone be renamed to v0.5.0 to reflect the year delay?

2. How will inventory verification (65/25/10 split) be validated? Is there a script to audit classifications or is this manual review?

3. What is the rollback strategy if Phase 4 namespace migration breaks production workflows in ai-agents? Can we maintain dual namespace support temporarily?

4. Are there any existing consumers of ai-agents framework components (forks, experiments) that would inform 4-plugin granularity design?

5. What is the acceptable failure rate for path abstraction in Phase 0 integration tests? (100% success required or graceful degradation acceptable?)

## Recommendations

### Immediate Actions

1. **Update ADR-045 with Critical Fixes**: Address C1 (timeline conflict), C2 (inventory verification), C3 (path validation), C4 (namespace migration)

2. **Add Phase 0 Blocking Gates**:
   - Verify v0.3.0 + v0.3.1 completion before starting
   - Run inventory verification script, resolve all violations
   - Path validation integration test with non-standard consumer

3. **Define Acceptance Criteria**:
   - v0.3.0 complete: All chains merged, ADR-037 benchmarks pass
   - v0.3.1 complete: Zero .ps1 in scripts/, Pester retired
   - v0.4.0 Phase 0: Path validation passes, inventory verified, Copilot decision made

### Phase-Specific Additions

**Phase 0 (Foundation)**:
- [ ] Run `scripts/verify-framework-inventory.py`, fix violations
- [ ] Create path validation integration test
- [ ] Copilot CLI investigation with GO/NO-GO decision
- [ ] Document prerequisite completion verification

**Phase 2 (Framework Skills)**:
- [ ] Audit pytest test data paths, convert to package_resources
- [ ] Memory Router path parameterization validation
- [ ] Test suites pass from simulated plugin cache

**Phase 4 (Consumer Wiring)**:
- [ ] Run `scripts/find-skill-references.py`, update all matches
- [ ] Namespace migration verification test (zero 404s)
- [ ] Integration test: Full session lifecycle with namespaced skills

**Phase 5 (Documentation)**:
- [ ] Schema monitoring process documented
- [ ] Consumer setup requirements (directory structure, env vars)
- [ ] Conditional Copilot CLI integration (if Phase 0 GO decision)

## Approval Conditions

**ADR-045 requires revision before acceptance:**

1. **C1 resolved**: Timeline clarified with v0.3.1 completion as hard blocker
2. **C2 resolved**: Inventory verification methodology documented and scripted
3. **C3 resolved**: Path validation strategy defined with failure modes
4. **C4 resolved**: Namespace migration verification plan with grep patterns

**Plan approval conditions:**

1. All Critical issues (C1-C4) addressed in revised ADR-045
2. Phase 0 blocking gates defined with measurable acceptance criteria
3. Important issues (I1-I4) acknowledged with mitigation plan or accepted risk

## Alignment Analysis

### ADR Consistency

| ADR | Alignment | Notes |
|-----|-----------|-------|
| ADR-042 (Python Migration) | ✅ ALIGNED | Correctly sequenced as prerequisite |
| ADR-037 (Memory Router) | ⚠️ PARTIAL | Memory skills extraction strategy undefined (M3) |
| ADR-030 (Skills Pattern) | ✅ ALIGNED | Skills-first pattern matches plugin model |
| ADR-007 (Memory-First) | ✅ ALIGNED | Serena-first routing preserved in extraction |
| ADR-006 (Thin Workflows) | ✅ ALIGNED | No workflow logic changes, still delegates to scripts |
| ADR-005 (PowerShell-only) | ✅ ALIGNED | Superseded by ADR-042, extraction is Python-only |

### Project Goals Alignment

**Goal: Share framework across projects** ✅ ALIGNED
- Plugin marketplace enables external consumption
- 4-plugin granularity supports partial adoption

**Goal: Reduce cognitive load in ai-agents** ✅ ALIGNED
- Separates framework from domain concerns
- Clear boundary enforced by repository split

**Goal: Enable versioned releases** ✅ ALIGNED
- awesome-ai v0.4.0 provides stable API
- Consumers can pin to specific versions

**Implicit Goal: Maintain quality** ⚠️ PARTIAL
- Test migration strategy undefined (I4)
- Path validation critical for preventing regressions (C3)

## Scope Assessment

**Well-Defined Scope**:
- 4 plugins with clear component allocation
- 6 phases with dependency flowchart
- Parallel tracks identified for optimization

**Scope Creep Risks**:
- Copilot CLI integration scope undefined (I2)
- Test data migration could expand Phase 2 by 30-50% (I4)
- Memory Router path abstraction may require architectural changes (M3)

**Missing from Scope**:
- Rollback plan if Phase 4 breaks ai-agents
- Beta testing phase with external consumers
- Documentation feedback cycle

## Risk Assessment

### Underestimated Risks

1. **Path Abstraction Failure** (C3)
   - Current risk: Medium
   - Actual risk: High
   - Mitigation gap: No integration test with diverse consumer structures

2. **Namespace Migration Verification** (C4)
   - Current risk: Medium (noted in ADR)
   - Actual risk: High
   - Mitigation gap: Grep sweep insufficient, need runtime verification

3. **Test Data Portability** (I4)
   - Current risk: Not assessed
   - Actual risk: Medium
   - Mitigation gap: No test from plugin cache location

### Missing Risks

1. **Consumer Breaking Changes**: awesome-ai v0.5.0 could break ai-agents if API changes. No semantic versioning policy.

2. **Plugin Cache Disk Space**: 4 plugins × ~50MB each = ~200MB cache. No disk space validation.

3. **Concurrent Version Conflict**: If ai-agents pins to v0.4.0 but another project uses v0.4.5, namespace collisions possible in shared environments.

## Handoff Recommendation

**Route to**: planner (for revision)

**Scope of revision**:
1. Address all Critical issues (C1-C4) with specific plan additions
2. Clarify Important issues (I1-I4) with mitigation or accepted risk
3. Add acceptance criteria for prerequisite completion and Phase 0 gates

**After revision**:
- Route back to critic for verification
- If approved, route to architect for ADR finalization
- After ADR acceptance, route to implementer for Phase 0 execution

## Verdict Rules Applied

**NEEDS REVISION** because:
- 4 Critical issues identified (blocking)
- Fundamental approach questions on timeline and prerequisites
- Missing acceptance criteria for Phase 0
- Scope has undefined elements (Copilot CLI, test migration)

**Not APPROVED** because:
- Critical issues C1-C4 must be resolved before implementation
- Prerequisite completion criteria undefined
- Path abstraction failure modes unmitigated

**Not REJECTED** because:
- Direction is sound (plugin marketplace is correct architecture)
- Research foundation is strong (session 1180 analysis)
- 4-plugin granularity is reasonable (refinable based on usage)
- Plan is detailed and well-structured (just needs critical gaps filled)

---

**Next Steps**: Planner revises ADR-045 and v0.4.0 PLAN.md addressing C1-C4, then returns to critic for re-review.
