# ADR-037: Memory Router Architecture - Phase 1 Review

**Reviewer**: Architect
**Review Date**: 2026-01-01
**ADR**: ADR-037 (Proposed)
**Phase**: Phase 1 - Independent Review
**Status**: [BLOCKING ISSUES IDENTIFIED]

---

## Executive Summary

ADR-037 proposes a unified memory access layer (Memory Router) that abstracts Forgetful (semantic search) and Serena (lexical search) behind a single PowerShell interface. The decision is **architecturally sound** but has **4 blocking concerns** that must be resolved before proceeding to multi-agent debate (Phase 2).

**Recommendation**: Return to Session 123 with blocking issues. After resolution, escalate to adr-review skill for Phase 2 multi-agent consensus.

---

## Architect Review

### Strengths

1. **Correct Problem Identification**: The ADR accurately identifies real cognitive overhead—agents currently must know which memory system to query and handle fallback logic themselves. This violates ADR-007 (Memory-First Architecture) by adding retrieval complexity.

2. **Sound Fallback Architecture**: The fallback chain (Forgetful → Serena) with graceful degradation is architecturally correct. Services fail; fallback mechanisms prevent total memory unavailability.

3. **Clear Interface Design**: The proposed `Search-Memory` / `Get-Memory` / `Save-Memory` interface is intuitive and language-agnostic. Good PowerShell naming conventions.

4. **Alignment with Existing Decisions**:
   - ADR-007 (Memory-First) mandates retrieval before reasoning → Router simplifies this
   - ADR-017 (Tiered Index) provides Serena optimization → Router leverages this
   - memory-architecture-serena-primary recognizes Serena as canonical → Router respects this

5. **Performance Targets Realistic**: 50-100ms (Forgetful primary) vs 530ms baseline shows meaningful improvement while acknowledging fallback cost (550ms after timeout).

### Weaknesses / Gaps

#### Gap 1: Missing Deduplication Strategy [BLOCKING]

**Problem**: The ADR lists "Result Merging: Deduplicate and rank results from multiple sources" as a design requirement but provides **zero implementation detail** for deduplication.

**Quote from ADR-037**:
```
3. **Result Merging**: Deduplicate and rank results from multiple sources
```

**Question**: How is deduplication performed?
- By memory ID? (But Serena uses file names, Forgetful uses auto-generated IDs)
- By content hash? (Added CPU cost, implementation burden)
- By fuzzy matching? (High false positive risk)
- By semantic similarity threshold? (Requires embeddings logic)

**Impact**: Without deduplication strategy, Union merges will return duplicate results under different IDs, wasting tokens and confusing agents. Primary-first strategy avoids this but then provides no benefit over Forgetful-only (except fallback).

**Current text** in ADR is insufficient:
```powershell
$results = Merge-MemoryResults -Primary $results -Secondary $serenaResults
```

**This is pseudocode, not a decision.** The actual deduplication logic must be specified.

**Recommendation**: Add explicit deduplication algorithm to Result Merging Strategy section before Phase 2.

---

#### Gap 2: Content-Addressed Lookup vs Name-Based Lookup [BLOCKING]

**Problem**: ADR-037 conflates two different lookup semantics without acknowledging the architectural tension.

**Current state**:
- **Serena**: Lexical search over markdown files → Returns file names (IDs are paths)
- **Forgetful**: Semantic search via embeddings → Returns observation IDs (auto-generated UUIDs)

**The Gap**: When merging results, what is the "identity" of a memory?

Example scenario:
1. Agent calls `Search-Memory -Query "PowerShell array handling"`
2. Forgetful returns: observation ID `abc-123`, title "PowerShell Array Pitfalls", score 0.92
3. Serena returns: file `powershell-array-handling.md`, title "PowerShell Array Handling", score 0.95 (keyword match)

Are these the same memory or different? **ADR-037 doesn't say.**

**Architectural tension**:
- Serena is name-based (file identity persists across sessions)
- Forgetful is content-addressed (observation ID is stable but database-local)

**Quote from memory-architecture-serena-primary**:
> "Forgetful and claude-mem tools may be available on hosted platforms, but **the database contents are not**. Only Serena memories travel with the repository."

**This means**: When Forgetful IDs are returned, there's no guarantee those IDs will be valid in the next platform/VM. Agents MUST have a fallback strategy to Serena file names.

