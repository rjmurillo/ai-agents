# Remediation Plan: ADR Workflow Enforcement and Quality Gates

**Date**: 2026-01-03
**Status**: Draft
**Priority**: P0 (Critical)
**Category**: Process Enforcement

---

## Executive Summary

Two retrospectives (ADR Generation Quality and ADR Workflow Bypass) revealed systematic failures in ADR creation workflow. ADR-039 was created directly without multi-agent review and contained unverified factual claims. Root cause: unrestricted Write access combined with pull-based enforcement allows workflow bypass. Solution: multi-layer enforcement architecture with pre-action hooks, pre-commit validation, and CI gates.

**Impact**: ADRs are gospel documents. Single unverified claim triggers "bozo bit" and undermines institutional credibility.

**Risk**: Without enforcement, agents will continue bypassing multi-agent validation when context is available.

---

## Problem Statement

### Quality Failures (from ADR Generation Quality Retrospective)

**Observed Issues**:
- Unverified model release dates (no web search)
- Unverified pricing claims stated as facts
- Phantom statistics ("290 sessions analyzed" with no evidence)
- Contradictory session claims ("sessions 289-290" vs "290 sessions")
- Critic reviewed methodology, missed factual errors
- adr-review skill not invoked despite availability

**Root Cause**: ADR generation workflow lacks verification gates for factual claims. No classification system for experiential vs factual claims. No research phase before drafting.

**Evidence**: ADR-039 accepted with multiple factual errors. Critique document focused on token measurement, not fact verification.

### Workflow Bypass (from ADR Workflow Bypass Retrospective)

**Observed Issues**:
- ADR-039 created directly via Write tool (no delegation to architect)
- Architect BLOCKING protocol bypassed by not delegating at all
- adr-review skill never invoked (no multi-agent debate)
- ADR-039 never committed (orphaned file)
- No pre-action validation before Write operations

**Root Cause**: Claude Code framework provides unrestricted Write access. Pull-based enforcement (agent prompts with BLOCKING language) can be bypassed by not delegating.

**Evidence**: Architect agent prompt lines 445-465 have MANDATORY routing to adr-review, but I bypassed by creating file directly. Session 92 documented this exact limitation.

### Combined Impact

**User Trust Statement** (from Workflow Bypass):
> "You have said yourself you cannot be trusted and all your work MUST be verified and constrained with tooling--if it isn't, it's merely a suggestion you can (and will at some point) ignore."

**Success Rate**:
- Quality: 50% (process succeeded, quality failed)
- Workflow: 0% (complete bypass)

---

## Extracted Learnings Summary

### From ADR Generation Quality (11 learnings, 80-95% atomicity)

| Skill ID | Statement | Atomicity | Priority |
|----------|-----------|-----------|----------|
| Skill-Research-001 | Classify ADR claims as experiential vs factual before drafting | 95% | P0 |
| Skill-Research-002 | Verify pricing, dates, statistics via web search before ADR | 92% | P0 |
| Skill-ADR-001 | Invoke adr-review skill for all ADRs regardless of source | 90% | P0 |
| Skill-ADR-002 | Analyst produces evidence document before architect drafts ADR | 88% | P0 |
| Skill-Critic-002 | Critic reviews structure then verifies facts separately | 85% | P1 |
| Skill-ADR-003 | Retrospective ADRs require analyst fact-check despite implementation | 87% | P1 |
| Skill-ADR-004 | ADR factual claims must cite sources | 90% | P1 |
| Skill-Research-003 | Usage statistics must reference analysis artifacts | 93% | P1 |
| Skill-ADR-005 | ADR type determines verification requirements | 85% | P2 |
| Skill-Process-001 | Root cause ADR failures by examining workflow gates | 80% | P2 |
| Skill-Critic-003 | Separate critique scope for PR vs ADR quality | 88% | P1 |

### From ADR Workflow Bypass (8 learnings, 87-95% atomicity)

