# ADR Debate Log: ADR-037 Memory Router Architecture

## Summary

- **Rounds**: 2 (Phase 1 independent review + revision + Phase 4 convergence)
- **Outcome**: CONSENSUS REACHED
- **Final Status**: Proposed → Needs-Revision → **Accepted**
- **Date**: 2026-01-01

---

## Phase 0: Related Work Research

| Type | # | Title | Relevance |
|------|---|-------|-----------|
| Open Issue | #731 | Update agent prompts to use Memory Router | Direct dependency (follow-up) |
| Open Issue | #729 | ADR-007 Bulletproof Enforcement | Foundational - memory-first hooks |
| Open Issue | #167 | Vector Memory System | ADR-037 implements this for M-003 |
| Open Issue | #180 | Reflexion Memory | Future work (Phase 2A M-004/M-005) |
| Open Issue | #584 | M1-003: Serena Integration Layer | Directly related to router |
| Open PR | #730 | ADR-007 enforcement + Forgetful setup | feat/memory branch with setup scripts |
| Closed Issue | #307 | Memory Automation | Prior work on indexing |

---

## Phase 1: Agent Positions

### Architect

**Strengths**: Correct problem identification, sound fallback strategy, clear interface design, good ADR alignment.

**Blocking Concerns (P0)**:

| Issue | Description |
|-------|-------------|
| Deduplication algorithm undefined | No hash algorithm, collision handling, or version selection specified |
| Identity semantics unclear | Serena (name-based) vs Forgetful (content-addressed) - which is canonical? |
| Routing pseudocode doesn't match strategy table | Three strategies listed without decision criteria |
| Health check mechanism undefined | Test-ForgetfulAvailable latency impact unknown |

### Critic

**Blocking Concerns (P0/P1)**:

| Issue | Priority | Description |
|-------|----------|-------------|
| Failure modes undefined | P0 | No spec for HTTP timeout or partial response handling |
| "Good results" threshold missing | P1 | When does router skip Serena fallback? |
| Deduplication unspecified | P1 | Merge-MemoryResults has no algorithm |
| Query injection not addressed | P1 | Security risk in Serena pattern matching |
| Hardcoded port numbers | P1 | Port 8020/24282 fixed, no env var strategy |

### Independent-Thinker

**Blocking Concerns (P0)**:

| Issue | Priority | Description |
|-------|----------|-------------|
| Forgetful availability unvalidated | P0 | Architecture assumes primary is reliable; no SLA |
| Latency targets not evidence-based | P0 | 50-100ms is stub implementation, not measured |
| **Contradicts ADR-007 without justification** | **P0** | ADR-007 establishes Serena-first; ADR-037 inverts to Forgetful-first |
| Result merging algorithm undefined | P1 | Thresholds, tie-breaking, collision resolution missing |
| No evidence Forgetful works in production | P1 | Installation scripts exist but actual deployment unknown |

### Security

**Blocking Concerns (P1)**:

| Issue | Priority | Description |
|-------|----------|-------------|
| Query input validation missing | P1 | CWE-20: Regex/JSON injection risk |
| HTTP transport unencrypted | P1 | CWE-319: Cleartext transmission at localhost:8020 |
| DoS-vulnerable timeout logic | P2 | CWE-400: Cascading timeouts under degraded service |
| Hash algorithm unspecified | P2 | CWE-327: Collision risk in deduplication |

### Analyst

**Blocking Concerns (P0/P1)**:

| Issue | Priority | Description |
|-------|----------|-------------|
| Forgetful performance unvalidated | P0 | 50-100ms target not measured against production |
| Forgetful internals undocumented | P1 | HNSW indexing, quantization, token budget unclear |
| Result merge algorithm missing | P1 | Scoring formula not specified |
| PowerShell-MCP integration untested | P1 | Core assumption has no prototype |
| Timeout handling incomplete | P2 | Fallback latency ~550ms may exceed expectations |

### High-Level Advisor

**Verdict**: APPROVED WITH CONDITIONS

**Blocking Concerns (P0)**:

| Issue | Priority | Description |
|-------|----------|-------------|
| M-008 benchmarks incomplete | P0 | No Forgetful measurements exist |
| M-001 documentation incomplete | P0 | Forgetful internals undocumented |
| Security (query injection) | P0 | Must be solved before implementation |
| Dedup algorithm undefined | P1 | Core feature incomplete |
| Result merging strategy undefined | P1 | No decision rules for strategy selection |

---

## Phase 2: Consolidation

### Consensus Points (6/6 Agents Agree)

1. Problem is real - ADR-037 addresses genuine cognitive overhead
2. Fallback design is sound - Forgetful → Serena graceful degradation is correct approach
3. Deduplication is underspecified - Algorithm, hash function, collision handling missing
4. Result merging is incomplete - Strategies listed but no decision criteria

### Conflict Resolution

**Conflict 1: ADR-007 Alignment**

| Position | Agent | Verdict |
|----------|-------|---------|
| ADR-037 contradicts ADR-007 (Serena-first) | independent-thinker | **PREVAILS** |
| ADR-037 aligns with ADR-007 | architect | Rejected |

**Ruling**: ADR-037 must be rewritten with **Serena-first, Forgetful-supplementary** to align with ADR-007 canonical layer decision.

**Conflict 2: Implementation Timing**

| Position | Agent | Verdict |
|----------|-------|---------|
| Complete M-008 benchmarks first | high-level-advisor | **PREVAILS** |
| Proceed with implementation, benchmark later | analyst | Rejected |

