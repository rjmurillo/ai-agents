# Design Review: VSCode Copilot Parity Plan

**Reviewer**: Architect
**Date**: 2026-01-14
**Artifact**: `.agents/planning/claude-compat/vscode-copilot-parity-plan.md`
**Status**: [WARNING] - Conditional approval with required actions

---

## Executive Summary

The parity plan maintains ADR-036 compliance but introduces architectural risks requiring mitigation. The plan adds 7 agents to source, 7 templates, and 14 auto-generated files. This increases maintenance burden from 36 to 50 files. Three concerns require resolution before implementation proceeds.

| Concern | Verdict | Required Action |
|---------|---------|-----------------|
| ADR-036 Compliance | [PASS] | None - maintains two-source pattern |
| New Artifact Type (prompts) | [WARNING] | Requires ADR before implementation |
| Memory System Portability | [FAIL] | Document graceful degradation strategy |
| Platform Capability Tiers | [WARNING] | Rename from "parity" to "compatibility" |
| Installer Scope Creep | [PASS] | Changes are minimal and scoped |
| Sync Automation Gap | [WARNING] | Add drift detection for new templates |

---

## Concern 1: ADR-036 Compliance

**Status**: [PASS]

### Analysis

The plan correctly follows the two-source architecture:

| Source | Current | After Plan | Change |
|--------|---------|------------|--------|
| src/claude/ (Source 1) | 20 files | 27 files | +7 agents |
| templates/agents/ (Source 2) | 18 files | 25 files | +7 templates |
| src/copilot-cli/ (generated) | 18 files | 25 files | +7 auto |
| src/vs-code-agents/ (generated) | 18 files | 25 files | +7 auto |
| **Total** | 74 files | 102 files | +28 files |

**File count correction**: ADR-036 states 36 editable files (18 Claude + 18 templates). Post-plan: 52 editable files (27 + 25). This is a 44% increase in maintenance surface.

### Synchronization Burden

ADR-036 explicitly accepts manual synchronization as "toil" (line 76-82). The plan adds 7 more files requiring this toil. The burden is linear with agent count.

**Quantified impact**: Each cross-platform content update now touches 25 templates instead of 18 (+39% effort per change).

### Verdict

Plan maintains ADR-036 architecture. Increased maintenance burden is an accepted tradeoff per the ADR.

---

## Concern 2: New Artifact Type (Prompts)

**Status**: [WARNING] - ADR required before implementation

### Analysis

The plan introduces `templates/prompts/` as a new artifact category:

```text
templates/
├── agents/           # Existing (ADR-036)
├── platforms/        # Existing (ADR-036)
└── prompts/          # NEW - not covered by ADR-036
    ├── README.md
    ├── pr-review.prompt.md
    └── push-pr.prompt.md
```

**Architectural implications**:

1. **New generation pipeline?** ADR-036 defines `Generate-Agents.ps1` for agents. Do prompts need `Generate-Prompts.ps1`?
2. **Platform variations?** Do prompts have platform-specific variants like agents?
3. **Installer integration?** Config.psd1 changes suggest yes, but no automation documented.

### Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Scope creep to more artifact types | Medium | Medium | ADR defines boundaries |
| Inconsistent generation patterns | Medium | High | Single generation approach |
| Drift between prompt variants | High | Medium | Same drift detection as agents |

### Recommendation

Create ADR-041: Portable Prompt Architecture. Required sections:

1. Relationship to ADR-036 (extension or modification?)
2. Generation strategy (manual, templated, or auto-generated)
3. Platform variant handling
4. Installer integration approach
5. Drift detection requirements

**Blocking**: Milestone 3 (Portable Prompts) should not proceed until ADR-041 is accepted.

---

## Concern 3: Memory System Architecture

**Status**: [FAIL] - Plan claims portability without evidence

### Analysis

The `context-retrieval` agent has deep MCP dependencies:

| Tool Reference | Count | Portable? |
|----------------|-------|-----------|
| `mcp__forgetful__*` | 5+ | No - localhost HTTP service |
| `mcp__context7__*` | 2 | Unknown - needs research |
| `mcp__serena__*` | via Memory Router | No - Claude-specific MCP |
| `mcp__deepwiki__*` | 1 | Unknown - needs research |

The plan states (line 189-193):
> Replace `mcp__forgetful__*` tool references (Claude-specific)
> Replace with cloudmcp-manager or generic memory

**Problem**: `cloudmcp-manager` is NOT more portable than Forgetful. It is also an MCP tool with specific availability requirements.

### ADR-037 Implications

ADR-037 establishes Memory Router with Serena-first routing. Key finding:

> Serena is the canonical memory layer because it travels with the Git repository. Forgetful provides supplementary semantic search but its database contents are local-only and unavailable on hosted platforms.

**Question**: What is the Copilot/VSCode equivalent of Serena? Answer: None documented.

### Recommendation

1. **Document capability tiers** for context-retrieval agent:

   | Platform | Memory Capability | Degradation |
   |----------|-------------------|-------------|
   | Claude | Full (Serena + Forgetful + MCP) | N/A |
   | VSCode | Lexical only (file-based) | No semantic search |
   | Copilot CLI | Lexical only (file-based) | No semantic search |

2. **Update context-retrieval.shared.md** to explicitly handle missing memory tools:

   ```markdown
   ## Platform-Specific Memory
   
   - **With MCP Memory**: Use cloudmcp-manager or Forgetful
   - **Without MCP Memory**: Fall back to file-based search of .agents/ and .serena/
   - **Minimum viable**: Grep-based context gathering from project files
   ```

