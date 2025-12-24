# Session 87: ADR-017 Analyst Review (Model Routing Policy)

**Date**: 2025-12-23
**Agent**: analyst
**Task**: Comprehensive analyst review of ADR-017 (Copilot model routing policy optimized for low false PASS)
**Status**: IN_PROGRESS

## Protocol Compliance

### Phase 1: Serena Initialization ✅
- Tool: `mcp__serena__initial_instructions`
- Evidence: Tool output received confirming project activation
- Status: VERIFIED

### Phase 2: Context Retrieval ✅
- Tool: `Read(.agents/HANDOFF.md)`
- Evidence: File content loaded (read-only protocol, no update needed)
- Status: VERIFIED

### Phase 3: Session Log Creation ✅
- Tool: `Write(.agents/sessions/2025-12-23-session-87-adr-017-analyst-review.md)`
- Status: CREATING NOW

## Context Retrieved

### ADR-017 Overview
- **Status**: Proposed
- **Date**: 2025-12-23
- **Core Problem**: False PASS verdicts (missing issues) in AI reviews, especially with large PRs where context is summary-only
- **Proposed Solution**: Evidence-aware, tiered model routing with conservative verdict policy

### Key Files Examined
- `.agents/architecture/ADR-017-model-routing-low-false-pass.md` (197 lines)
- `.github/actions/ai-review/action.yml` (650 lines)
- `.github/workflows/ai-pr-quality-gate.yml` (initial 145 lines)

### Relevant Memories Loaded
1. `adr-014-review-findings`: ADR review patterns (parallel dispatch of architect/critic/analyst/security)
2. `skill-protocol-004-rfc-2119-must-evidence`: RFC 2119 compliance requirements
3. `skill-protocol-002-verification-based-gate-effectiveness`: Verification-based gate patterns
4. `copilot-pr-review-patterns`: Historical Copilot review signal quality (21% actionable on PR #249)
5. `pr-review-noise-skills`: CodeRabbit and Copilot false positive patterns

## Analysis Progress

### Initial Assessment
- ADR is well-structured and addresses a real, documented problem
- Proposes specific, implementable routing logic
- Contains both implementation details and governance requirements
- Claims are heuristic-based but lack empirical evidence

### Key Questions for Analysis
1. **Root cause**: Does false PASS primarily stem from summary-only context or model limitations?
2. **Model claims**: Are the vendor model recommendations empirically validated in this environment?
3. **Evidence availability**: What is actual false PASS rate before/after implementation?
4. **Feasibility**: Can the tiered routing be implemented without major workflow refactoring?
5. **Success metrics**: Are the proposed metrics measurable and sufficient?

## Investigation Areas

- [ ] Examine workflow usage of copilot-model parameter
- [ ] Check if workflows currently pass model selection explicitly
- [ ] Review action.yml to identify required changes
- [ ] Assess governance requirement (guardrail step for omitted copilot-model)
- [ ] Evaluate evidence availability in current context builders

---

**Session Status**: IN_PROGRESS - Analysis phase
**Next**: Complete detailed analyst review following ADR-017 section by section