**Recommendation**: Clarify whether Router returns:
- Option A: Only Serena file names (Forgetful results translated to Serena lookups)
- Option B: Mixed IDs (Forgetful observation IDs + Serena file names) with caveats about platform portability
- Option C: Content-addressed fallback (if Forgetful ID not available on new platform, re-retrieve via Serena)

---

#### Gap 3: Routing Logic Doesn't Match Result Merging Strategy [BLOCKING]

**Problem**: The pseudocode routing logic doesn't align with the documented merging strategies.

**Routing pseudocode** (lines 71-95):
```powershell
if (-not $ForceSerena -and $forgetfulAvailable) {
    $results = Invoke-ForgetfulSearch -Query $Query -Limit $MaxResults
}

if ($results.Count -eq 0 -or $ForceSerena) {
    $serenaResults = Invoke-SerenaSearch -Query $Query -Limit $MaxResults
    $results = Merge-MemoryResults -Primary $results -Secondary $serenaResults
}
```

**Issue**: This implements **Primary-first IF empty** strategy:
- Query Forgetful first
- Only query Serena if Forgetful returns 0 results OR if forced

**But the documented strategies** (table on line 100-104) say:
- **Primary-first**: Return Forgetful results, skip Serena
- **Union**: Combine both, deduplicate
- **Weighted**: Score by semantic similarity + recency

**Which strategy should be used?** The pseudocode picks "Primary-first IF empty" but the table doesn't list this as an option. What about cases where:
- Forgetful returns 3 results with scores 0.65-0.75 (marginal relevance)
- Serena likely has better keyword matches

Should the router query Serena anyway? When should Union be used?

**Recommendation**: Match routing pseudocode to documented strategies OR update strategy table to reflect actual implementation choice.

---

#### Gap 4: Availability Detection Not Specified [BLOCKING]

**Problem**: The ADR repeatedly mentions "Availability Detection: Automatic routing based on system health" (line 41, 145) but provides **zero implementation detail**.

**Questions**:
- How is Forgetful availability tested? HTTP HEAD to port 8020?
- What's the timeout? 100ms? 500ms? (Critical for 50ms latency target)
- What if Forgetful is slow (5s response time)? Fall back immediately or wait?
- Is availability cached per-session or checked per-call?
- If unavailable in session initialization, does router skip health checks for entire session?

**Impact on Performance Targets**:
- If health check is 100ms and Forgetful returns 50ms results, net is 150ms
- Target says "50-100ms (Forgetful primary)" but doesn't account for health check cost

**Code references health check**:
```powershell
$forgetfulAvailable = Test-ForgetfulAvailable
```

**But `Test-ForgetfulAvailable` is not specified.** Is it:
- `Test-Path` to port 8020?
- HTTP timeout?
- MCP tool invocation?

**Recommendation**: Specify health check mechanism and confirm it doesn't undermine the 50-100ms target.

---

## Scope Concerns

### Scope Concern 1: Is This an Architectural Decision or an Implementation Plan?

**Tension**: ADR-037 reads as a **partial implementation plan** more than an architectural decision.

**Evidence**:
- Lines 152-177: Multi-phase implementation plan (phases 1-3)
- Lines 198-204: Performance targets (metric table)
- Lines 71-95: Pseudocode for routing logic

**Problem**: An ADR should capture the **decision** (unified interface, fallback strategy) but execution details (which phase, which scripts, performance metrics) belong in implementation plans, not the ADR.

**MADR 4.0 expectation**: ADRs document:
- Context and drivers
- Decision and rationale
- Consequences and confirmation

**MADR 4.0 anti-pattern**: ADRs that contain implementation plans (which scripts to create, which phases, which metrics).

**Recommendation**: Extract Implementation Plan (lines 151-177) to `.agents/planning/PLAN-memory-router-*.md`. Keep ADR focused on the architectural decision:
- What interface do agents see? (KEEP)
- What's the fallback strategy? (KEEP)
- How does it integrate with ADR-007 and ADR-017? (KEEP)
- Phase 1 creates MemoryRouter.psm1? (MOVE to plan)
- Performance targets? (MOVE to acceptance criteria in plan)

---