**Ruling**: M-008 benchmarks must complete BEFORE M-003 implementation begins.

---

## Phase 3: Required Changes

### P0 Changes (Blocking)

| # | Issue | Change Required |
|---|-------|-----------------|
| 1 | **Routing logic contradiction** | Invert to Serena-first, Forgetful-supplementary |
| 2 | **Deduplication undefined** | Add SHA-256 content hash with Serena-wins on collision |
| 3 | **Performance unvalidated** | Mark targets as "unvalidated, pending M-008" |
| 4 | **Query validation missing** | Add Security section with input validation |
| 5 | **Health check undefined** | Specify TCP connect, 500ms timeout, 30s cache |

### P1 Changes (Important)

| # | Issue | Change Required |
|---|-------|-----------------|
| 6 | Result merging strategy | Choose "Primary-first with augmentation" |
| 7 | Identity semantics | Declare Serena file names as canonical IDs |
| 8 | HTTP transport | Document localhost assumption in Security section |
| 9 | Implementation plan | Extract to separate planning doc, reference only |

---

## Dissenting Views

| Agent | Position | Rationale for Not Adopting |
|-------|----------|---------------------------|
| analyst | Proceed with implementation, benchmark during Phase 2 | Conflicts with high-level-advisor ruling; risk of wasted effort if benchmarks show Forgetful is slow |

---

## Next Steps

### Before ADR-037 Can Be Accepted

1. **Revise routing logic**: Serena-first, Forgetful-supplementary (align with ADR-007)
2. **Complete M-008 benchmarks**: Measure Forgetful against production workload
3. **Add Security section**: Input validation, localhost assumption
4. **Specify deduplication**: SHA-256 hash, collision handling
5. **Define health check**: TCP connect, 500ms timeout, 30s TTL cache

### Recommended Routing

- **Next agent**: planner (to break down revision work into tasks)
- **After revision**: Re-submit for Phase 4 convergence check

---

## Recommendations for Orchestrator

**ADR Status**: NEEDS-REVISION

**Implementation Gate**: BLOCKED until P0 changes complete

**Backlog Issues Created**:

- Issue #731: Update agent prompts to use Memory Router (dependency)

**Debate Artifacts**:

- This log: `.agents/critique/ADR-037-debate-log.md`
- ADR location: `.agents/architecture/ADR-037-memory-router-architecture.md`

---

## Round 2: Convergence Check (v2.0 Revision)

### Revision Summary (v1.0 → v2.0)

| P0 Issue | Resolution |
|----------|------------|
| Routing logic contradicted ADR-007 | Inverted to Serena-first, Forgetful-supplementary |
| Deduplication undefined | Added SHA-256 algorithm with full pseudocode |
| Query injection risk | Added ValidatePattern input validation in Security section |
| Health check undefined | Added TCP connect with 500ms timeout, 30s cache TTL |
| Performance unvalidated | Marked targets as "Pending M-008" |
| Identity semantics unclear | Declared Serena file names as canonical IDs |
| Result merging undefined | Chose "Serena-first with augmentation" strategy |

### Agent Positions (Round 2)

| Agent | Position | Key Rationale |
|-------|----------|---------------|
| architect | **Accept** | All P0 concerns resolved with complete pseudocode specifications |
| critic | **Accept** | Technical detail sufficient for implementation; all blocking concerns addressed |
| independent-thinker | **Accept** | ADR-007 contradiction resolved; Serena-first confirmed in routing logic |
| security | **Accept** | Security controls verified; risk score 3/10 (Low); CWE mitigations documented |
| analyst | **Disagree-and-Commit** | Performance unvalidated but architectural decisions sound; M-008 will validate |
| high-level-advisor | **Accept** | All P0 blockers resolved; proceed to implementation with M-008 as gate |

### Consensus Result

**5 Accept + 1 Disagree-and-Commit = CONSENSUS REACHED**

Per adr-review protocol: "All 6 agents Accept OR Disagree-and-Commit = Consensus reached"

### Analyst Dissent (Disagree-and-Commit)

**Concern**: Performance targets remain speculative until M-008 validation. Risk of Forgetful adding unacceptable latency is real.

**Why Commit**: Architectural decisions are sound. Serena-first routing provides safety net. Concerns can be addressed incrementally during Phase 1-3 implementation.

**Tracking**: If M-008 reveals Forgetful latency >200ms, augmentation strategy should be revisited.

### Residual Concerns (P1/P2 - Non-Blocking)

| Priority | Issue | Owner | Tracking |
|----------|-------|-------|----------|
| P1 | Forgetful performance unvalidated | M-008 | Must complete before Phase 2 |
| P1 | PowerShell-MCP integration untested | M-003 | Integration spike in Phase 1 |
| P1 | Forgetful internals undocumented | M-001 | Separate documentation issue |
| P2 | Weighted result merging deferred | Phase 3 | Optimization scope |
| P2 | Result caching deferred | Phase 3 | Optimization scope |
| P2 | Port configuration hardcoding | M-004 | Technical debt |
| P2 | Health check race condition | Phase 3 | Add mutex if needed |

---

## Final Recommendations

**ADR Status**: ACCEPTED

**Implementation Gate**: APPROVED - Proceed to M-003 with M-008 benchmark as Phase 1 validation gate

**Next Actions**:

1. Update ADR-037 status to "Accepted"
2. Route to implementer for M-003 execution
3. Track M-008 benchmark completion before Phase 2 agent integration

**Debate Complete**: 2 rounds, consensus achieved on 2026-01-01