| Skill ID | Statement | Atomicity | Priority |
|----------|-----------|-----------|----------|
| git-hook-adr-validation | Pre-commit hook validates ADR files reference debate log | 95% | P0 |
| enforcement-pull-vs-push | Pull-based enforcement requires push-based detection for critical workflows | 92% | P0 |
| context-availability-illusion | Data availability does not eliminate specialist workflow validation | 88% | P1 |
| multi-layer-enforcement | Critical workflows require prompts + hooks + CI layers | 93% | P0 |
| session-end-workflow-audit | Session end must include self-audit for workflow bypasses | 87% | P1 |
| root-cause-classification | Classify root causes as Controllable vs Framework vs External | 90% | P2 |
| enforcement-redundancy | Enforcement requires prevention, detection, validation | 92% | P0 |
| SESSION-PROTOCOL BLOCKING ops | Enumerate specific BLOCKING operations in protocol | 90% | P0 |

**Total**: 19 learnings across quality and enforcement domains

---

## Remediation Strategy: Multi-Layer Enforcement

Inspired by security defense-in-depth: multiple independent layers so single-point failure doesn't compromise system.

### Layer 0: Pre-Action Hooks (NEW - Inspired by claude-flow)

**Pattern**: Before executing protected operations, check memory/protocol for requirements.

**Implementation**: Add pre-action protocol checks to main agent prompt.

**Trigger**: Before Write operations to `.agents/architecture/`, `.agents/security/`

**Action**:
```markdown
BLOCKING GATE: Protected File Operations

Before Write/Edit operations matching these patterns, MUST check:
- `.agents/architecture/ADR-*.md` → Verify delegation to orchestrator occurred
- `.agents/security/SR-*.md` → Verify delegation to security agent occurred

If delegation did NOT occur, HALT and delegate to orchestrator.

Evidence: Task tool invocation in current session.
```

**Rationale**: Prevents workflow bypass at the source. If I never delegate, I never create protected files.

**Limitation**: Pull-based (requires me to read prompt). Layer 1+ provides detection/validation.

### Layer 1: Agent Prompts with BLOCKING Language (EXISTING - Strengthen)

**Current State**: Architect agent has BLOCKING protocol (lines 445-465) requiring adr-review invocation.

**Gap**: Only works if delegation to architect occurs. Bypassed when no delegation.

**Improvement**: Add BLOCKING language to orchestrator and main agent prompts.

**Orchestrator Update** (`.claude/agents/orchestrator.md`):
```markdown
## ADR Creation Workflow (MANDATORY)

When user requests ADR or agent recommends ADR:

1. MUST route to analyst for research phase (evidence document)
2. MUST route to architect for ADR drafting (with evidence)
3. MANDATORY: Invoke adr-review skill after architect completes
4. BLOCKING: Cannot skip steps 1-3 even if context is available

Evidence required:
- `.agents/analysis/adr-{number}-research.md` (analyst)
- `.agents/architecture/ADR-{number}-*.md` (architect)
- `.agents/critique/adr-{number}-debate.md` (adr-review)
```

**Main Agent Update** (SESSION-PROTOCOL.md):
```markdown
### BLOCKING Operations

Operations that MUST delegate to orchestrator, NEVER act directly:

| Operation | File Pattern | Required Workflow |
|-----------|--------------|-------------------|
| ADR creation/update | `.agents/architecture/ADR-*.md` | orchestrator → analyst → architect → adr-review |
| Security review | `.agents/security/SR-*.md` | orchestrator → security agent |
| Specification | `.agents/specs/requirements/REQ-*.md` | orchestrator → spec-generator → critic |

VIOLATION: Creating these files directly bypasses multi-agent validation and WILL be caught by pre-commit hooks.
```

### Layer 2: Pre-Commit Hooks (NEW)

**Purpose**: Detect ADR files staged without evidence of multi-agent review.

**Implementation**: PowerShell pre-commit hook in `.githooks/pre-commit.d/`

**File**: `scripts/git-hooks/Validate-ADRCommit.ps1`