### Scope Concern 2: Integration with ADR-013 Not Addressed

**Context**: ADR-013 (Agent Orchestration MCP) proposes structured agent invocation via a future Agent Orchestration MCP.

**Gap**: ADR-037 makes Memory Router a PowerShell module (`scripts/MemoryRouter.psm1`) but ADR-013 would eventually make agent coordination MCP-based. These architectures may conflict.

**Scenarios**:
1. **Today**: Memory Router is PowerShell module, agents call `Search-Memory` directly
2. **Future (ADR-013)**: Agent Orchestration MCP manages memory access, agents call `invoke_agent(...)`

**Question**: Does ADR-037 preclude ADR-013? Or will ADR-013 wrap the Memory Router?

**Recommendation**: Add section clarifying relationship to future orchestration MCP. Ensure this doesn't create coupling that makes ADR-013 harder to implement.

---

## Questions for Session 123 (Pre-Phase 2)

### Q1: Deduplication (Gap 1)

How should Memory Router deduplicate results when merging Forgetful + Serena?

- Option A: By content hash (cost: ~10-50ms SHA256 per result)
- Option B: By semantic similarity threshold (cost: embedding model inference)
- Option C: Don't deduplicate; let agents handle duplicates
- Option D: Only merge if Forgetful returns sparse results (<3 matches)

**Why this matters**: Union strategy is only viable if dedup cost is <10ms/result.

---

### Q2: Identity Semantics (Gap 2)

When Memory Router returns results, what is the "ID" of a memory?

- Option A: Serena file name (platform-portable, canonical per ADR-007)
- Option B: Forgetful observation ID (semantic but database-local, not portable)
- Option C: Mixed IDs with explicit fallback rules

**Recommendation**: Enforce Option A (Serena names as canonical) to respect memory-architecture-serena-primary memory and ensure cross-platform portability.

---

### Q3: Routing Strategy (Gap 3)

Which result merging strategy is actually chosen for the first implementation?

Current options in ADR:
1. **Primary-first**: Always return Forgetful if available (cheapest, least thorough)
2. **Union**: Always query both and merge (most thorough, most expensive)
3. **Weighted**: Query both and rank by composite score (balanced)
4. **Primary-first IF empty**: Current pseudocode (hybrid, undefined criteria)

**Recommendation**: Choose one explicitly and implement that pseudocode.

---

### Q4: Health Check Mechanism (Gap 4)

How will `Test-ForgetfulAvailable` detect Forgetful availability without exceeding 50-100ms latency budget?

- Option A: TCP connect test to port 8020 (fast, ~10ms)
- Option B: HTTP HEAD request (slower, ~50-100ms)
- Option C: Cache availability flag for entire session (fast, potentially stale)
- Option D: Inline: "Try Forgetful, fall back if timeout"

**Recommendation**: Test-ForgetfulAvailable should be a fast connectivity check (<10ms), not a full health probe. Real errors (timeout, connection refused) are caught inline.

---

## Blocking Concerns Table

| ID | Concern | Category | Priority | Impact | Resolution |
|----|---------|----------|----------|--------|------------|
| **1** | Deduplication algorithm not specified | Design Gap | **P0** | Union strategy is unusable without explicit dedup logic | Specify algorithm in Result Merging Strategy table |
| **2** | Content vs Name-based identity not clarified | Architectural Tension | **P0** | Cross-platform portability broken if Forgetful IDs used as primary | Clarify that Serena names are canonical IDs; Forgetful IDs are supplementary |
| **3** | Routing pseudocode doesn't match strategies table | Logic Error | **P0** | Ambiguity about which strategy is implemented | Align pseudocode to single chosen strategy OR expand strategies table |
| **4** | Availability detection mechanism not specified | Implementation Gap | **P0** | Health check cost could undermine latency targets; blocking issue if check is expensive | Specify `Test-ForgetfulAvailable` implementation (TCP? HTTP? Session-cached?) |
| **5** | Implementation plan in ADR scope creep | Pattern Violation | **P1** | Conflates decision with execution; adds maintenance burden as plan changes | Extract Implementation Plan section to planning document |
| **6** | Integration with ADR-013 not addressed | Coordination Gap | **P1** | Future Agent Orchestration MCP may conflict with current PowerShell module approach | Add integration clarification or dependency note |

