# MCP PRD Critique - Three MCP Strategy Review

> **Critic Agent Review**
> **Date**: 2025-12-21
> **Documents Reviewed**:
> - PRD-session-state-mcp.md
> - PRD-skill-catalog-mcp.md
> - PRD-agent-orchestration-mcp.md
>
> **Review Objective**: Evaluate completeness, feasibility, evidence quality, risk coverage, and cross-PRD integration

---

## Executive Summary

### Overall Assessment: APPROVE WITH CONDITIONS

All three PRDs demonstrate strong evidence-based reasoning, comprehensive requirements, and realistic implementation plans. However, **critical integration risks** and **dependency coordination** require explicit mitigation before implementation begins.

### Key Findings

| PRD | Verdict | Confidence | Critical Issues |
|-----|---------|------------|-----------------|
| **Session State MCP** | APPROVE WITH CONDITIONS | High | 1 critical: Serena dependency fallback needs validation |
| **Skill Catalog MCP** | APPROVE WITH CONDITIONS | High | 2 critical: Blocking gate false positives, capability map maintenance |
| **Agent Orchestration MCP** | REQUEST CHANGES | Medium | 3 critical: Three-MCP coordination, HANDOFF.md transition, parallel timeout |

### Decision Summary

- **Session State MCP**: Ready for Phase 1 implementation with fallback validation
- **Skill Catalog MCP**: Ready for Phase 0-1 with refined capability map strategy
- **Agent Orchestration MCP**: Requires integration test plan and HANDOFF.md deprecation timeline before approval

---

## 1. PRD-session-state-mcp.md Review

### 1.1 Completeness ✅ STRONG

**Strengths**:
- All 12 sections fully developed with clear RFC 2119 requirements
- 5 phased requirements (F1-F5) with verification criteria
- 4 technical requirement sections (T1-T4) covering integration, performance, security, reliability
- Success metrics baseline/target with specific measurement methods
- Evidence from 5+ retrospectives with quantitative data

**Minor Gaps**:
- **Q11.1 (Design Decision)**: "Should session_start() auto-invoke Serena init?" - Recommendation is clear (B: keep explicit), but **no fallback if agents still skip**. Suggest adding enforcement mechanism (e.g., Session State MCP refuses to advance without Serena evidence).
- **Open Question: Mid-session crash recovery** - Orphan expiration (24h) is reasonable, but **no mechanism to alert user of orphaned session**. Add to Phase 4 requirements.

**Rating**: 9/10 - Comprehensive, minor procedural gaps

---

### 1.2 Feasibility ✅ REALISTIC

**Strengths**:
- Success metrics are achievable: 100% BLOCKING gate compliance proven (79% Session Start with blocking language)
- Phased approach (4 phases over 4 weeks) with clear acceptance criteria
- Performance requirements realistic (<500ms local, <5s external validation)
- Serena fallback to file-based state (`.agents/sessions/.session-state.json`) provides graceful degradation

**Concerns**:

#### **CRITICAL: Serena Dependency Fallback Validation**

**Issue**: Spec claims "File-based fallback in degraded mode" (T1.4, Risk mitigation), but **no validation that fallback preserves cross-session context**.

**Evidence Gap**: If Serena MCP is unavailable, how does Session State MCP restore `session-history` memory (F3.2) from file-based state?

**Mitigation Required**:
1. Add **Phase 1.5 Acceptance Criteria**: "File-based fallback tested with Serena unavailable"
2. Specify fallback file format: `.agents/sessions/.session-history.json` (in addition to `.session-state.json`)
3. Add **T1.6 (MUST)**: "MCP MUST detect Serena availability on startup and log fallback mode activation"

**Risk Level**: HIGH (impacts primary goal F3.1-F3.5: Cross-Session Context)

**Recommendation**: BLOCK Phase 2 (Cross-Session Context) until Phase 1.5 fallback validation passes.

---

#### **Performance Metric: Markdownlint External Check**

**Issue**: T2.2 allows up to 5s for external checks (markdownlint). Current project has 100+ markdown files.

**Question**: Has markdownlint performance been benchmarked? If `npx markdownlint-cli2 "**/*.md"` takes >10s, this blocks session end validation.

**Mitigation**:
- Add to **Open Questions** (Q11.5): "Markdownlint performance with 100+ files"
- Benchmark in Phase 2 implementation
- Fallback: `markdownlint-cli2 --fix ".agents/**/*.md"` (subset) instead of all files

**Risk Level**: MEDIUM (impacts user experience, not blocking)

---

**Rating**: 8/10 - Realistic with critical fallback validation gap

---

### 1.3 Evidence Quality ✅ EXCELLENT

**Strengths**:
- **Quantitative evidence**: 95.8% Session End failure rate (23 of 24 sessions), 5+ violations per session (Session 15)
- **Comparative evidence**: 79% Session Start compliance (with BLOCKING) vs 4.2% Session End (trust-based) - proves pattern
- **Failure examples**: Session 46 false positive, Session 15 multiple violations, 2025-12-20 batch
- **Success examples**: Session 44 100% compliant, Sessions 19-21 BLOCKING gate adherence
- **Retrospective citations**: 3 retrospectives referenced with file paths

**Minor Issues**:
- **Session 44 reference** (Section 12): Cited as "100% compliant session" but **no link to session log file path**. Add absolute path for verifiability.
- **skill-protocol-002 citation**: Referenced in Section 2.3 and 12, but **not linked in Appendix**. Add to Reference Documents.

**Rating**: 10/10 - Best-in-class evidence backing

---

### 1.4 Risk Coverage ✅ COMPREHENSIVE