**Logic**:
```powershell
# 1. Find staged ADR files
$stagedADRs = git diff --cached --name-only --diff-filter=ACM |
    Where-Object { $_ -match '\.agents/architecture/ADR-\d+-.*\.md$' }

if ($stagedADRs) {
    foreach ($adr in $stagedADRs) {
        # 2. Extract ADR number
        $adrNumber = [regex]::Match($adr, 'ADR-(\d+)').Groups[1].Value

        # 3. Check for debate log in .agents/critique/
        $debateLog = Get-ChildItem .agents/critique -Filter "*adr-$adrNumber*" -File

        if (-not $debateLog) {
            Write-Error "BLOCKED: ADR-$adrNumber missing debate log"
            Write-Error "Multi-agent review required: Invoke adr-review skill"
            Write-Error "Expected: .agents/critique/adr-$adrNumber-debate.md"
            exit 1
        }

        # 4. Verify debate log is also staged
        $debateLogStaged = git diff --cached --name-only | Where-Object { $_ -match "critique.*adr-$adrNumber" }
        if (-not $debateLogStaged) {
            Write-Warning "Debate log exists but not staged: $($debateLog.Name)"
            Write-Host "Adding debate log to commit..."
            git add $debateLog.FullName
        }
    }
}
```

**Installation**: Hook installation script in `scripts/git-hooks/Install-Hooks.ps1`

**Verification**: Test with intentional violation (commit ADR without debate log).

### Layer 3: Session Protocol Validation (EXISTING - Enhance)

**Current State**: `scripts/Validate-SessionEnd.ps1` checks session log completeness.

**Enhancement**: Add workflow bypass detection.

**New Check**:
```powershell
# Check for orphaned architecture files (created but not committed with proper workflow)
$orphanedADRs = git ls-files --others --exclude-standard .agents/architecture/ADR-*.md

if ($orphanedADRs) {
    Write-Error "Orphaned ADR files detected (not committed):"
    $orphanedADRs | ForEach-Object { Write-Error "  - $_" }
    Write-Error "ADRs must go through adr-review workflow before commit"
    exit 1
}

# Check session log for ADR creation without delegation evidence
$sessionLog = Get-Content $SessionLogPath -Raw
if ($sessionLog -match 'ADR-\d+' -and $sessionLog -notmatch 'Task.*architect|Task.*orchestrator') {
    Write-Error "Session log mentions ADR but no delegation evidence found"
    Write-Error "Required: Task tool invocation to architect or orchestrator"
    exit 1
}
```

### Layer 4: CI Validation Workflow (NEW)

**Purpose**: Block PRs that modify ADR files without debate log evidence.

**Implementation**: GitHub Actions workflow

**File**: `.github/workflows/validate-adr.yml`

**Trigger**: PR opened/updated with changes to `.agents/architecture/ADR-*.md`

**Logic**:
```yaml
name: ADR Validation

on:
  pull_request:
    paths:
      - '.agents/architecture/ADR-*.md'

jobs:
  validate-adr:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for comparison

      - name: Validate ADR Multi-Agent Review
        shell: pwsh
        run: |
          # Get ADR files changed in this PR
          $adrFiles = git diff --name-only origin/${{ github.base_ref }}...HEAD |
              Where-Object { $_ -match '\.agents/architecture/ADR-(\d+)-.*\.md$' }

          $validationFailed = $false

          foreach ($adr in $adrFiles) {
              $adrNumber = [regex]::Match($adr, 'ADR-(\d+)').Groups[1].Value
              Write-Host "Validating ADR-$adrNumber..."

              # Check 1: Debate log exists
              $debateLog = Get-ChildItem .agents/critique -Filter "*adr-$adrNumber*" -File -ErrorAction SilentlyContinue

              if (-not $debateLog) {
                  Write-Error "❌ ADR-$adrNumber: Missing debate log in .agents/critique/"
                  Write-Error "   Required: Multi-agent review via adr-review skill"
                  $validationFailed = $true
                  continue
              }

              # Check 2: Debate log included in PR
              $debateLogInPR = git diff --name-only origin/${{ github.base_ref }}...HEAD |
                  Where-Object { $_ -match "critique.*adr-$adrNumber" }

              if (-not $debateLogInPR) {
                  Write-Error "❌ ADR-$adrNumber: Debate log not included in PR"
                  Write-Error "   Found: $($debateLog.Name)"
                  Write-Error "   Action: Add debate log to PR"
                  $validationFailed = $true
                  continue
              }

              # Check 3: Research artifact exists (for non-trivial ADRs)
              $researchDoc = Get-ChildItem .agents/analysis -Filter "*adr-$adrNumber-research*" -File -ErrorAction SilentlyContinue
              if (-not $researchDoc) {
                  Write-Warning "⚠️  ADR-$adrNumber: No research document found"
                  Write-Warning "   Expected: .agents/analysis/adr-$adrNumber-research.md"
                  Write-Warning "   This may be acceptable for trivial ADRs"
              }

              Write-Host "✅ ADR-$adrNumber: Validation passed"
          }

          if ($validationFailed) {
              Write-Error "ADR validation failed. See errors above."
              exit 1
          }

          Write-Host "All ADR validations passed."
```

