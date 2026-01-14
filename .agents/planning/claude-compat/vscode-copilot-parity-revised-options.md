# VSCode Copilot Parity Plan: Revised Work Breakdown Options

**Status**: [IN PROGRESS] - Addressing specialist feedback critical findings

**Created**: 2026-01-14

## Critical Findings Summary

The original plan contained significant errors identified during specialist review:

| Finding | Original Claim | Corrected Value | Impact |
|---------|----------------|-----------------|--------|
| Agent count | 8 agents to port | **7 agents** (AGENTS.md is documentation) | Scope reduction |
| cloudmcp-manager portability | Portable memory | **NOT portable** (MCP server unavailable on Copilot) | Design change |
| context-retrieval effort | 4h | **6-8h** (Forgetful, Serena, Context7, Memory Router dependencies) | Schedule risk |
| License research | 30 min | **1-2h** (security risk requires due diligence) | Compliance risk |
| Prompt file location | .github/prompts/ everywhere | **VSCode: .github/prompts/, CLI: no separate directory** | Installer complexity |
| ADR requirement | None | **ADR-041 required** before prompts artifact type | Governance gate |
| Copilot CLI blockers | Issue #452 only | **5+ blocking issues** beyond #452 | Platform viability |

---

## Option A: Full Plan (Revised)

**Strategic Goal**: Port all 7 agents to Copilot platforms with corrected scope and effort.

### Revised Scope

| Category | Count | Original Effort | Revised Effort | Rationale |
|----------|-------|-----------------|----------------|-----------|
| License research | 1 file | 1h | **2h** | Security risk requires evidence trail |
| ADR-041 creation | 1 ADR | 0h | **2h** | Governance gate for prompts artifact |
| New agent templates | 7 agents | 15.5h | **18h** | context-retrieval increased to 8h |
| Add to src/claude/ | 6 agents | 3h | 3h | No change |
| Prompt files | 2 prompts | 4h | **3h** | CLI excluded (no separate directory) |
| Installer updates | Config + module | 2h | **4h** | Platform-specific logic for prompts |
| Platform validation | Testing | 0h | **3h** | Copilot CLI blocking issues |
| Documentation | 2 documents | 3h | **4h** | cloudmcp-manager limitations |
| **Total** | | 28.5h | **39h** | +37% increase |

### Phase 0: Governance and License (4h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| A0-T1 | Create ADR-041: Prompts Artifact Type | 2h | Required before Phase 3 |
| A0-T2 | Research agent origins (debug, janitor, prompt-builder, technical-writer) | 1h | None |
| A0-T3 | Verify MIT licenses with evidence trail | 0.5h | After A0-T2 |
| A0-T4 | Create THIRD-PARTY-LICENSES.txt with attribution | 0.5h | After A0-T3; Security: Document unknowns |

**ADR-041 Scope**:

- Define prompts as first-class artifact type
- Specify file locations per platform (VSCode vs CLI)
- Define generation pipeline requirements
- Document relationship to commands (Claude) and agents

### Phase 1: Add Missing Agents to Source (3h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| A1-T1 | Copy adr-generator.md to src/claude/ | 0.25h | None |
| A1-T2 | Copy context-retrieval.md to src/claude/ | 0.5h | Document heavy MCP dependencies |
| A1-T3 | Copy debug.md to src/claude/ | 0.25h | None |
| A1-T4 | Copy janitor.md to src/claude/ | 0.25h | None |
| A1-T5 | Copy prompt-builder.md to src/claude/ | 0.25h | None |
| A1-T6 | Verify sync spec-generator.md | 0.5h | Compare, merge if needed |
| A1-T7 | Copy technical-writer.md to src/claude/ | 0.25h | None |
| A1-T8 | Update src/claude/AGENTS.md catalog | 0.75h | After A1-T1..T7 |

### Phase 2: Create Shared Templates (18h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| A2-T1 | Create adr-generator.shared.md | 2h | Remove Serena refs |
| A2-T2 | Create context-retrieval.shared.md | **8h** | Remove Forgetful, Serena, Context7, Memory Router; document as degraded |
| A2-T3 | Create debug.shared.md | 1.5h | None |
| A2-T4 | Create janitor.shared.md | 1.5h | None |
| A2-T5 | Create prompt-builder.shared.md | 2h | Remove mcp__* syntax |
| A2-T6 | Create spec-generator.shared.md | 2h | Replace Serena |
| A2-T7 | Create technical-writer.shared.md | 2h | None |
| A2-T8 | Run generation script | 0.5h | After A2-T1..T7 |
| A2-T9 | Validate generation | 0.5h | After A2-T8 |

**context-retrieval Adaptation Strategy**:

```markdown
Original Dependencies (Claude-only):
- mcp__forgetful__* (semantic memory, knowledge graph)
- mcp__serena__* (project memory)
- mcp__context7__* (framework docs)
- Memory Router skill (unified search)

Portable Fallback:
- File system search (Glob, Grep, Read) - FULLY PORTABLE
- WebSearch - PARTIALLY PORTABLE (rate limits)
- Documentation links - FULLY PORTABLE
- NO persistent memory across sessions

Degraded Capability Notice:
"This agent operates without persistent memory on Copilot platforms.
Context gathering limited to file system search and web lookup."
```

### Phase 3: Portable Prompts (3h)

**Note**: VSCode only. Copilot CLI does not support separate prompt files.

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| A3-T1 | Validate ADR-041 approved | 0h | BLOCKING: Cannot proceed without ADR |
| A3-T2 | Create templates/prompts/README.md | 0.5h | After ADR-041 |
| A3-T3 | Create pr-review.prompt.md (VSCode only) | 1.5h | Replace ultrathink, skills |
| A3-T4 | Create push-pr.prompt.md (VSCode only) | 1h | Replace skills with gh CLI |

### Phase 4: Installer Integration (4h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| A4-T1 | Update Config.psd1 with platform-specific prompts | 1.5h | VSCode: .github/prompts/, CLI: none |
| A4-T2 | Update Install-Common.psm1 for prompts | 1.5h | Conditional installation |
| A4-T3 | Test VSCode installation | 0.5h | After A4-T1..T2 |
| A4-T4 | Test Copilot CLI installation | 0.5h | Document blocking issues |

### Phase 5: Platform Validation (3h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| A5-T1 | Document Copilot CLI blocking issues beyond #452 | 1h | Research GitHub issues |
| A5-T2 | Smoke test debug agent in VSCode | 0.5h | None |
| A5-T3 | Smoke test debug agent in Copilot CLI | 0.5h | May fail due to blockers |
| A5-T4 | Create platform compatibility matrix | 1h | After A5-T1..T3 |

### Phase 6: Documentation (4h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| A6-T1 | Create PLATFORM-LIMITATIONS.md | 2h | Document cloudmcp-manager, memory |
| A6-T2 | Update templates/README.md | 1h | Feature matrix |
| A6-T3 | Update templates/AGENTS.md | 1h | All 7 agents documented |

### Option A: Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| context-retrieval becomes near-useless | HIGH | HIGH | Document as "degraded mode" prominently |
| Copilot CLI has more blockers | MEDIUM | HIGH | A5-T1: Research before implementation |
| ADR-041 delayed/rejected | LOW | MEDIUM | Phase 3 blocked; complete other phases |
| cloudmcp-manager alternative not found | HIGH | MEDIUM | Accept no persistent memory; document |
| Effort underestimate persists | MEDIUM | MEDIUM | Add 20% buffer (39h -> 47h) |

### Option A: Go/No-Go Criteria

| Criterion | Threshold | Status |
|-----------|-----------|--------|
| ADR-041 approved | MUST | [PENDING] |
| License research complete | MUST | [PENDING] |
| At least 5/7 agents portable | SHOULD | Unknown |
| context-retrieval viable in degraded mode | SHOULD | Requires design |
| Copilot CLI blockers < 3 critical | SHOULD | Requires research |

---

## Option B: Selective Compatibility

**Strategic Goal**: Port only fully portable agents. Skip agents with heavy dependencies.

### Portable Agents (4)

| Agent | Dependencies | Portability |
|-------|--------------|-------------|
| debug | File system, shell | **FULLY PORTABLE** |
| janitor | File system, git | **FULLY PORTABLE** |
| technical-writer | File system, templates | **FULLY PORTABLE** |
| adr-generator | File system, templates | **FULLY PORTABLE** |

### Excluded Agents (3)

| Agent | Dependencies | Reason for Exclusion |
|-------|--------------|---------------------|
| context-retrieval | Forgetful, Serena, Context7, Memory Router | 80% capability loss |
| prompt-builder | mcp__* tool syntax | Significant adaptation |
| spec-generator | Serena memory | Medium adaptation |

### Revised Scope

| Category | Count | Effort | Notes |
|----------|-------|--------|-------|
| License research | 1 file | 1h | Fewer agents to verify |
| New agent templates | 4 agents | 7h | Simple agents only |
| Add to src/claude/ | 4 agents | 1.5h | Fewer files |
| Prompt files | 0 prompts | 0h | Defer until ADR-041 |
| Installer updates | Config only | 1h | No prompts logic |
| Documentation | 2 documents | 2h | Smaller scope |
| **Total** | | **12.5h** | -56% from revised Option A |

### Phase 0: License Research (1h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| B0-T1 | Research origin of debug.md, janitor.md, technical-writer.md, adr-generator.md | 0.5h | None |
| B0-T2 | Create THIRD-PARTY-LICENSES.txt | 0.5h | After B0-T1 |

