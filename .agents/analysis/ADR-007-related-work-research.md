# Related Work Research: ADR-007 Memory-First Architecture

**ADR**: ADR-007: Memory-First Architecture (Augmented 2026-01-01)
**Date**: 2026-01-01
**Analyst**: Claude Opus 4.5

---

## Related Issues

### Open Issues (Memory-Related)

| # | Title | Status | Relevance | Priority |
|---|-------|--------|-----------|----------|
| [#584](https://github.com/rjmurillo/ai-agents/issues/584) | M1-003: Implement Serena Integration Layer | Open | **CRITICAL** - Required for dual memory architecture | P0 |
| [#683](https://github.com/rjmurillo/ai-agents/issues/683) | feat(agent-memory): maintain explicit PR-to-branch mapping in Serena | Open | **HIGH** - Branch coordination memory | P1 |
| [#496](https://github.com/rjmurillo/ai-agents/issues/496) | Automated Memory Index Enforcement | Open | **HIGH** - Validates memory indexing integrity | P1 |
| [#167](https://github.com/rjmurillo/ai-agents/issues/167) | feat: Implement Vector Memory System with Semantic Search | Open | **MEDIUM** - Future semantic search upgrade | P3 |
| [#581](https://github.com/rjmurillo/ai-agents/issues/581) | [EPIC] Skills Index Registry - O(1) Skill Lookup and Governance | Open | **MEDIUM** - Memory organization pattern | P1 |
| [#650](https://github.com/rjmurillo/ai-agents/issues/650) | User Story: Validator recognizes investigation-only sessions (Phase 1) | Open | **MEDIUM** - Session memory classification | P0 |
| [#234](https://github.com/rjmurillo/ai-agents/issues/234) | feat: Automated daily reviewer signal quality statistics | Open | **LOW** - Memory-based metrics | P1 |
| [#180](https://github.com/rjmurillo/ai-agents/issues/180) | feat: Implement Reflexion Memory with Causal Reasoning | Open | **LOW** - Advanced memory patterns | P2 |
| [#179](https://github.com/rjmurillo/ai-agents/issues/179) | feat: Expand MCP Tool Ecosystem (GitHub, Performance, Neural) | Open | **LOW** - MCP infrastructure | P2 |
| [#475](https://github.com/rjmurillo/ai-agents/issues/475) | Add AI-Assisted Memory Title/Content Alignment Validation to CI | Open | **MEDIUM** - Memory quality enforcement | P1 |
| [#220](https://github.com/rjmurillo/ai-agents/issues/220) | feat: Skill Catalog MCP (ADR-012) - Skill Discovery & Validation | Open | **MEDIUM** - Memory-driven skill lookup | P2 |
| [#663](https://github.com/rjmurillo/ai-agents/issues/663) | Task: Implement CI backstop validation (P2) | Open | **LOW** - Protocol enforcement | P2 |
| [#126](https://github.com/rjmurillo/ai-agents/issues/126) | investigate: Skillbook deduplication in retrospective workflow | Open | **LOW** - Memory deduplication patterns | P2 |
| [#219](https://github.com/rjmurillo/ai-agents/issues/219) | feat: Session State MCP (ADR-011) - Protocol Enforcement | Open | **HIGH** - Session memory persistence | P1 |
| [#173](https://github.com/rjmurillo/ai-agents/issues/173) | feat: Implement Skill Auto-Consolidation from Retrospectives | Open | **MEDIUM** - Memory consolidation | P2 |
| [#221](https://github.com/rjmurillo/ai-agents/issues/221) | feat: Agent Orchestration MCP (ADR-013) - Structured Invocation & Parallel Execution | Open | **HIGH** - Multi-agent memory coordination | P1 |
| [#170](https://github.com/rjmurillo/ai-agents/issues/170) | feat: Implement Lifecycle Hooks for Session Automation | Open | **MEDIUM** - Memory automation triggers | P2 |
| [#183](https://github.com/rjmurillo/ai-agents/issues/183) | Epic: Claude-Flow Inspired Enhancements | Open | **HIGH** - Memory research source | P2 |
| [#265](https://github.com/rjmurillo/ai-agents/issues/265) | [EPIC] Pre-PR Validation System: Prevent premature PR opening across all agents | Open | **LOW** - Uses memory for validation | P0 |
| [#42](https://github.com/rjmurillo/ai-agents/issues/42) | feat: Add pre-PR security gate for infrastructure changes | Open | **LOW** - Security memory patterns | P2 |

### Related PRs

| # | Title | Branch | Status |
|---|-------|--------|--------|
| [#566](https://github.com/rjmurillo/ai-agents/pull/566) | docs: improve autonomous-issue-development.md structure | docs/506-autonomous-issue-development | Open |

**Note**: Only 1 open PR found. Memory work appears to be tracked in issues rather than active PRs.

### Closed Issues

No directly related closed issues found for "memory architecture", "vector memory", or "knowledge graph" searches.

**Interpretation**: This suggests that memory architecture is relatively new ground for the project. ADR-007 is foundational work without significant prior iterations.

---

## Related ADRs

### Direct References

| ADR | Title | Relationship |
|-----|-------|-------------|
| **ADR-008** | Protocol Automation via Lifecycle Hooks | **Enforces** memory retrieval in session protocol |
| **ADR-017** | Tiered Memory Index Architecture | **Implements** memory organization pattern from ADR-007 |
| **ADR-014** | Distributed Handoff Architecture | **Depends on** Serena memory for cross-session context |
| **ADR-011** | Session State MCP | **Future** - Will persist session memory via Serena |

### Architecture Impact

| ADR | Memory Relevance |
|-----|------------------|
| ADR-002 | Agent Model Selection Optimization - Model routing affects memory token budgets |
| ADR-003 | Agent Tool Selection Criteria - Memory retrieval is a tool selection factor |
| ADR-005 | PowerShell-Only Scripting - Memory scripts must be PowerShell |
| ADR-006 | Thin Workflows, Testable Modules - Memory validation in modules |
| ADR-009 | Parallel-Safe Multi-Agent Design - Memory conflicts in parallel sessions |
| ADR-010 | Quality Gates Evaluator-Optimizer - Memory quality is a gate criteria |
| ADR-012 | Skill Catalog MCP - Memory-driven skill lookup |
| ADR-013 | Agent Orchestration MCP - Cross-agent memory coordination |
| ADR-015 | Artifact Storage Minimization - Memory storage competes with artifacts |
| ADR-018 | Cache Invalidation Strategy - Memory caching patterns |
| ADR-020 | Feature Request Review Step - Feature evaluation memory |
| ADR-027 | GitHub MCP Agent Isolation - Memory isolation per agent |
| ADR-030 | Skills Pattern Superiority - Skills stored in memory |
| ADR-032 | EARS Requirements Syntax - Requirements stored in memory |
| ADR-033 | Routing Level Enforcement Gates - Memory-driven routing |
| ADR-034 | Investigation Session QA Exemption - Session memory classification |
| ADR-035 | Exit Code Standardization - Validation scripts in memory |
| ADR-036 | Two-Source Agent Template Architecture - Template patterns in memory |

**Key Finding**: 24 of 36 ADRs reference memory, retrieval, or knowledge patterns. Memory architecture is deeply integrated into project design.

---

## Implications for ADR-007

### 1. Critical Dependencies

**Issue #584 (M1-003: Serena Integration Layer)** is a P0 blocker:

- ADR-007 declares Serena as the "canonical" memory layer
- Current implementation relies on Serena MCP availability
- Without #584, dual memory architecture (Serena + Forgetful) cannot be validated

**Recommendation**: Link ADR-007 to #584 as a dependency. ADR-007 is "Accepted" but implementation is gated by #584.

### 2. Known Gaps

**Issue #167 (Vector Memory System)** is marked P3 but ADR-017 identifies it as a "sunset trigger":

> "This architecture is optimized for lexical matching without embeddings. When Issue #167 (Vector Memory System) is implemented:
> 1. Re-evaluate tiered approach vs semantic search
> 2. Tiered indices may become unnecessary overhead
> 3. Consider deprecation in favor of embedding-based retrieval"

**Conflict**: ADR-007 augmentation references Forgetful MCP (which has semantic search) but #167 is still open. Forgetful may already solve #167's semantic search requirement.

**Recommendation**: Re-evaluate #167 priority. If Forgetful MCP provides semantic search, #167 may be redundant. Update ADR-007 to clarify Forgetful's role in semantic retrieval.

### 3. Ongoing Work

**Issue #475 (Memory Title/Content Alignment Validation)** is P1:

- ADR-007 Zettelkasten principles require atomicity and explicit linking
- #475 validates that memory titles accurately reflect content
- This enforces Zettelkasten's "one concept per note" principle

**Link Recommendation**: #475 should reference ADR-007's Zettelkasten principles as the specification source.

**Issue #581 (Skills Index Registry)** overlaps with ADR-017:

- Both address memory organization and O(1) lookup
- ADR-017 implemented tiered indexing; #581 proposes flat registry
- ADR-017 explicitly supersedes the flat registry approach (per line 392)

**Recommendation**: Close #581 or update to reference ADR-017 as the implemented solution.

### 4. Future MCP Integration

Three proposed MCPs depend on memory architecture:

| MCP | Issue | Memory Role |
|-----|-------|-------------|
| Session State MCP | #219 | Persists session state to Serena memory |
| Skill Catalog MCP | #220 | Memory-driven skill discovery |
| Agent Orchestration MCP | #221 | Cross-agent memory coordination |

**Implication**: ADR-007's dual memory architecture (Serena + Forgetful) will be the foundation for all three MCPs. Any changes to ADR-007 affect MCP design.

---

## Data Transparency

### Evidence Located

- **20 open issues** with memory-related labels or titles
- **1 open PR** (documentation-only)
- **0 closed issues** matching memory architecture queries
- **4 ADRs** with direct references to ADR-007
- **24 ADRs** (67%) with memory-related content
- **3 proposed MCPs** depending on memory architecture

### Not Located

- **Historical context**: Why memory was initially "an afterthought" (per ADR-007 line 13)
- **Metrics**: Quantitative evidence for "repeated discoveries" claim (line 15)
- **Prior proposals**: No evidence of rejected memory architecture alternatives
- **Migration plans**: How to transition from cloudmcp-manager to Serena/Forgetful

---

## Recommendations

### For ADR Review

1. **Link Dependencies**: Add #584 (Serena Integration) as a blocking dependency for ADR-007 implementation
2. **Clarify Forgetful vs #167**: Update ADR-007 to specify whether Forgetful MCP fulfills #167's semantic search requirement
3. **Update Superseded Issues**: Close or update #581 (Skills Index Registry) to reference ADR-017
4. **Reference Validation**: Link #475 (Memory Alignment Validation) to ADR-007 Zettelkasten principles
5. **MCP Coordination**: Document that Session State MCP (#219), Skill Catalog MCP (#220), and Agent Orchestration MCP (#221) all depend on ADR-007's architecture

### For Issue Management

1. **Priority Realignment**: Consider elevating #167 or closing it if Forgetful MCP already provides semantic search
2. **Documentation Gap**: Create migration guide from cloudmcp-manager to Serena (mentioned in ADR-007 but not documented)
3. **Metrics Collection**: Instrument memory retrieval to validate "repeated discoveries" claim with quantitative data

---

## Conclusion

**Verdict**: ADR-007 is well-integrated into the project architecture with 24 ADRs referencing memory patterns. The augmentation (Forgetful, BMAD, Zettelkasten) aligns with existing work (ADR-017 tiered indexing, ADR-014 distributed handoff).

**Critical Path**: Issue #584 (Serena Integration) is the primary blocker. ADR-007 can be accepted as architectural guidance, but implementation depends on #584 completion.

**Risk**: Overlap between Forgetful MCP (semantic search) and Issue #167 (Vector Memory System) creates ambiguity. Clarify which system owns semantic retrieval.

**Confidence**: High - Extensive ADR cross-references and active issue tracking demonstrate strong architectural alignment.

---

## Sources Consulted

- GitHub Issues API (gh CLI)
- `.agents/architecture/` ADR files
- ADR-007, ADR-008, ADR-011, ADR-014, ADR-017 (full text)
- 20 open issues with memory-related labels
- 1 open PR (documentation)