**Strengths**:
- 9 risks identified (3 high, 4 medium, 2 low) with probability, impact, mitigation
- **High-risk items** all have concrete mitigations (file fallback, rate limits, benchmarks)
- **Serena dependency** (High risk) has fallback + degraded mode logging
- **Agent force abuse** (Medium risk) has rate limit (max 3/session) + violation log

**Concerns**:

#### **Risk: State Machine Bugs (Medium risk)**

**Mitigation**: "Comprehensive unit tests; state snapshots for rollback"

**Gap**: No mention of **integration tests with Serena MCP**. Unit tests alone won't catch Serena memory corruption edge cases (T4.1).

**Recommendation**: Add to Phase 1 Acceptance Criteria:
- "Integration test: State persists across MCP restart (via Serena memory)"
- "Integration test: State recovers from Serena memory corruption (fallback to file)"

**Risk Level**: MEDIUM (state machine is critical path)

---

#### **Risk: Documentation Drift (Medium risk)**

**Mitigation**: "SESSION-PROTOCOL.md remains canonical; MCP reads it programmatically"

**Gap**: **How** does MCP read SESSION-PROTOCOL.md programmatically? Spec doesn't define parsing logic.

**Question**: Is MCP hardcoding gates, or parsing SESSION-PROTOCOL.md dynamically?