---

## Alignment with Architectural Principles

| Principle | Status | Notes |
|-----------|--------|-------|
| **Consistency** | ✅ PASS | Follows PowerShell naming conventions; aligns with ADR-007 and ADR-017 |
| **Simplicity** | ⚠️ CONDITIONAL | Simplified for agents (good) but complex routing logic (concern) |
| **Testability** | ⚠️ UNCERTAIN | Unit test approach not specified; mock servers mentioned but strategy missing |
| **Extensibility** | ✅ PASS | Can add more backends without changing agent code (good) |
| **Separation** | ⚠️ CONDITIONAL | Router adds abstraction layer (good) but hides complexity (concern) |

---

## MADR 4.0 Compliance Checklist

| Criterion | Status | Notes |
|-----------|--------|-------|
| **Context statement** | ✅ PASS | Clear problem statement: cognitive overhead of dual memory systems |
| **Decision drivers listed** | ✅ PASS | Implicit: simplify agent logic, graceful degradation, semantic search |
| **Alternatives considered** | ✅ PASS | 3 alternatives listed (Forgetful-only, Serena+embedding, dual-query) |
| **Decision outcome explicit** | ✅ PASS | "Implement Memory Router with fallback chain" |
| **Consequences balanced** | ✅ PASS | Lists positive, negative, neutral consequences |
| **Confirmation method** | ⚠️ WEAK | Section 218-224 says "Review" but doesn't specify how to verify router behavior |
| **Reversibility assessed** | ❌ MISSING | No rollback strategy if router fails; no abort criteria |

---

## Pre-Phase 2 Checklist

**MANDATORY before escalating to adr-review skill (Phase 2 multi-agent debate)**:

- [ ] **Gap 1**: Add explicit deduplication algorithm to Result Merging Strategy section
- [ ] **Gap 2**: Clarify identity semantics (Serena names as canonical per memory-architecture-serena-primary)
- [ ] **Gap 3**: Align routing pseudocode to single chosen merging strategy
- [ ] **Gap 4**: Specify `Test-ForgetfulAvailable` mechanism and latency impact
- [ ] **Scope 1**: Extract Implementation Plan (lines 151-177) to planning document
- [ ] **MADR Compliance**: Add Reversibility Assessment section (rollback approach, abort criteria)
- [ ] **Confirmation**: Specify how to verify router is functioning correctly (logging? metrics?)

---

## Recommended Next Steps

1. **Session 123 Revision**: Address all P0 blocking concerns above
2. **Updated ADR**: Resubmit ADR-037 with gaps filled
3. **Phase 2 Escalation**: Once blocking issues resolved, invoke adr-review skill:
   ```bash
   Skill(skill="adr-review", args=".agents/architecture/ADR-037-memory-router-architecture.md")
   ```
4. **Multi-Agent Debate**: Critic, Security, Analyst, Independent-Thinker will validate
5. **Phase 3 Finalization**: User approval + status update to Accepted

---

## Architecture Pattern Library References

This ADR builds on established patterns:

| Pattern | Source | Relevance |
|---------|--------|-----------|
| Fallback chain | Resilience patterns | Graceful degradation ✅ |
| Unified interface | Facade pattern | Simplify client code ✅ |
| Availability detection | Circuit breaker | Health checks ⚠️ (mechanism missing) |
| Content deduplication | Data integration | Result merging ⚠️ (algorithm missing) |
| Semantic search abstraction | Search patterns | Forgetful integration ✅ |

---

## Conclusion

**ADR-037 is architecturally sound but incomplete.** The core decision (unified interface + fallback strategy) is solid and aligns with ADR-007, ADR-017, and memory-architecture-serena-primary. However, **4 blocking design gaps** must be resolved before proceeding to multi-agent debate:

1. **Deduplication algorithm** (Gap 1)
2. **Identity semantics clarification** (Gap 2)
3. **Routing strategy alignment** (Gap 3)
4. **Health check mechanism** (Gap 4)

Once resolved, ADR-037 is ready for Phase 2 multi-agent consensus validation.

---

**Review Date**: 2026-01-01
**Reviewer**: Architect Agent
**Next Step**: Return to Session 123 for blocking issue resolution
**Escalation Path**: adr-review skill (Phase 2 multi-agent debate)