3. **Add acceptance criteria** to Milestone 2, Task 2:
   > Agent functions when NO memory MCP tools are available (graceful degradation)

---

## Concern 4: Platform Capability Divergence

**Status**: [WARNING] - Terminology creates false expectations

### Analysis

The plan title uses "parity" but ADR-036 Platform Capability Matrix shows significant gaps:

| Capability | Claude | Copilot | Gap |
|------------|--------|---------|-----|
| MCP Tools | 500+ | Limited | 95%+ reduction |
| Serena Integration | Full | None | 100% loss |
| Persistent Memory | Full | Limited | Significant loss |

Claiming "parity" when delivering "compatibility" creates expectation mismatch.

### Recommendation

1. Rename plan from "Parity Plan" to "Compatibility Plan"
2. Add "Capability Tier" section to plan documentation:

   | Tier | Definition | Platforms |
   |------|------------|-----------|
   | Full | All agent features available | Claude Code |
   | Enhanced | Core features + limited MCP | VSCode with MCP setup |
   | Basic | Core features, no MCP | VSCode/Copilot CLI default |

3. Document which agents operate at which tier on each platform

---

## Concern 5: Installer Architecture Impact

**Status**: [PASS]

### Analysis

Config.psd1 changes are scoped and follow existing patterns:

```powershell
# Existing pattern for commands (Claude)
CommandsDir   = '.claude/commands'
CommandFiles  = @("pr-comment-responder.md")

# Proposed pattern for prompts (Copilot/VSCode)
PromptsDir    = '.github/prompts'
PromptFiles   = @("pr-review.prompt.md", "push-pr.prompt.md")
```

The installer already handles multiple artifact types (agents, commands, skills). Adding prompts follows the same pattern.

### Verification

Install-Common.psm1 may need a new function:

```powershell
function Install-PromptFiles {
    # Similar to Install-CommandFiles but for .prompt.md
}
```

**Estimated complexity**: ~50 lines, consistent with existing patterns.

---

## Concern 6: Sync Automation Gap

**Status**: [WARNING]

### Analysis

The plan identifies manual sync as toil (line 604-605 in ADR-036 reference):

> Template drift after initial sync - Risk: Low - Weekly drift detection CI exists

**Problem**: The plan adds 7 new templates but does not verify:

1. Does drift-detection.yml auto-discover new templates?
2. Are new agents covered by existing CI?

### Recommendation

Add verification task to Milestone 2:

```markdown
10. [ ] Verify drift detection covers new agents
    - Acceptance: CI detects template vs generated divergence for all 7 new agents
    - Files: .github/workflows/drift-detection.yml
```

---

## Domain Model Alignment

| Concept | Current | Proposed | Status |
|---------|---------|----------|--------|
| Agent | md file with frontmatter | Unchanged | Aligned |
| Template | *.shared.md in templates/ | Unchanged | Aligned |
| Command | Claude slash command | N/A for Copilot | Intentional divergence |
| Prompt | (new) .prompt.md file | New artifact type | Requires ADR |

**Bounded Context Changes**: The plan introduces "prompts" as a new bounded context parallel to "commands". This is the architectural decision requiring ADR documentation.

---

## Abstraction Consistency

| Layer | Current | Change Impact | Status |
|-------|---------|---------------|--------|
| Source (src/) | Platform-specific agents | +7 Claude agents | Maintained |
| Templates (templates/) | Shared agent definitions | +7 shared + new prompts/ | Consistency question |
| Generated (src/*-agents/) | Auto-generated | +14 files | Maintained |
| Installer (scripts/) | Handles agents, commands, skills | +prompts | Extension needed |

**Issue**: templates/ currently contains agents/ and platforms/. Adding prompts/ creates a new top-level category without documented relationship to agents/.

---

## Recommendations

### Required Actions (Blocking)

1. **Create ADR-041**: Portable Prompt Architecture
   - Status: Required before Milestone 3
   - Scope: Define prompts as artifact type, generation strategy, platform handling

2. **Document Memory Degradation**: Update plan with graceful degradation strategy
   - Status: Required before Milestone 2, Task 2
   - Scope: What happens when memory MCP tools unavailable

### Recommended Actions (Non-Blocking)

3. **Rename Plan**: Change from "Parity" to "Compatibility"
   - Rationale: Sets accurate expectations

4. **Add Drift Detection Verification**: Ensure CI covers new templates
   - Rationale: Prevents silent regression

5. **Update Effort Estimate**: Account for ADR creation
   - Current: 28.5h
   - Revised: 32.5h (+4h for ADR-041 + drift verification)

---

## Issues Discovered

| Issue | Priority | Category | Description |
|-------|----------|----------|-------------|
| ARCH-001 | P1 | Design Flaw | Prompts artifact type introduced without ADR |
| ARCH-002 | P1 | Blocker | Memory portability claims unsubstantiated |
| ARCH-003 | P2 | Risk | "Parity" terminology creates false expectations |
| ARCH-004 | P2 | Debt | Sync automation coverage unverified for new templates |

**Issue Summary**: P0: 0, P1: 2, P2: 2, Total: 4

---

## Verdict

**Conditional Approval** with blocking requirements:

1. [BLOCKING] Create ADR-041 before Milestone 3
2. [BLOCKING] Document memory degradation strategy before Milestone 2

After addressing blocking items, plan may proceed. Non-blocking recommendations should be addressed within implementation milestones.

---

*Architecture review complete. Handing off to orchestrator for routing decision.*