**If hardcoded**: Documentation drift risk is REAL (updates to SESSION-PROTOCOL.md won't reflect in MCP).

**If dynamic**: Add **F1.6 (MUST)**: "MCP MUST parse SESSION-PROTOCOL.md for gate definitions on startup"

**Recommendation**: Clarify in **Open Questions** (Q11.6): "Should MCP parse SESSION-PROTOCOL.md or hardcode gates?"

**Risk Level**: MEDIUM (impacts maintainability)

---

**Rating**: 8/10 - Comprehensive with integration test gap

---

### 1.5 Session State MCP - Final Verdict

**APPROVE WITH CONDITIONS**

**Conditions**:
1. ✅ **BLOCKING**: Validate Serena fallback in Phase 1.5 (cross-session context recovery)
2. ✅ **BLOCKING**: Add integration tests for Serena MCP state persistence (Phase 1 acceptance criteria)
3. ⚠️ **RECOMMENDED**: Clarify SESSION-PROTOCOL.md parsing strategy (hardcoded vs dynamic)
4. ⚠️ **RECOMMENDED**: Benchmark markdownlint performance (Phase 2)
5. ⚠️ **RECOMMENDED**: Add session log file paths to evidence citations (Section 12)

**Confidence**: HIGH - Evidence is strong, implementation plan is realistic, risks are known.

**Risk to Project Success**: LOW if conditions 1-2 addressed, MEDIUM if skipped.

---

## 2. PRD-skill-catalog-mcp.md Review

### 2.1 Completeness ✅ STRONG

**Strengths**:
- All 14 sections fully developed (including 2 appendices with examples)
- Functional requirements organized by phase (P0-P3) with RFC 2119 levels
- Technical requirements cover architecture, performance, Serena integration, error handling
- 5 open questions with options, recommendations, decision owners, deadlines
- Evidence appendix (Appendix B) with Session 15 violation examples and root cause analysis

**Minor Gaps**:
- **REQ-INDEX-007 (SHOULD)**: "Index refresh triggered on file changes" - **No specification of how**. File watcher? Git hook? TTL? (Open Question Q1 addresses this, but requirement should reference Q1 decision).
- **REQ-SEARCH-002 (MUST)**: Weighted search fields are well-defined, but **no specification of search algorithm** (e.g., TF-IDF, fuzzy match, exact substring?). Add to Technical Requirements.
- **REQ-SUGGEST-004 (SHOULD)**: Suggestion ranking criteria clear, but **no confidence threshold for "low" vs "medium" vs "high" relevance**. Add to Open Questions or specify in requirement.

**Rating**: 8/10 - Comprehensive with minor algorithm specification gaps

---

### 2.2 Feasibility ✅ REALISTIC

**Strengths**:
- Success metrics achievable: 0 violations per session (vs current 5+), <30s skill discovery (vs 5 min manual)
- Phased approach (5 phases over 5-6 weeks) with clear dependencies
- Performance requirements realistic: <500ms search, <5s index rebuild for 50 skills
- Serena fallback to in-memory + file-based persistence (`.agents/.skill-catalog-index.json`)

**Concerns**:

#### **CRITICAL: Blocking Gate False Positives**

**Issue**: REQ-VALIDATE-005 (MUST): "For operations with existing skills, blocking MUST be true"

**Risk**: Agent needs to run `gh pr view --json customField` (custom field not in skill), but `check_skill_exists(operation="gh", subcommand="pr view")` returns `blocking: true` → Agent blocked from legitimate operation.

**Mitigation in PRD (Section 8.2)**: "Capability map only blocks exact matches (e.g., gh pr view blocked, gh pr view --json customField not blocked)"

**Gap**: **How does MCP distinguish "exact match" from "partial match"?** Subcommand alone (`pr view`) isn't sufficient - need parameter analysis.

**Recommendation**:
1. Add **REQ-VALIDATE-007 (MUST)**: "MCP MUST parse operation parameters and only block if skill supports exact parameter set"
2. Add **TECH-019**: "Capability map MUST include required parameters for exact match (e.g., gh pr view requires --json title,body)"
3. Add **Phase 2 Acceptance Criteria**: "False positive rate <5% measured against 20 known valid raw commands"

**Risk Level**: HIGH (impacts agent productivity, user trust in MCP)

---

#### **CRITICAL: Capability Map Maintenance (Open Question Q3)**

**Issue**: "Who maintains the capability map? How do we keep it in sync with new skills?"

**Current Recommendation**: "Auto-detected via replaces_command metadata field in SKILL.md"

**Gap**: **No validation that skill developers will populate replaces_command**. If field is optional or frequently forgotten, capability map becomes stale.

**Concerns**:
1. New skill added without `replaces_command` → Not detected by validation gate → Agents use raw commands despite skill existing
2. Skill updated (new parameters) but `replaces_command` not updated → False positives (blocks legitimate variations)

**Recommendation**:
1. Make `replaces_command` **REQUIRED** for executable skills (add to `.claude/skills/github/SKILL.md` schema validation)
2. Add **pre-commit hook** (or CI check) validating all skills have `replaces_command`
3. Add **Phase 1 Acceptance Criteria**: "Index build fails if executable skill missing replaces_command"
4. Move Q3 decision deadline to **Phase 0** (before implementation starts) - this is architectural, not deferred

**Risk Level**: HIGH (impacts primary goal: violation prevention)

---

**Rating**: 7/10 - Realistic implementation, but blocking gate precision needs refinement

---

### 2.3 Evidence Quality ✅ STRONG

**Strengths**:
- **Quantitative evidence**: 5+ violations in Session 15, specific examples in Appendix B
- **Violation patterns**: Raw `gh pr view`, `gh pr comment`, `gh issue edit` with "should have been" comparisons
- **Root cause analysis** (Appendix B.2): 4 reasons why agents use raw commands (habit, not checking, ignoring corrections, lack of discipline)
- **Proof of need**: "Trust-based enforcement failed" (Serena memory exists, user corrections given, violations still occurred)

**Minor Issues**:
- **skill-usage-mandatory memory citation**: Referenced throughout but **no file path in References (Section 14)**. Add `.serena/memories/skill-usage-mandatory.md`.
- **Session 15 retrospective citation**: File path given in Section 14, but **no direct quote/excerpt** from retrospective in Appendix B. Consider adding 1-2 key quotes for verifiability.
- **Skill effectiveness metrics** (Section 7.3): "Most cited skills → High-value" is qualitative, but **no baseline for "most" (e.g., >10 citations/month?)**. Minor issue, can be refined post-deployment.

**Rating**: 9/10 - Strong evidence with minor citation completeness gaps

---

### 2.4 Risk Coverage ✅ GOOD

**Strengths**:
- 5 risks identified with likelihood, impact, mitigation
- **High-impact risks** addressed: Index staleness (file watcher + TTL), false positive blocking (capability map refinement), Serena dependency (in-memory + file fallback)
- **Performance risk** (Section 8.3): <500ms SLO, in-memory cache, parallel execution

**Concerns**:

#### **Risk 8.2: False Positive Blocking - Mitigation Insufficient**

**Current Mitigation**:
1. "Capability map only blocks exact matches"
2. "Override mechanism: Agent explains why skill doesn't fit, proceeds with warning"
3. "Feedback loop: Log false positives for capability map refinement"

**Gap**: **Override mechanism is manual** (agent must explain) - defeats purpose of automated validation gate.

**Better Mitigation**:
1. **Parameter-aware blocking** (see 2.2 Feasibility concern): Block only if skill supports exact parameter set
2. **Confidence-based blocking**: `blocking: true` only if confidence >90%, otherwise `blocking: false, warning: "Skill xyz exists"`
3. **User-configurable strictness**: Allow project-level config `blocking_strictness: "strict" | "moderate" | "permissive"`

**Recommendation**: Add **Risk 8.6**: "Blocking gate undermines agent autonomy" with confidence-based mitigation

**Risk Level**: MEDIUM (usability vs enforcement trade-off)

---

#### **Risk 8.5: Serena MCP Dependency - Fallback Validation**

**Mitigation**: "In-memory fallback mode (index works without persistence)"

**Gap**: Same as Session State MCP - **no validation that in-memory fallback is tested**. What happens if Serena becomes available mid-session? Does MCP sync in-memory state to Serena?

**Recommendation**:
- Add **Phase 1 Acceptance Criteria**: "Serena unavailable mode tested (index builds in-memory, citations skip persistence)"
- Add **Phase 2**: "Serena recovery tested (MCP syncs in-memory state to Serena when available)"

**Risk Level**: MEDIUM (impacts usage tracking, not core search)

---

**Rating**: 8/10 - Good risk coverage with mitigation refinement needed

---

### 2.5 Skill Catalog MCP - Final Verdict

**APPROVE WITH CONDITIONS**

**Conditions**:
1. ✅ **BLOCKING**: Refine blocking gate to parameter-aware matching (REQ-VALIDATE-007, TECH-019)
2. ✅ **BLOCKING**: Make `replaces_command` REQUIRED for executable skills (schema validation + pre-commit hook)
3. ✅ **BLOCKING**: Validate false positive rate <5% in Phase 2 acceptance criteria
4. ⚠️ **RECOMMENDED**: Add confidence-based blocking (Risk 8.6 mitigation)
5. ⚠️ **RECOMMENDED**: Test Serena fallback and recovery (Phase 1-2 acceptance criteria)
6. ⚠️ **RECOMMENDED**: Add skill-usage-mandatory file path to References

**Confidence**: HIGH - Evidence is strong, concerns are addressable with specification refinement.

**Risk to Project Success**: MEDIUM if conditions 1-3 not addressed (blocking gate may harm more than help).

---

## 3. PRD-agent-orchestration-mcp.md Review

### 3.1 Completeness ⚠️ MOSTLY COMPLETE

**Strengths**:
- All 12 sections present with appendices (workflow diagrams, schemas, evidence references)
- Functional requirements organized by feature (FR-1 to FR-8) with RFC 2119 levels
- 6 implementation phases with dependencies, effort estimates, acceptance criteria
- 7 open questions with options, recommendations, decision owners, deadlines
- Evidence appendices (skill-orchestration-001, skill-orchestration-002, AGENT-SYSTEM.md citations)

**Significant Gaps**:

#### **GAP 1: Three-MCP Integration Architecture (CRITICAL)**

**Issue**: PRD references Session State MCP (FR-7.1, Phase 5) and Skill Catalog MCP (DEP-006), but **no diagram or specification of how three MCPs coordinate**.

**Questions**:
1. Does Agent Orchestration MCP call Session State MCP directly, or vice versa?
2. If both MCPs call Serena MCP simultaneously, who owns `agent-handoff-chain` memory? (Serena contention risk)
3. What happens if Session State MCP `record_evidence("AGENT_INVOCATION")` fails? Does Agent Orchestration MCP retry, or proceed?
4. Circular dependency: Session State → Agent Orchestration → Serena ← Session State. What is initialization order?

**Recommendation**:
1. Add **Appendix F: Three-MCP Integration Architecture**:
   - Component diagram showing MCP dependencies
   - Call sequence diagram (which MCP invokes which)
   - Error handling flow (what happens if one MCP is unavailable)
2. Add **FR-7.3 (MUST)**: "MCP MUST handle Session State MCP unavailability gracefully (skip integration, log warning)"
3. Add **TR-8.4 (MUST)**: "MCP MUST NOT block on Session State MCP calls (async integration)"

**Risk Level**: CRITICAL (three-MCP coordination is unspecified, high failure risk)

---

#### **GAP 2: HANDOFF.md Transition Plan (CRITICAL)**

**Issue**: Open Question Q7 asks "When should HANDOFF.md be deprecated?" with recommendation "Hybrid approach" (HANDOFF.md for summaries, MCP for detailed state).

**Gap**: **No specification of hybrid format**. What goes in HANDOFF.md vs MCP? Who writes to HANDOFF.md (orchestrator or MCP)? When?

**Current Conflict**:
- SESSION-PROTOCOL.md requires: "All agents MUST update HANDOFF.md at session end"
- Agent Orchestration MCP FR-4.7: "Parallel agents MUST NOT update HANDOFF.md directly (orchestrator aggregates)"

**These are contradictory**. If SESSION-PROTOCOL.md is not updated, how do agents know to skip HANDOFF.md updates?

**Recommendation**:
1. Add **Section 13: HANDOFF.md Migration Plan**:
   - Phase 1-2: Dual-write (agents update HANDOFF.md + MCP tracks handoffs) - redundancy ensures safety
   - Phase 3: Orchestrator-only writes (SESSION-PROTOCOL.md updated to allow MCP aggregation)
   - Phase 4: Deprecation decision (after 3 months of data)
2. Add **FR-4.8 (MUST)**: "MCP MUST provide orchestrator-callable write_handoff_summary(summary) tool for HANDOFF.md updates"
3. Add **TR-8.5 (MUST)**: "MCP MUST validate SESSION-PROTOCOL.md compliance (dual-write vs MCP-only mode)"

**Risk Level**: CRITICAL (violates existing protocol, will cause confusion)

---

#### **GAP 3: Parallel Execution Timeout (Open Question Q6)**

**Issue**: "How long should aggregate_parallel_results(wait_for_all=true) wait before timing out?"

**Recommendation**: "15 minutes default, configurable per invocation"

**Gap**: **No specification of what happens after timeout**. Does MCP:
- Return partial results (agents that completed)?
- Return error (all or nothing)?
- Escalate to user?

**Also**: No specification of **agent cancellation**. If timeout occurs, do running agents get terminated, or continue in background?

**Recommendation**:
1. Add **FR-4.8 (MUST)**: "MCP MUST return partial results on timeout if any agents completed, with status 'partial_timeout'"
2. Add **FR-4.9 (SHOULD)**: "MCP SHOULD NOT terminate running agents on timeout (let them complete for cache)"
3. Add **TR-5.4 (MUST)**: "MCP MUST mark timed-out agents as 'timeout' in parallel state (for orchestrator retry logic)"

**Risk Level**: HIGH (parallel execution is core feature, timeout behavior is undefined)

---

**Rating**: 6/10 - Mostly complete with critical integration and protocol gaps

---

### 3.2 Feasibility ⚠️ OPTIMISTIC

**Strengths**:
- Success metrics are measurable: 95% handoff context preservation, <2 min conflict resolution, 100% model selection accuracy
- Phased approach (6 phases over 3 months) with dependencies
- Performance requirements realistic: <500ms invoke_agent, <2000ms aggregate (5 agents)

**Concerns**:

#### **CONCERN 1: Three-MCP Coordination Complexity (Risk 6)**

**Issue**: "Agent Orchestration MCP + Serena MCP + Session State MCP create circular dependencies or coordination failures"

**Current Mitigation**: "Optional integration: Agent Orchestration MCP functions without Session State MCP"

**Gap**: If Session State MCP is optional, **how does Agent Orchestration MCP track session_id** (REQ-USAGE-003: "Citation SHOULD include session_id")?

**Also**: If Skill Catalog MCP is optional (DEP-006), **how does smart routing** (Phase 4) suggest skills without skill catalog?

**Concern**: "Optional" mitigations suggest **degraded functionality is acceptable**, but PRD doesn't specify what features are lost in degraded mode.

**Recommendation**:
1. Add **Table: MCP Integration Dependency Matrix**:
   - Agent Orchestration MCP features vs Serena/Session/Skill availability
   - Example: "Handoff tracking: REQUIRES Serena, OPTIONAL Session State, INDEPENDENT of Skill"
2. Add **TR-2.4 (MUST)**: "MCP MUST expose get_capabilities() showing which integrations are active"
3. Add **Phase 1 Acceptance Criteria**: "MCP functions with only Serena available (no Session State or Skill Catalog)"

**Risk Level**: HIGH (three-MCP coordination is unproven, complexity risk)

---

#### **CONCERN 2: Parallel Conflict Detection Algorithm (TR-6.1-6.2)**

**Issue**: "MCP MUST detect conflicts by extracting recommendations, comparing for contradictions, identifying overlapping file modifications"

**Gap**: **How?** Text similarity threshold? Keyword matching? LLM-based analysis?

**Also**: "Text similarity analysis" and "structured decision comparison" (TR-6.2) are contradictory - are decisions structured (APPROVE/REJECT) or unstructured text?

**Current State**: Agents don't use structured decision formats consistently.

**Recommendation**:
1. Add **TECH-020 (MUST)**: "MCP MUST use Levenshtein distance >80% as conflict threshold for text recommendations"
2. Add **TECH-021 (SHOULD)**: "MCP SHOULD encourage agents to use structured decision formats (APPROVE/REJECT/CONDITIONAL)"
3. Add **Phase 3 Acceptance Criteria**: "Conflict detection tested with 10 known conflict scenarios (5 true positives, 5 true negatives)"
4. Add **Phase 3 Validation**: "False positive rate <20% measured against historical parallel sessions"

**Risk Level**: HIGH (conflict detection is core to parallel execution value, algorithm is unspecified)

---

#### **CONCERN 3: Model Override Abuse (Risk 5)**

**Current Mitigation**: "Log ERROR for opus-required agents using Sonnet, Validate-SessionEnd.ps1 checks model usage"

**Gap**: How does `Validate-SessionEnd.ps1` check model usage? **Agent Orchestration MCP doesn't log to session log** (no Session State integration in Phase 1-4).

**Also**: What if orchestrator legitimately needs to override model (e.g., testing, cost constraints)?

**Recommendation**:
1. Add **FR-2.5 (MUST)**: "MCP MUST log all model overrides to session state (if available) or session log (fallback)"
2. Add **FR-2.6 (SHOULD)**: "MCP SHOULD require override_reason parameter for MUST-level model enforcement violations"
3. Update **Validate-SessionEnd.ps1** to parse Agent Orchestration MCP logs (or Serena memory `agent-invocation-history`)

**Risk Level**: MEDIUM (enforcement is specified, but validation mechanism is incomplete)

---

**Rating**: 6/10 - Feasible with critical coordination and algorithm gaps

---

### 3.3 Evidence Quality ✅ GOOD

**Strengths**:
- **Quantitative evidence**: 40% time savings (skill-orchestration-001), 100% HANDOFF conflict rate in parallel (skill-orchestration-002)
- **Concrete examples**: Sessions 19-20 HANDOFF staging conflict with commit SHA (1856a59)
- **Evidence appendices**: skill-orchestration-001/002 cited with file paths
- **Model assignment evidence**: AGENT-SYSTEM.md Section 10 model assignment table

**Minor Issues**:
- **Handoff context loss**: "~60% preservation currently" is qualitative estimate, not measured. Add caveat: "Estimated based on session log review, not empirically measured".
- **Model selection accuracy**: "~85% estimated" - same issue. Add to **Open Questions** (Q8): "Measure baseline model selection accuracy in 20 recent sessions before Phase 1".
- **skill-orchestration-002 citation**: File path given in Appendix D, but **no excerpt or key quote**. Consider adding 1-2 sentences from memory for verifiability.

**Rating**: 8/10 - Good evidence with minor estimation transparency gaps

---

### 3.4 Risk Coverage ⚠️ INCOMPLETE

**Strengths**:
- 6 risks identified with likelihood, impact, mitigation
- **High-impact risks** addressed: Adoption resistance (steering files, gradual migration), Serena unavailability (in-memory fallback)

**Critical Missing Risks**:

#### **MISSING RISK 1: Orchestrator Prompt Bloat**

**Issue**: Enriching prompts with context (FR-2.3: "prepend Prior Agent Output, Steering Guidance, artifacts") risks **token bloat**.

**Example**: If analyst produces 5000-token report, and architect handoff adds 3000 tokens, and planner adds 2000 tokens, implementer gets 10K+ token prompt before task description.

**Impact**: HIGH (exceeds model context limits, wastes tokens)

**Mitigation**:
1. Add **FR-2.7 (SHOULD)**: "MCP SHOULD truncate context to 2000 tokens max per prior agent (summarize if exceeded)"
2. Add **Open Question Q8**: "What is maximum handoff context size?" (from Q3)
3. Add **Phase 2 Validation**: "Measure actual handoff sizes, set p95 + 20% buffer limit"

**Risk Level**: HIGH (undermines primary goal: context preservation)

---

#### **MISSING RISK 2: Agent Invocation Recursion Limit**

**Issue**: What if agent A invokes agent B, which invokes agent C, which invokes agent A? (Cycle)

**Current State**: No specification of recursion depth limit or cycle detection.

**Impact**: MEDIUM (infinite loop, MCP hangs)

**Mitigation**:
1. Add **FR-2.8 (MUST)**: "MCP MUST track invocation call stack and reject cycles (A→B→A)"
2. Add **FR-2.9 (SHOULD)**: "MCP SHOULD limit call stack depth to 5 agents"

**Risk Level**: MEDIUM (edge case, but breaks MCP if occurs)

---

#### **MISSING RISK 3: Parallel Execution Deadlock**

**Issue**: What if parallel agent A waits for artifact from parallel agent B, and B waits for A? (Deadlock)

**Current State**: No specification of inter-agent dependencies in parallel execution.

**Impact**: MEDIUM (parallel execution hangs)

**Mitigation**:
1. Add **FR-4.10 (SHOULD)**: "MCP SHOULD validate parallel agents have no inter-dependencies (warn if detected)"
2. Add **Open Question Q9**: "Should MCP support parallel agent coordination (e.g., agent A signals agent B)?"

**Risk Level**: MEDIUM (parallel execution is advertised benefit, deadlock undermines it)

---

**Rating**: 6/10 - Good coverage with critical missing risks (token bloat, recursion, deadlock)

---

### 3.5 Agent Orchestration MCP - Final Verdict

**REQUEST CHANGES**

**Critical Changes Required**:
1. ✅ **BLOCKING**: Add Appendix F: Three-MCP Integration Architecture (component diagram, call sequence, error handling)
2. ✅ **BLOCKING**: Add Section 13: HANDOFF.md Migration Plan (dual-write → MCP-only transition)
3. ✅ **BLOCKING**: Specify parallel execution timeout behavior (FR-4.8-4.9, TR-5.4)
4. ✅ **BLOCKING**: Specify conflict detection algorithm (TECH-020-021, Phase 3 validation)
5. ✅ **BLOCKING**: Add missing risks (orchestrator prompt bloat, invocation recursion, parallel deadlock)

**Recommended Changes**:
6. ⚠️ **RECOMMENDED**: Add MCP Integration Dependency Matrix (which features require which MCPs)
7. ⚠️ **RECOMMENDED**: Measure baseline metrics (handoff context preservation, model selection accuracy) before Phase 1
8. ⚠️ **RECOMMENDED**: Add model override validation to Validate-SessionEnd.ps1 (FR-2.5-2.6)

**Confidence**: MEDIUM - Evidence is good, but coordination complexity and missing specifications create high risk.

**Risk to Project Success**: HIGH if changes 1-5 not addressed. Three-MCP integration is unproven and underspecified.

---

## 4. Cross-PRD Integration Analysis

### 4.1 Dependency Alignment ⚠️ NEEDS COORDINATION

**Integration Points**:

| From MCP | To MCP | Integration | Specified? | Risk |
|----------|--------|-------------|------------|------|
| **Agent Orchestration** | Serena | Handoff chain persistence | ✅ Yes (TR-4.1) | LOW |
| **Agent Orchestration** | Session State | Record invocation evidence | ⚠️ Partial (FR-7.1) | MEDIUM |
| **Skill Catalog** | Serena | Index persistence, citations | ✅ Yes (TECH-012) | LOW |
| **Skill Catalog** | Session State | Skill validation phase | ⚠️ Mentioned (TECH-018) | MEDIUM |
| **Session State** | Serena | State persistence, history | ✅ Yes (T1.1-T1.4) | LOW |
| **Session State** | Validate-SessionEnd.ps1 | Validation parity | ⚠️ Mentioned (F5.2) | MEDIUM |

**Critical Gaps**:

#### **GAP A: Session State ↔ Skill Catalog Integration**

**Session State PRD**: "Phase 1.5: Skill Validation" mentioned in multiple retrospectives, but **not in implementation phases** (Phases 1-4).

**Skill Catalog PRD**: TECH-018 (SHOULD): "If Session State MCP available, invoke check_skill_exists during SKILL_VALIDATION phase"

**Problem**: Session State Phase 1.5 is referenced but not defined. Which PRD owns SKILL_VALIDATION phase implementation?

**Recommendation**:
1. **Session State PRD**: Add **Phase 1.5: Skill Validation Integration (Week 2)** to implementation phases (between Phase 1 and 2)
2. **Skill Catalog PRD**: Reference Session State Phase 1.5 in dependencies (DEP-004)
3. **Both PRDs**: Add joint acceptance criteria: "Session State invokes check_skill_exists, blocks on violations"

**Risk Level**: MEDIUM (integration is desired, but ownership is unclear)

---

#### **GAP B: Agent Orchestration ↔ Session State Integration Timing**

**Agent Orchestration PRD**: Phase 5 (Post-ADR-011) integrates with Session State MCP

**Session State PRD**: Phase 1 (Week 1) delivers core state machine

**Problem**: Agent Orchestration Phase 5 is "Month 3", but Session State Phase 1 is "Week 1". **8-week gap** where Session State exists but Agent Orchestration doesn't integrate.

**Consequence**: Session State can't track agent invocations (primary evidence source) for 2 months after deployment.

**Recommendation**:
1. **Agent Orchestration PRD**: Move Phase 5 (Session State Integration) to **Phase 2** (Week 3, parallel with Handoff Tracking)
2. **Session State PRD**: Add **FR-2.6 (SHOULD)**: "MCP SHOULD provide agent_invocation_hook for external MCPs to record invocations"
3. **Both PRDs**: Add joint integration test in Phase 2: "Agent invocation recorded in Session State"

**Risk Level**: MEDIUM (delayed integration reduces Session State value)

---

#### **GAP C: Validate-SessionEnd.ps1 Coordination**

**Session State PRD**: F5.2 (SHOULD): "MCP SHOULD integrate with Validate-SessionEnd.ps1 (same validation criteria)"

**Agent Orchestration PRD**: Risk 5 mitigation: "Validate-SessionEnd.ps1 checks model usage"

**Problem**: Three systems (Session State MCP, Agent Orchestration MCP, Validate-SessionEnd.ps1) all perform validation, but **no unified validation schema**.

**Consequence**: Duplicate validation logic, drift over time, conflicting results.

**Recommendation**:
1. Create **ADR-014: Unified Validation Schema**:
   - Define canonical validation criteria (git commit, HANDOFF update, markdown lint, skill usage, model selection)
   - Specify which system checks which criteria (e.g., Session State: protocol gates, Skill Catalog: skill usage, Agent Orchestration: model selection)
   - Update Validate-SessionEnd.ps1 to consume MCP outputs (instead of re-implementing checks)
2. **All PRDs**: Reference ADR-014 in dependencies

**Risk Level**: MEDIUM (validation drift is likely, but not blocking)

---

**Rating**: 6/10 - Integration points identified, but coordination gaps exist

---

### 4.2 Implementation Sequencing ⚠️ NEEDS ADJUSTMENT

**Current Proposed Sequence** (from PRDs):

| MCP | Phase 1 Start | Phase 1 Complete | Full Complete |
|-----|---------------|------------------|---------------|
| **Session State** | Week 1 | Week 1 | Week 4 |
| **Skill Catalog** | Week 1 | Week 2 | Week 6 |
| **Agent Orchestration** | Week 1 | Week 2 | Month 3 |

**Dependencies** (from PRDs):

- Agent Orchestration Phase 5 → Session State (exists)
- Skill Catalog Phase 2 → Session State Phase 1.5 (optional)
- Agent Orchestration Phase 4 → Skill Catalog (optional)

**Sequencing Issues**:

#### **ISSUE 1: Parallel Phase 1 Start Creates Risk**

**Problem**: All three MCPs start Week 1, all depend on Serena MCP. **Serena contention risk** (three MCPs writing memories simultaneously).

**Also**: Implementer capacity - can one implementer build three MCPs in parallel? (Estimate: 48-72 hours total for all three Phase 1s)

**Recommendation**:
1. **Sequential Phase 1 starts**:
   - Week 1: **Session State Phase 1** (foundational, no dependencies)
   - Week 2: **Skill Catalog Phase 0-1** (depends on Session State Phase 1.5 in Week 2)
   - Week 3: **Agent Orchestration Phase 1** (depends on Session State for invocation tracking)
2. **Parallel Phase 2+ work** (lower risk, Phase 1 lessons learned)

**Risk Level**: MEDIUM (parallel starts manageable, but sequential reduces risk)

---

#### **ISSUE 2: Session State Phase 1.5 (Skill Validation) Undefined**

**Problem**: Skill Catalog PRD references Session State Phase 1.5, but Session State PRD only defines Phases 1-4.

**Recommendation**: Add Session State Phase 1.5 to implementation phases (see GAP A above).

**Risk Level**: MEDIUM (integration feature is wanted, but not planned)

---

**Recommended Sequencing**:

| Week | Session State | Skill Catalog | Agent Orchestration |
|------|---------------|---------------|---------------------|
| 1 | Phase 1: Core State Machine | - | - |
| 2 | Phase 1.5: Skill Validation + Phase 2 start | Phase 0-1: Index + Search | - |
| 3 | Phase 2: Evidence Automation | Phase 2: Validation Gate | Phase 1: Core Invocation |
| 4 | Phase 3: Cross-Session Context | Phase 3: Usage Tracking | Phase 2: Handoff Tracking + Session State Integration |
| 5-6 | Phase 4: Violation Auditing | Phase 4: Smart Suggestions | Phase 3: Parallel Execution |
| 7-12 | - | - | Phase 4-6: Routing + Analytics |

**Rating**: 6/10 - Sequencing needs adjustment to reduce risk and clarify dependencies

---

### 4.3 Cross-PRD Success Metrics Alignment ✅ CONSISTENT

**Success Metrics Comparison**:

| Metric | Session State Target | Skill Catalog Target | Agent Orchestration Target |
|--------|---------------------|----------------------|---------------------------|
| **Protocol Compliance** | 100% BLOCKING gates | 0 violations/session | 100% sessions tracked |
| **Time Savings** | <5 min protocol overhead | <30s skill discovery | 40% parallel time savings |
| **Context Preservation** | - | - | 95% handoff context |
| **Automation** | 0 manual interventions | 0 violations | 0 HANDOFF conflicts |

**Alignment**: All PRDs target **100% compliance** and **zero manual intervention** - consistent vision.

**No Conflicts**: Success metrics don't overlap (each MCP measures different outcomes).

**Rating**: 10/10 - Excellent alignment

---

## 5. Summary Recommendations

### 5.1 Approval Summary

| PRD | Verdict | Blockers | Confidence |
|-----|---------|----------|------------|
| **Session State MCP** | APPROVE WITH CONDITIONS | 2 blockers | HIGH |
| **Skill Catalog MCP** | APPROVE WITH CONDITIONS | 3 blockers | HIGH |
| **Agent Orchestration MCP** | REQUEST CHANGES | 5 blockers | MEDIUM |

### 5.2 Critical Path to Approval

**For Session State MCP**:
1. ✅ Validate Serena fallback (Phase 1.5 acceptance criteria)
2. ✅ Add integration tests for Serena persistence (Phase 1)

**For Skill Catalog MCP**:
1. ✅ Refine blocking gate to parameter-aware matching (REQ-VALIDATE-007, TECH-019)
2. ✅ Make `replaces_command` REQUIRED (schema validation)
3. ✅ Validate false positive rate <5% (Phase 2 acceptance criteria)

**For Agent Orchestration MCP**:
1. ✅ Add Three-MCP Integration Architecture (Appendix F)
2. ✅ Add HANDOFF.md Migration Plan (Section 13)
3. ✅ Specify parallel timeout behavior (FR-4.8-4.9)
4. ✅ Specify conflict detection algorithm (TECH-020-021)
5. ✅ Add missing risks (token bloat, recursion, deadlock)

**Cross-PRD Coordination**:
1. ✅ Add Session State Phase 1.5 (Skill Validation)
2. ✅ Sequence implementations (Session State → Skill Catalog → Agent Orchestration)
3. ⚠️ Create ADR-014: Unified Validation Schema (recommended, not blocking)

---

### 5.3 Recommended Action Plan

**Immediate Actions** (Before Implementation Starts):

1. **Explainer Agent**: Address Agent Orchestration MCP blockers (5 critical changes)
2. **High-Level-Advisor**: Resolve Agent Orchestration Open Questions Q1-Q7 (routing algorithm, conflict policy, etc.)
3. **Architect**: Create Three-MCP Integration Architecture diagram (Appendix F for Agent Orchestration PRD)
4. **Planner**: Revise implementation sequence (sequential Phase 1 starts, add Session State Phase 1.5)

**Phase 1 Preparation** (Week 1):

1. **Implementer**: Validate Serena fallback for Session State MCP (file-based state recovery)
2. **Implementer**: Add integration tests for all three MCPs (Serena persistence, state recovery)
3. **Security**: Review capability map blocking logic (Skill Catalog MCP parameter-aware matching)

**Phase 2+ Monitoring** (Weeks 2-6):

1. **QA**: Measure false positive rates (Skill Catalog blocking gate)
2. **Analyst**: Measure baseline metrics (handoff context preservation, model selection accuracy)
3. **Retrospective**: Track MCP adoption and effectiveness (for future skill extraction)

---

## 6. Final Recommendations for Roadmap Agent

### 6.1 Prioritization

**Recommended Implementation Order**:

1. **Session State MCP Phase 1** (Week 1) - Foundational, no dependencies, high ROI (100% gate compliance)
2. **Session State MCP Phase 1.5 + Skill Catalog MCP Phase 0-1** (Week 2) - Skill validation is high-value (0 violations)
3. **Skill Catalog MCP Phase 2 + Agent Orchestration MCP Phase 1** (Week 3) - Parallel work, medium risk
4. **All MCPs Phase 2-3** (Weeks 4-6) - Parallel work, integration tests
5. **Agent Orchestration MCP Phase 3-6** (Weeks 7-12) - Advanced features (parallel execution, smart routing)

**Rationale**: Sequential Phase 1 starts reduce Serena contention risk and allow learning from each MCP deployment.

---

### 6.2 Risk Tolerance

**If High Risk Tolerance** (move fast, accept failures):
- Approve all three PRDs with conditions
- Start all three Phase 1s in parallel
- Accept 20-30% chance of integration failures requiring rework

**If Medium Risk Tolerance** (balanced):
- Approve Session State + Skill Catalog PRDs
- Request changes for Agent Orchestration PRD (address 5 blockers)
- Start Session State Phase 1, then Skill Catalog 2 weeks later

**If Low Risk Tolerance** (minimize failures):
- Approve Session State PRD only
- Request changes for Skill Catalog + Agent Orchestration PRDs
- Sequential deployment: Session State → Skill Catalog → Agent Orchestration (12-week timeline)

**Recommended**: **Medium Risk Tolerance** (balanced approach, 6-8 week timeline)

---

### 6.3 Success Criteria for Roadmap

**Three-MCP Strategy is Successful If** (6 months post-launch):

1. ✅ **Session End compliance**: 100% (vs current 4.2%)
2. ✅ **Skill violations**: 0 per session (vs current 5+)
3. ✅ **Parallel execution conflicts**: 0 HANDOFF.md conflicts (vs current 100%)
4. ✅ **Agent invocation type safety**: 100% MCP usage (vs current 0%)
5. ✅ **Manual interventions**: <1 per session (vs current 5+)

**Three-MCP Strategy Fails If**:

1. ❌ Any MCP has <50% adoption (agents bypass MCP tools)
2. ❌ Integration failures between MCPs cause >10% downtime
3. ❌ False positive rate (blocking gates, conflict detection) >20%
4. ❌ Performance regression >1s per agent invocation

---

## 7. Conclusion

All three PRDs demonstrate **strong evidence-based reasoning**, **realistic implementation plans**, and **clear value propositions**. However:

- **Session State MCP**: Ready for implementation with minor fallback validation
- **Skill Catalog MCP**: Ready for implementation with blocking gate refinement
- **Agent Orchestration MCP**: Requires significant specification work (three-MCP coordination, HANDOFF.md transition, timeout behavior, conflict detection algorithm)

**Overall Recommendation**: **Approve Session State + Skill Catalog PRDs**, **request changes for Agent Orchestration PRD**. Start Session State Phase 1 immediately, address Agent Orchestration blockers in parallel, then re-review Agent Orchestration PRD before implementation.

---

**Critic Agent Sign-Off**

**Review Confidence**: HIGH for Session State and Skill Catalog, MEDIUM for Agent Orchestration

**Recommended Next Steps**:
1. Route to **high-level-advisor** for strategic decision on risk tolerance
2. Route to **explainer** to address Agent Orchestration MCP blockers
3. Route to **planner** to finalize implementation sequence
4. Route to **roadmap** to integrate into project plan

**Date**: 2025-12-21
**Reviewer**: Critic Agent (Claude Opus 4.5)

---

*End of Critique*