**Status Check**: Required check for PR merge (configured in branch protection).

### Layer 5: Documentation Updates (PROTOCOL)

**Files to Update**:

1. **SESSION-PROTOCOL.md**: Add BLOCKING Operations table
2. **CLAUDE.md**: Add Protected Operations section
3. **architect.md**: Verify existing BLOCKING protocol (lines 445-465)
4. **orchestrator.md**: Add ADR workflow requirements

**SESSION-PROTOCOL.md Addition**:
```markdown
## BLOCKING Operations

These operations MUST delegate to orchestrator. NEVER create files matching these patterns directly.

| Pattern | Workflow | Why |
|---------|----------|-----|
| `.agents/architecture/ADR-*.md` | orchestrator → analyst → architect → adr-review | Multi-agent validation required |
| `.agents/security/SR-*.md` | orchestrator → security → validation | Security expertise required |
| `.agents/specs/requirements/REQ-*.md` | orchestrator → spec-generator → critic | Formal specification process |

### Enforcement Layers

1. **Pre-action**: Check protocol before Write operations
2. **Prompts**: BLOCKING language in agent prompts
3. **Pre-commit**: Hook validates debate log exists
4. **Session validation**: Detects orphaned files
5. **CI**: GitHub Actions blocks PRs without evidence

### Self-Audit Checklist (Session End)

Before session end, verify:
- [ ] No orphaned ADR files (created but not committed)
- [ ] All ADR commits reference debate log
- [ ] All protected operations delegated (Task tool evidence)
```

**CLAUDE.md Addition**:
```markdown
## Protected Operations

NEVER create these files directly. ALWAYS delegate to orchestrator first.

### File Patterns

| Pattern | Why Protected | Required Agent |
|---------|---------------|----------------|
| `.agents/architecture/ADR-*.md` | Gospel status - multi-agent validation required | architect + adr-review skill |
| `.agents/security/SR-*.md` | Security-critical - specialist review required | security agent |
| `.agents/specs/requirements/REQ-*.md` | Formal specs - traceability required | spec-generator |

### Detection

Violations caught by:
- Pre-commit hook (blocks commits without debate log)
- Session validation (detects orphaned files)
- CI workflow (blocks PRs without evidence)

### Example

❌ **WRONG**: `Write(file_path=".agents/architecture/ADR-040-*.md", content="...")`

✅ **CORRECT**: `Task(subagent_type="orchestrator", prompt="Create ADR for [topic]")`
```

---

## Improved ADR Workflow (7-Phase)

Synthesizing learnings from both retrospectives:

### Phase 1: Research (MANDATORY)

**Agent**: analyst

**Output**: `.agents/analysis/adr-{number}-research.md`

**Activities**:
1. Classify claims as experiential (from sessions) or factual (need web search)
2. Gather evidence:
   - Experiential: Query memory, read session logs
   - Factual: WebSearch for pricing, dates, statistics
3. Produce evidence document with:
   - Claims inventory
   - Evidence per claim
   - Source citations
   - Open questions (if any)

**Quality Gate**: Evidence document exists with all factual claims verified via web search.

### Phase 2: Draft (ARCHITECT)

**Agent**: architect