### Phase 1: Add to Source (1.5h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| B1-T1 | Copy adr-generator.md to src/claude/ | 0.25h | None |
| B1-T2 | Copy debug.md to src/claude/ | 0.25h | None |
| B1-T3 | Copy janitor.md to src/claude/ | 0.25h | None |
| B1-T4 | Copy technical-writer.md to src/claude/ | 0.25h | None |
| B1-T5 | Update src/claude/AGENTS.md | 0.5h | After B1-T1..T4 |

### Phase 2: Create Templates (7h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| B2-T1 | Create adr-generator.shared.md | 2h | None |
| B2-T2 | Create debug.shared.md | 1.5h | None |
| B2-T3 | Create janitor.shared.md | 1.5h | None |
| B2-T4 | Create technical-writer.shared.md | 1.5h | None |
| B2-T5 | Run generation script | 0.25h | After B2-T1..T4 |
| B2-T6 | Validate generation | 0.25h | After B2-T5 |

### Phase 3: Installer (1h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| B3-T1 | Verify Config.psd1 handles new agents | 0.5h | None |
| B3-T2 | Test installation | 0.5h | After B3-T1 |

### Phase 4: Documentation (2h)

| Task ID | Description | Effort | Conditions |
|---------|-------------|--------|------------|
| B4-T1 | Create PLATFORM-LIMITATIONS.md | 1h | Document excluded agents |
| B4-T2 | Update templates/README.md | 1h | 4-agent matrix |

### Option B: Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Users expect full parity | MEDIUM | MEDIUM | Clear documentation |
| Excluded agents requested later | HIGH | LOW | Can add incrementally |
| Underestimated even simple agents | LOW | LOW | Buffer included |

### Option B: Go/No-Go Criteria

| Criterion | Threshold | Status |
|-----------|-----------|--------|
| License research complete | MUST | [PENDING] |
| All 4 agents fully portable | MUST | Expected YES |
| Platform limitations documented | MUST | [PENDING] |

---

## Side-by-Side Comparison

| Dimension | Option A: Full Plan | Option B: Selective |
|-----------|---------------------|---------------------|
| **Agents Ported** | 7 | 4 |
| **Effort** | 39h (+47h with buffer) | 12.5h |
| **ADR Required** | ADR-041 | None |
| **context-retrieval** | Included (degraded) | Excluded |
| **prompt-builder** | Included | Excluded |
| **spec-generator** | Included | Excluded |
| **Prompts** | 2 (VSCode only) | 0 |
| **cloudmcp-manager** | Document unavailable | N/A |
| **Risk Level** | HIGH | LOW |
| **Time to Value** | 2-3 weeks | 1 week |
| **User Expectations** | "Full parity" claim | Honest limitations |

### Feature Availability Matrix

| Feature | Claude Code | VSCode (A) | VSCode (B) | Copilot CLI (A) | Copilot CLI (B) |
|---------|-------------|------------|------------|-----------------|-----------------|
| debug | Full | Full | Full | Blocked* | Blocked* |
| janitor | Full | Full | Full | Blocked* | Blocked* |
| technical-writer | Full | Full | Full | Blocked* | Blocked* |
| adr-generator | Full | Full | Full | Blocked* | Blocked* |
| context-retrieval | Full | Degraded | N/A | Blocked* | N/A |
| prompt-builder | Full | Adapted | N/A | Blocked* | N/A |
| spec-generator | Full | Adapted | N/A | Blocked* | N/A |
| Persistent memory | Full | None | None | None | None |
| pr-review prompt | Full | Full | N/A | N/A | N/A |
| push-pr prompt | Full | Full | N/A | N/A | N/A |

*Blocked by Copilot CLI issues beyond #452. Research required (A5-T1).

---

## Recommendation

### Primary Recommendation: Option B (Selective Compatibility)

**Rationale**:

1. **12.5h vs 39h**: 68% effort reduction with clear deliverable
2. **No governance blocker**: ADR-041 not required
3. **Honest marketing**: "4 agents available" is accurate vs "7 agents (3 degraded)"
4. **Lower risk**: Fully portable agents only
5. **Faster value**: 1 week vs 2-3 weeks

### Secondary Recommendation: Defer Context-Retrieval

If Option A is chosen, defer context-retrieval to Phase 2:

1. Port 4 simple agents (debug, janitor, technical-writer, adr-generator)
2. Learn from Copilot CLI blocking issues
3. Design degraded context-retrieval after platform validation

### Conditional Upgrade Path

| Milestone | Action |
|-----------|--------|
| Option B complete | Evaluate user demand for excluded agents |
| ADR-041 approved | Add prompts to VSCode |
| cloudmcp alternative found | Revisit context-retrieval |
| Copilot CLI issues resolved | Enable CLI agents |

---

## Next Steps

1. [ ] Approve Option A or Option B
2. [ ] If Option A: Create ADR-041 first
3. [ ] Begin license research (both options)
4. [ ] Research Copilot CLI blocking issues (Option A only)

---

*Plan revised 2026-01-14 based on specialist critical findings.*