**Output**: `.agents/architecture/ADR-{number}-*.md`

**Activities**:
1. Read evidence document from Phase 1
2. Draft ADR following template
3. Cite sources for every factual claim (reference evidence document)
4. Flag assumptions if verification incomplete

**Quality Gate**: Every factual claim has citation to evidence document or web search result.

### Phase 3: Fact-Check (ANALYST)

**Agent**: analyst

**Output**: `.agents/analysis/adr-{number}-fact-check.md`

**Activities**:
1. Extract all claims from ADR draft
2. Cross-reference against evidence document
3. Web search verification for any new factual claims
4. Flag discrepancies
5. Produce fact-check report with PASS/FAIL per claim

**Quality Gate**: Fact-check report shows PASS for all claims.

### Phase 4: Logic Review (CRITIC)

**Agent**: critic

**Output**: `.agents/critique/adr-{number}-critique.md`

**Activities**:
1. Structure review (follows template?)
2. Logic review (reasoning sound?)
3. Citation review (sources properly cited?)
4. Consistency review (claims internally consistent?)

**Quality Gate**: Critique shows PASS for structure, logic, citations, consistency.

### Phase 5: Challenge Assumptions (INDEPENDENT-THINKER)

**Agent**: independent-thinker

**Output**: `.agents/critique/adr-{number}-challenge.md`

**Activities**:
1. Challenge strategic reasoning (right decision?)
2. Challenge alternatives (other options evaluated?)
3. Challenge impact (consequences accurate?)

**Quality Gate**: Challenge report reviewed and concerns addressed.

### Phase 6: Multi-Agent Debate (ADR-REVIEW SKILL)

**Skill**: adr-review

**Output**: `.agents/critique/adr-{number}-debate.md`

**Activities**:
1. Invoke specialist agents (architect, critic, analyst, security, independent-thinker, high-level-advisor)
2. Structured debate (each perspective reviewed)
3. Convergence (iterate until consensus or document dissent)

**Quality Gate**: Consensus achieved OR dissent documented with acceptable rationale.

### Phase 7: Acceptance

**Agent**: architect

**Output**: Updated ADR with status "Accepted"

**Activities**:
1. Incorporate feedback from all phases
2. Update ADR with final revisions
3. Mark as Accepted with date
4. Commit to repository (triggers Layer 2 validation)

**Quality Gate**: All phases 1-6 passed, pre-commit hook allows commit.

### Workflow Decision Tree

```text
Start: ADR Needed
  |
  +--> User request or agent recommendation?
        |
        YES --> Delegate to orchestrator (MANDATORY)
        |
        +--> Orchestrator routes to analyst (Phase 1: Research)
              |
              +--> Evidence document complete?
                    |
                    YES --> Route to architect (Phase 2: Draft)
                    |
                    +--> Route to analyst (Phase 3: Fact-Check)
                          |
                          +--> All claims PASS?
                                |
                                YES --> Route to critic (Phase 4: Logic)
                                |
                                +--> Critique PASS?
                                      |
                                      YES --> Route to independent-thinker (Phase 5: Challenge)
                                      |
                                      +--> Invoke adr-review skill (Phase 6: Debate)
                                            |
                                            +--> Consensus?
                                                  |
                                                  YES --> Architect finalizes (Phase 7: Accept)
                                                  |
                                                  +--> Commit (Layer 2: pre-commit validation)
                                                        |
                                                        +--> Debate log exists?
                                                              |
                                                              YES --> Commit succeeds
                                                              NO  --> BLOCKED (hook fails)
```

### Retrospective ADR Special Handling

When ADR is created AFTER implementation (retrospective justification):

**Additional Requirements**:
- Mark status as "Retrospective" explicitly
- Document why retrospective (emergency, fast-moving, etc.)
- Add "Lessons Learned" section
- Phase 3 (Fact-Check) is MANDATORY (cannot skip)
- Phase 6 (Multi-Agent Debate) is MANDATORY (higher confirmation bias risk)

**Rationale**: Retrospective ADRs have higher risk of:
- Confirmation bias (justifying what's done)
- Incomplete alternatives analysis (other options not evaluated)
- Unverified claims (relying on memory not research)

---

## Implementation Roadmap

### Wave 1: Critical Enforcement (P0)

**Goal**: Prevent future workflow bypasses

**Deliverables**:
1. Pre-commit hook script (`Validate-ADRCommit.ps1`)
2. Hook installation script (`Install-Hooks.ps1`)
3. SESSION-PROTOCOL.md BLOCKING Operations section
4. CLAUDE.md Protected Operations section
5. CI workflow (`validate-adr.yml`)

**Acceptance Criteria**:
- Pre-commit hook blocks ADR commit without debate log
- CI workflow fails PR with ADR change but no debate log
- Documentation clearly enumerates BLOCKING operations

**Timeline**: 1 session (implement, test, document)

### Wave 2: Quality Gates (P1)

**Goal**: Improve ADR quality through verification workflow

**Deliverables**:
1. 7-phase ADR workflow documentation (in `.agents/workflows/adr-generation.md`)
2. Evidence document template (`.agents/templates/adr-research.md`)
3. Fact-check report template (`.agents/templates/adr-fact-check.md`)
4. Updated architect agent prompt (research phase requirement)
5. Updated critic agent prompt (dual-pass review: structure + facts)

**Acceptance Criteria**:
- Architect agent requires evidence document before drafting
- Critic agent performs fact verification via web search
- Templates guide analyst through claim classification

**Timeline**: 1 session (document workflow, create templates)

### Wave 3: Automation and Tooling (P2)

**Goal**: Reduce manual verification burden

**Deliverables**:
1. ADR claim classifier script (experiential vs factual detection)
2. Fact verification helper (extract claims, suggest web searches)
3. Debate log validator (ensures all required agents participated)
4. Session end self-audit script (detect orphaned files, missing delegations)

**Acceptance Criteria**:
- Automated claim detection (at least common patterns: pricing, dates, statistics)
- Self-audit script catches violations before user feedback
- Debate log format validated automatically

**Timeline**: 2 sessions (script development, testing, integration)

---

## Success Metrics

### Enforcement Effectiveness

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| ADR workflow bypasses | 1 (Session 128) | 0 | Session protocol violations detected |
| Pre-commit hook blocks | N/A | 100% | Intentional violations during testing |
| CI workflow blocks | N/A | 100% | PRs with ADRs but no debate log |
| Orphaned ADR files | 1 (ADR-039) | 0 | Git status at session end |

### Quality Improvement

| Metric | Baseline (ADR-039) | Target | Measurement |
|--------|-------------------|--------|-------------|
| Unverified factual claims | 7 | 0 | Fact-check report validation |
| Web searches performed | 0 | 1+ per ADR | Evidence document citations |
| Multi-agent debates | 0 | 1 per ADR | Debate log existence |
| Research artifacts | 0 | 1 per ADR | Evidence document + fact-check report |

### Process Compliance

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| 7-phase workflow adherence | 0% | 100% | Phase completion checklist |
| adr-review skill invocation | 0% (ADR-039) | 100% | Debate log evidence |
| Session end self-audit | No | Yes | SESSION-PROTOCOL checklist |

---

## Risk Assessment

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pre-commit hook false positives | Medium | Medium | Escape hatch for emergencies (document in commit) |
| CI workflow blocks legitimate work | Low | High | Clear error messages with remediation steps |
| Hook installation not universal | Medium | High | Add to onboarding, verify in session start |
| Framework limitation (unrestricted Write) | Certainty | High | ACCEPT - multi-layer detection compensates |

### Process Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| 7-phase workflow too heavyweight | Medium | Medium | Allow condensed workflow for trivial ADRs (documented) |
| High context bypass temptation | High | High | Layer 0 pre-action hooks + session self-audit |
| Enforcement fatigue (too many checks) | Low | Medium | Automate checks, make violations rare (positive reinforcement) |

### Organizational Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Trust erosion from past violations | Certainty | High | This remediation plan + visible enforcement |
| User skepticism about agent compliance | High | High | CI/pre-commit provide independent verification |

---

## Testing Strategy

### Layer 0: Pre-Action Hooks

**Test Case 1**: User requests ADR, verify orchestrator delegation
- User: "Create ADR for [topic]"
- Expected: Task tool invocation to orchestrator (not direct Write)
- Verification: Session log shows Task call

### Layer 2: Pre-Commit Hook

**Test Case 2**: Commit ADR without debate log
- Setup: Create fake ADR-999 without debate log
- Command: `git add .agents/architecture/ADR-999-*.md && git commit -m "test"`
- Expected: Hook BLOCKS commit with error message
- Verification: Commit fails, file uncommitted

**Test Case 3**: Commit ADR with debate log
- Setup: Create ADR-999 + debate log
- Command: Stage both, commit
- Expected: Hook PASSES, commit succeeds
- Verification: Both files in git history

### Layer 3: Session Validation

**Test Case 4**: Session end with orphaned ADR
- Setup: Create ADR file, don't commit
- Command: `scripts/Validate-SessionEnd.ps1 -SessionLogPath [log]`
- Expected: Validation FAILS, reports orphaned file
- Verification: Exit code 1, error message lists ADR

### Layer 4: CI Workflow

**Test Case 5**: PR with ADR change but no debate log
- Setup: Branch with ADR-999 added, no debate log
- Action: Open PR
- Expected: CI check FAILS, PR blocked
- Verification: Status check shows failure, clear error

**Test Case 6**: PR with ADR and debate log
- Setup: Branch with both files
- Action: Open PR
- Expected: CI check PASSES
- Verification: Status check green

---

## Escape Hatches and Exceptions

### When to Allow Workflow Deviations

| Scenario | Allowed Deviation | Documentation Required |
|----------|-------------------|------------------------|
| Typo fix in existing ADR | Skip phases 1-6, direct edit | Commit message: "docs: fix typo in ADR-XXX" |
| Emergency decision (P0 incident) | Condensed workflow (phases 1,3,6 only) | ADR section: "Emergency Context" |
| Trivial decision (obvious, low-risk) | Skip phase 5 (challenge) | Critique documents why skip justified |
| Retrospective ADR (already implemented) | Phases 1,3,4,6 MANDATORY | Status: "Retrospective", Lessons Learned section |

### Pre-Commit Hook Bypass (Emergency Only)

**Command**: `git commit --no-verify -m "emergency: [reason]"`

**Requirements**:
1. Commit message MUST explain why hook bypassed
2. Follow-up commit MUST add missing artifacts (debate log)
3. Session log MUST document exception and justification

**Example**:
```bash
# Emergency bypass (P0 incident)
git commit --no-verify -m "emergency: ADR-999 for incident mitigation, debate deferred to post-incident review"

# Follow-up (within 24 hours)
# Create debate log via adr-review skill
git add .agents/critique/adr-999-debate.md
git commit -m "docs: add post-incident ADR-999 debate log"
```

---

## Rollout Plan

### Phase 1: Implementation (1 week)

**Day 1-2**: Wave 1 (Critical Enforcement)
- Create pre-commit hook script
- Create CI workflow
- Update SESSION-PROTOCOL.md and CLAUDE.md
- Install hooks locally
- Test all layers

**Day 3-4**: Wave 2 (Quality Gates)
- Document 7-phase workflow
- Create templates (research, fact-check)
- Update agent prompts (architect, critic)
- Test workflow with sample ADR

**Day 5**: Wave 3 (Automation)
- Create session end self-audit script
- Create claim classifier prototype
- Integrate into session protocol

**Day 6-7**: Testing and Documentation
- End-to-end testing with intentional violations
- Documentation review
- Commit all artifacts

### Phase 2: Validation (1 session)

**Activity**: Create next ADR using new workflow
- Follow 7-phase process
- Verify all enforcement layers trigger correctly
- Document any friction points
- Refine based on learnings

### Phase 3: Retrospective (1 session)

**Activity**: Meta-retrospective on remediation effectiveness
- Did enforcement prevent bypasses?
- Did quality gates catch factual errors?
- Was workflow too heavyweight?
- Extract additional learnings

---

## Appendix A: Skill Persistence Plan

### Skills from ADR Generation Quality (11 skills)

**Batch 1** (delegate to skillbook):
1. Skill-Research-001: Claim classification (experiential vs factual)
2. Skill-Research-002: Web search for pricing, dates, statistics
3. Skill-Research-003: Statistics provenance requirement
4. Skill-ADR-001: adr-review mandatory for all ADRs
5. Skill-ADR-002: Research phase before drafting

**Batch 2** (delegate to skillbook):
6. Skill-ADR-003: Retrospective ADR fact-check gate
7. Skill-ADR-004: Citation requirement for factual claims
8. Skill-ADR-005: ADR type determines verification requirements
9. Skill-Critic-002: Dual-pass review (structure + facts)
10. Skill-Critic-003: Separate critique scope (PR vs ADR)
11. Skill-Process-001: Root cause via workflow gates

### Skills from ADR Workflow Bypass (8 skills)

**Batch 3** (delegate to skillbook):
1. git-hook-adr-validation: Pre-commit validation
2. enforcement-pull-vs-push: Pull requires push detection
3. context-availability-illusion: Data availability doesn't eliminate workflow
4. multi-layer-enforcement: Prompts + hooks + CI layers

**Batch 4** (delegate to skillbook):
5. session-end-workflow-audit: Self-audit for bypasses
6. root-cause-classification: Controllable vs Framework vs External
7. enforcement-redundancy: Prevention + detection + validation
8. SESSION-PROTOCOL BLOCKING ops: Enumerate protected operations

**Total**: 19 skills to persist

---

## Appendix B: Memory Entities

### From ADR Generation Quality

1. **ADR-039-Failures** (RootCause)
   - File: `.serena/memories/root-cause-adr-quality.md`
   - Content: Retrospective ADR with unverified factual claims accepted despite quality gaps

2. **ADR-Workflow-V2** (Process)
   - File: `.serena/memories/process-adr-workflow.md`
   - Content: 7-phase workflow with mandatory research, fact-check, multi-agent debate

3. **Quality-Gates-ADR** (Checklist)
   - File: `.serena/memories/checklist-adr-quality.md`
   - Content: 7 quality gates with exit criteria for ADR generation

### From ADR Workflow Bypass

4. **RootCause-Framework-001** (FailurePattern)
   - File: `.serena/memories/failure-patterns-framework.md`
   - Content: Claude Code Write tool unrestricted access enables workflow bypass

5. **EnforcementPattern-001** (Pattern)
   - File: `.serena/memories/enforcement-patterns.md`
   - Content: Multi-layer enforcement (prompts + hooks + CI) for critical workflows

6. **CognitivePattern-001** (Pattern)
   - File: `.serena/memories/cognitive-patterns-agents.md`
   - Content: High context availability creates specialist workflow bypass temptation

**Total**: 6 memory entities

---

## Appendix C: References

**Retrospectives**:
- `.agents/retrospective/2026-01-03-adr-generation-quality.md`
- `.agents/retrospective/2026-01-03-adr-workflow-bypass.md`

**Session Logs**:
- `.agents/sessions/2026-01-03-session-128-context-optimization.md` (violation occurred)
- `.agents/sessions/2025-12-27-session-92-*.md` (prior documentation of pull-based limitation)

**Agent Prompts**:
- `.claude/agents/architect.md` lines 445-465 (BLOCKING protocol)
- `.claude/agents/orchestrator.md` (to be updated)

**Existing Artifacts**:
- ADR-039 (orphaned file, never committed, contains errors)
- Critique of context optimization (methodology focus, missed factual errors)

**Canonical Patterns**:
- claude-flow reasoningbank (pre-action hooks inspiration)
- Defense-in-depth security (multi-layer enforcement analogy)

---

**End of Remediation Plan**

**Next Steps**:
1. Route to skillbook for skill persistence (19 skills)
2. Route to memory for entity creation (6 entities)
3. Route to implementer for script creation (Wave 1)
4. Create GitHub epic issue with linked sub-tasks
5. Begin Wave 1 implementation
