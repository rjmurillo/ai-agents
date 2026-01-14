# Plan: Claude Code Feature Parity for VSCode, VSCode Insiders, and Copilot CLI

**Status**: [APPROVED WITH REMEDIATIONS] - Full plan with specialist feedback incorporated

**Revision**: 2026-01-14 (Post-Multi-Agent Review)

## Strategic Context (Revised 2026-01-14)

**Cost Analysis**:

| Platform | Pricing | Strategic Priority |
|----------|---------|-------------------|
| VSCode Copilot | Unlimited premium requests | **P0 - Primary investment** |
| Copilot CLI | Unlimited premium requests | **P0 - Primary investment** |
| Claude Code | Paid, throttled | P1 - Source of truth |
| Codex CLI | Paid, throttled | P2 - Evaluate via Issue 858 |

**Goal**: Port ALL Claude Code agents to Copilot platforms, including agents currently only in `.claude/agents/` that need to be added to project source.

---

## Multi-Agent Review: Critical Findings and Remediations (2026-01-14)

> **Review performed by**: Critic, Architect, Independent-Thinker, Analyst, Security, High-Level-Advisor, Roadmap, Planner
>
> **Artifacts created**: See `.agents/critique/002-*.md`, `.agents/architecture/DESIGN-REVIEW-*.md`, `.agents/security/SR-*.md`, `.agents/planning/claude-compat/vscode-copilot-parity-revised-options.md`

### Critical Findings Summary

| ID | Finding | Original | Corrected | Remediation |
|----|---------|----------|-----------|-------------|
| CF-1 | Agent count | 8 agents | **7 agents** | AGENTS.md is documentation, not an agent |
| CF-2 | cloudmcp-manager | Portable | **NOT portable** | Design degraded mode; document limitations |
| CF-3 | context-retrieval effort | 4h | **8h** | Heavy MCP dependencies require redesign |
| CF-4 | License due diligence | 30 min | **2h** | Security requires evidence trail |
| CF-5 | Prompt file location | Same everywhere | **Platform-specific** | VSCode: .github/prompts/, CLI: none |
| CF-6 | ADR requirement | None | **ADR-041 required** | Governance gate for prompts artifact |
| CF-7 | Copilot CLI blockers | #452 only | **5+ blocking issues** | Research and document all blockers |
| CF-8 | Total effort | 28.5h | **43h** | Includes buffer and validation |

### Remediated Effort Breakdown

| Category | Original | Revised | Delta | Rationale |
|----------|----------|---------|-------|-----------|
| Phase 0: Governance & License | 1h | **4h** | +3h | ADR-041 + extended license research |
| Phase 1: Add to src/claude/ | 3h | **4h** | +1h | Content validation added |
| Phase 2: Create Templates | 15.5h | **20h** | +4.5h | context-retrieval 8h + MCP audit |
| Phase 3: Portable Prompts | 4h | **3h** | -1h | CLI excluded (no prompts) |
| Phase 4: Installer | 2h | **4h** | +2h | Platform-specific logic |
| Phase 5: Platform Validation | 0h | **4h** | +4h | Blocking issue research + testing |
| Phase 6: Documentation | 3h | **4h** | +1h | Limitations documentation |
| **Total** | **28.5h** | **43h** | **+14.5h** | +51% from original |

### Blocking Conditions (MUST complete before implementation)

| ID | Condition | Phase | Owner |
|----|-----------|-------|-------|
| BC-1 | Create ADR-041: Prompts Artifact Type | Phase 0 | Architect |
| BC-2 | Complete license research with evidence trail | Phase 0 | Security |
| BC-3 | Validate user-facing content restrictions | Phase 1 | Implementer |
| BC-4 | Research all Copilot CLI blocking issues | Phase 5 | Analyst |

### Platform Capability Reality Check

| Capability | Claude Code | VSCode Copilot | Copilot CLI | Remediation Strategy |
|------------|-------------|----------------|-------------|---------------------|
| Persistent Memory | Full (Serena + Forgetful) | **None** | **None** | Document as limitation; no workaround |
| MCP Tools | 500+ servers | Limited | Limited | Strip MCP refs; use native tools |
| Multi-Agent | Task() tool | @agent syntax | @agent syntax | Adapt handoff syntax |
| Hooks | 15+ scripts | None | None | Document as limitation |
| Skills | 32 directories | None | None | Replace with gh CLI + inline |

### context-retrieval Degradation Strategy

The context-retrieval agent loses 80% capability on non-Claude platforms. Remediation:

```markdown
## Claude Code (Full Capability)
- Forgetful MCP: Semantic memory + knowledge graph
- Serena MCP: Project-specific memories
- Context7 MCP: Framework documentation
- Memory Router: Unified search across sources
- DeepWiki MCP: Repository documentation

## VSCode/Copilot CLI (Degraded Mode)
- File system: Glob, Grep, Read (PORTABLE)
- Web search: WebSearch, WebFetch (RATE-LIMITED)
- Manual context: User provides project context

## Agent Header (Copilot Version)
> **Platform Notice**: This agent operates in degraded mode on non-Claude platforms.
> Persistent memory and semantic search are unavailable. Context gathering is
> limited to file system search and web lookup.
```

---

## Revised Scope (2026-01-14)

### Agents to Template

`.claude/agents/` contains 26 agents. `templates/agents/` contains 18. Gap = 8 agents.

| Agent | In .claude/agents/ | In templates/ | Action |
|-------|-------------------|---------------|--------|
| adr-generator | Yes | No | **Add to templates** |
| context-retrieval | Yes | No | **Add to templates** (adapt MCP refs) |
| debug | Yes | No | **Add to templates** |
| janitor | Yes | No | **Add to templates** |
| prompt-builder | Yes | No | **Add to templates** |
| spec-generator | Yes | No | **Add to templates** |
| technical-writer | Yes | No | **Add to templates** |
| AGENTS.md | Yes | No | **Add to templates** (documentation) |

**Note**: These agents exist in `.claude/agents/` (runtime) but not in `src/claude/` (source). This plan will:

1. Add them to `src/claude/` as source files
2. Create corresponding templates in `templates/agents/`
3. Generate Copilot/VSCode variants

### Commands to Port as Prompts

| Command | Action |
|---------|--------|
| pr-review.md | Adapt to portable prompt |
| push-pr.md | Adapt to portable prompt |
| pr-comment-responder.md | Already configured |

---

## Value Statement

As a developer using VSCode or Copilot CLI, I want access to as many Claude Code capabilities as possible so that I can benefit from the same agentic workflows regardless of my chosen IDE.

## Target Version

v0.2.0

## Executive Summary

This plan analyzes the `.claude/` directory contents against `templates/` to determine what Claude Code features can be ported to VSCode and Copilot CLI via the `scripts/install.ps1` installer. Based on platform capability constraints (ADR-036), this plan identifies compatible features and documents incompatibilities with technical rationale.

**POST-VALIDATION UPDATE**: Initial analysis significantly overstated parity potential. See Critical Findings above.

## Revised Recommendation

**Plan Direction**: APPROVED - Full Copilot parity with Claude Code

### Recommended Plan: Full Agent Parity

**Strategic Goal**: Enable all 26 Claude Code agents on VSCode and Copilot CLI (unlimited premium requests).

**Scope**:

| Category | Count | Effort |
|----------|-------|--------|
| Phase 0: Governance + License | ADR-041 + research | 4h |
| Phase 1: Add to src/claude/ | 6 agents + validation | 4h |
| Phase 2: Create Templates | 7 agents | 20h |
| Phase 3: Portable Prompts | 2 prompts (VSCode only) | 3h |
| Phase 4: Installer Integration | Config + module | 4h |
| Phase 5: Platform Validation | Testing + blockers | 4h |
| Phase 6: Documentation | 3 documents | 4h |
| **Total** | | **43h** |

### Phase 0: Governance and License Research (4h) [REMEDIATED]

> **Security Finding**: Original 30-minute gate insufficient for due diligence.
> **Architect Finding**: ADR-041 required before introducing prompts artifact type.

#### Task 0.1: Create ADR-041 - Prompts Artifact Type (2h) [BLOCKING]

Before implementing prompts (Phase 3), create ADR-041 documenting:

| Section | Content |
|---------|---------|
| Context | Need for portable prompts across platforms |
| Decision | Define prompts as first-class artifact type |
| File Locations | VSCode: .github/prompts/, CLI: Not supported |
| Generation | How prompts integrate with existing template pipeline |
| Relationship | Prompts vs Commands (Claude) vs Agents |

**Acceptance Criteria**: ADR-041 approved before Phase 3 begins.

#### Task 0.2: License Research with Evidence Trail (1.5h)

| Task | Effort | Notes |
|------|--------|-------|
| Research agent origins | 1h | Document search methodology |
| Verify MIT licenses | 0.25h | Require evidence (URL, commit SHA) |
| Create THIRD-PARTY-LICENSES.txt | 0.25h | Document attributions OR mark as original |

**Research Methodology** (Security requirement):

1. Search GitHub for distinctive patterns in each agent
2. Check git history for original authorship
3. Search VSCode marketplace for agent packs
4. Check Anthropic/GitHub repos for similar content
5. Document search trail in THIRD-PARTY-LICENSES.txt

**Decision Gate** (1h limit, then escalate):
- If origin found: Document attribution
- If origin NOT found after 1h: Mark as "Original work - no external source identified"
- If copyrighted content suspected: BLOCK and escalate to legal

**Agent Origin Analysis**:

| Agent | Likely Origin | License Status | Action |
|-------|---------------|----------------|--------|
| adr-generator | Custom/Internal | N/A | Original work |
| context-retrieval | Custom/Internal | N/A | Original work (uses project MCP) |
| debug | VSCode Copilot ecosystem | Verify MIT | Add attribution if external |
| janitor | VSCode Copilot ecosystem | Verify MIT | Add attribution if external |
| prompt-builder | VSCode Copilot ecosystem | Verify MIT | Add attribution if external |
| spec-generator | Custom/Internal | N/A | Already in src/claude/ |
| technical-writer | VSCode Copilot ecosystem | Verify MIT | Add attribution if external |

#### Task 0.3: Create THIRD-PARTY-LICENSES.txt (0.5h)

**THIRD-PARTY-LICENSES.txt Template**:

```text
# Third-Party Licenses

This file documents third-party content included in this repository.

## Agent Templates

### debug.md, janitor.md, prompt-builder.md, technical-writer.md

These agents originated from [SOURCE] and are used under the MIT License.

Original source: [URL]
Original author: [AUTHOR]
License: MIT

---

MIT License

Copyright (c) [YEAR] [COPYRIGHT HOLDER]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Research Tasks**:

1. [ ] Check if agents came from `github.com/anthropics/claude-code-agents` or similar
2. [ ] Check VSCode Copilot extension marketplace for agent packs
3. [ ] Search for debug.md/janitor.md/prompt-builder.md in public repositories
4. [ ] **Decision gate (30 min limit)**: If origins cannot be determined after 30 minutes of research, proceed with "Unknown origin, used under assumption of MIT compatibility per project license"

---

### Phase 1: Add Missing Agents to Source (3h)

Copy agents from `.claude/agents/` to `src/claude/` (source of truth):

| Task | Effort | Files |
|------|--------|-------|
| Copy adr-generator.md to src/claude/ | 0.25h | src/claude/adr-generator.md |
| Copy context-retrieval.md to src/claude/ | 0.5h | src/claude/context-retrieval.md |
| Copy debug.md to src/claude/ | 0.25h | src/claude/debug.md |
| Copy janitor.md to src/claude/ | 0.25h | src/claude/janitor.md |
| Copy prompt-builder.md to src/claude/ | 0.25h | src/claude/prompt-builder.md |
| Copy spec-generator.md to src/claude/ | 0.25h | src/claude/spec-generator.md |
| Copy technical-writer.md to src/claude/ | 0.25h | src/claude/technical-writer.md |
| Verify Claude-specific sections preserved | 1h | All 7 files |

### Phase 2: Create Shared Templates (14h)

Create templates for all 7 missing agents:

| Task | Effort | Notes |
|------|--------|-------|
| Create adr-generator.shared.md | 2h | Generic ADR workflow |
| Create context-retrieval.shared.md | **8h** | **[REMEDIATED]** Heavy MCP dependencies; see Degradation Strategy |
| Create debug.shared.md | 1.5h | Generic debugging workflow |
| Create janitor.shared.md | 1.5h | Generic cleanup workflow |
| Create prompt-builder.shared.md | 2h | Generic prompt engineering; remove mcp__* syntax |
| Create spec-generator.shared.md | 2h | EARS spec generation; replace Serena refs |
| Create technical-writer.shared.md | 2h | Generic documentation |
| MCP pattern audit | **1h** | **[NEW]** Exhaustive scan for all mcp__*, vscode/* patterns |
| Run generation script | 0.5h | Generate 14 new files |

**MCP Pattern Removal Checklist** (Security requirement):

```text
Patterns to remove/replace:
- mcp__forgetful__* (Forgetful MCP)
- mcp__serena__* (Serena MCP)
- mcp__context7__* (Context7 MCP) - keep if available on platform
- mcp__deepwiki__* (DeepWiki MCP) - keep if available on platform
- mcp__plugin_claude-mem_mcp-search__* (Claude memory plugin)
- mcp__cloudmcp-manager__* (cloudmcp-manager) - NOT PORTABLE
- vscode/* (VSCode-specific tool prefixes)
- Memory Router skill references

Patterns to keep:
- File system tools (Read, Glob, Grep)
- Web tools (WebSearch, WebFetch) if available
- @agent handoff syntax (Copilot native)
```

**Adaptation Notes**:
- Remove `mcp__serena__*` tool references (Claude-specific)
- Remove `mcp__forgetful__*` tool references (Claude-specific)
- Remove `mcp__cloudmcp-manager__*` references (NOT portable per analyst finding)
- Replace `Task()` with platform handoff syntax
- Remove Claude Code Tools sections
- Keep core workflows and document formats
- Add degradation notice to context-retrieval

### Phase 3: Portable Prompts (3h) [REMEDIATED]

> **Note**: VSCode only. Copilot CLI does not support separate prompt files.
> **Blocking**: Requires ADR-041 approval before starting.

| Task | Effort | Notes |
|------|--------|-------|
| Verify ADR-041 approved | 0h | **BLOCKING GATE** |
| Create templates/prompts/README.md | 0.5h | Structure + platform notes |
| Adapt pr-review.prompt.md | 1.5h | Replace ultrathink, skills with gh CLI |
| Adapt push-pr.prompt.md | 1h | Replace skills with gh CLI |

### Phase 4: Installer Integration (4h) [REMEDIATED]

| Task | Effort | Notes |
|------|--------|-------|
| Update Config.psd1 | 1.5h | VSCode: .github/prompts/, CLI: none |
| Update Install-Common.psm1 | 1.5h | Conditional prompts installation |
| Add path traversal validation | 0.5h | **[NEW]** Security requirement |
| Test VSCode installation | 0.25h | Repo + global scope |
| Test Copilot CLI installation | 0.25h | Document any failures |

### Phase 5: Platform Validation (4h) [NEW]

| Task | Effort | Notes |
|------|--------|-------|
| Research Copilot CLI blocking issues | 1.5h | Document #452, #760, #693, #687, #556 |
| Smoke test debug agent in VSCode | 0.5h | Load + basic prompt |
| Smoke test debug agent in Copilot CLI | 0.5h | May fail due to blockers |
| Create platform compatibility matrix | 1h | Document what works/fails |
| Define test matrix criteria | 0.5h | Beyond smoke tests |

**Test Matrix** (Critic requirement):

| Test | VSCode | Copilot CLI | Pass Criteria |
|------|--------|-------------|---------------|
| Agent loads without syntax errors | Required | Required | No parse errors |
| Agent responds to activation prompt | Required | Required | Coherent response |
| No blocked tool references | Required | Required | No mcp__*, vscode/* |
| Handoff syntax works | Required | Required | @agent invocation succeeds |
| Memory tools available | N/A | N/A | Documented as unavailable |

### Phase 6: Documentation (4h) [REMEDIATED]

| Task | Effort | Notes |
|------|--------|-------|
| Create PLATFORM-LIMITATIONS.md | 2h | Document all limitations prominently |
| Update templates/README.md | 1h | Feature matrix with degradation notes |
| Update templates/AGENTS.md | 1h | All 7 agents documented with caveats |

**PLATFORM-LIMITATIONS.md Required Sections**:

1. **Memory System**: No persistent memory on Copilot platforms
2. **MCP Tools**: Limited availability; document each tool's status
3. **Hooks**: No equivalent on Copilot platforms
4. **Skills**: Not portable; workarounds documented
5. **context-retrieval Degradation**: Explicit capability loss table

---

## Prerequisites

- [ ] Existing template generation pipeline (`build/Generate-Agents.ps1`) is functional
- [ ] `scripts/install.ps1` and `scripts/lib/Config.psd1` are operational
- [ ] Platform configuration files exist in `templates/platforms/`

## Platform Capability Analysis

### Source: ADR-036 Platform Capability Matrix

| Capability | Claude Code | Copilot CLI | VS Code Copilot | Parity Possible |
|------------|-------------|-------------|-----------------|-----------------|
| MCP Tools | Full (500+) | GitHub + custom | Custom MCP | Partial |
| Serena Integration | Full | None | None | No |
| Multi-Agent Orchestration | Full (Task tool) | Full (@agent) | Full (Agent HQ) | Yes |
| Agent Skills | Skills folder | Dec 2025 support | Full support | Yes |
| Repository Scope | Unlimited | Unlimited | Unlimited | Yes |
| Branch Access | Any | Any | Any | Yes |
| Persistent Memory | Serena + MCP | Limited | Limited | Partial |

## Current State Analysis

### `.claude/` Directory Contents (Source)

```text
.claude/
├── .gitignore                    # Local scope configuration
├── agents/                       # 26 agent files (runtime installed)
│   ├── AGENTS.md                 # Agent catalog documentation
│   └── *.md                      # Individual agent prompts
├── commands/                     # 11 slash command files
│   ├── README.md                 # Command catalog
│   ├── pr-comment-responder.md
│   ├── pr-review.md
│   ├── push-pr.md
│   ├── research.md
│   ├── session-init.md
│   ├── context-hub-setup.md
│   ├── context_gather.md
│   ├── forgetful/                # Memory commands subdirectory
│   └── memory-documentary.md
├── hooks/                        # 15+ hook scripts
│   ├── Common/HookUtilities.psm1
│   ├── PreToolUse/*.ps1
│   ├── PostToolUse/*.ps1
│   ├── SessionStart/*.ps1
│   ├── Stop/*.ps1
│   ├── SubagentStop/*.ps1
│   ├── PermissionRequest/*.ps1
│   ├── UserPromptSubmit/*.ps1
│   └── *.ps1                     # Top-level hooks
├── settings.json                 # Claude Code settings with hooks configuration
└── skills/                       # 30+ skill directories
    ├── CLAUDE.md                 # Skill development conventions
    ├── github/                   # GitHub operations skill (primary)
    └── [many more skills]
```

### `templates/` Directory Contents (Current)

```text
templates/
├── agents/                       # 18 shared agent templates
│   └── *.shared.md
├── platforms/                    # Platform configurations
│   ├── copilot-cli.yaml
│   └── vscode.yaml
├── AGENTS.md                     # Template system documentation
└── README.md
```

### Current `scripts/lib/Config.psd1` Installation Mapping

| Environment | SourceDir | Agents | Commands | Skills | Hooks |
|-------------|-----------|--------|----------|--------|-------|
| Claude | src/claude | Yes | 1 file | github only | No |
| Copilot | src/copilot-cli | Yes | No | No | No |
| VSCode | src/vs-code-agents | Yes | No | No | No |

## Gap Analysis

> **Note**: This section documents the original analysis. The Revised Scope section above contains the corrected, actionable findings.

### Category 1: Agents (FULL PARITY ACHIEVABLE)

**Current State**: 18 agents in templates, 26 agents in `.claude/agents/`

**Claude-Only Agents** (8 agents not in templates):

| Agent | File | Portable? | Rationale |
|-------|------|-----------|-----------|
| adr-generator | adr-generator.md | Yes | No Claude-specific dependencies |
| context-retrieval | context-retrieval.md | Partial | Heavy Forgetful MCP dependency |
| debug | debug.md | Yes | Generic debugging workflow |
| janitor | janitor.md | Yes | Generic cleanup agent |
| prompt-builder | prompt-builder.md | Yes | Generic prompt creation |
| spec-generator | spec-generator.md | Yes | Generic spec creation |
| technical-writer | technical-writer.md | Yes | Generic documentation |

**Recommendation**: Create shared templates for 6 of 8 Claude-only agents (exclude context-retrieval due to deep MCP integration).

### Category 2: Commands/Prompts (MEDIUM PARITY POTENTIAL)

**Claude Concepts**: Slash commands in `.claude/commands/`
**VSCode/Copilot Equivalents**: Prompt files (`.prompt.md`)

**Portable Commands**:

| Command | Portable? | Notes |
|---------|-----------|-------|
| pr-comment-responder.md | Yes | Already configured in Config.psd1 |
| pr-review.md | Yes | Generic PR review workflow |
| push-pr.md | Yes | Commit/push/PR creation |
| research.md | Partial | Uses extended thinking (Claude feature) |
| session-init.md | No | Claude session protocol specific |
| context-hub-setup.md | Partial | MCP tool dependencies |
| context_gather.md | Partial | MCP tool dependencies |
| memory-documentary.md | No | Forgetful MCP specific |
| forgetful/* | No | Forgetful MCP specific |

**Recommendation**: Add 3 portable commands as prompt files:

- pr-review.prompt.md
- push-pr.prompt.md
- research.prompt.md (adapted for non-Claude)

### Category 3: Skills (LOW PARITY POTENTIAL - PLATFORM LIMITATION)

**Claude Concept**: PowerShell modules in `.claude/skills/` with SKILL.md frontmatter

**VSCode/Copilot Reality**:

- VSCode Copilot: Supports MCP servers but NOT the Claude skills folder format
- Copilot CLI: Added skills support December 2025, but uses different format

**Analysis**: The `.claude/skills/` format (PowerShell modules with SKILL.md) is Claude Code specific. Porting would require:

1. Converting each skill to an MCP server (significant effort)
2. Documenting MCP server setup for each platform
3. Platform-specific installation scripts

**Recommendation**: Skills are NOT portable via the current installer. Document as a known limitation. The `github` skill scripts could be documented as standalone tools users can run manually.

### Category 4: Hooks (NO PARITY - PLATFORM LIMITATION)

**Claude Concept**: `settings.json` with hook matchers triggering PowerShell scripts

**Platform Reality**:

- VSCode: Has extension API hooks, NOT the same model
- Copilot CLI: No equivalent hook system

**Analysis**: Hooks are fundamentally Claude Code specific. They provide:

- PreToolUse guards (blocking gates)
- PostToolUse automation (markdown linting)
- SessionStart enforcement
- Permission auto-approval

**Recommendation**: Hooks are NOT portable. Document as a known limitation with workarounds:

- Pre-commit Git hooks can replace some PreToolUse guards
- CI workflows can replace PostToolUse validation
- Manual initialization replaces SessionStart hooks

### Category 5: Settings (NO PARITY - FORMAT INCOMPATIBLE)

**Claude Concept**: `.claude/settings.json` with hooks configuration and plugin enablement

**Platform Reality**:

- VSCode: Uses `.vscode/settings.json` with completely different schema
- Copilot CLI: Uses different configuration format

**Recommendation**: Settings are NOT portable. Each platform requires platform-specific configuration documentation.

## Milestones (Full Parity) [REMEDIATED]

### Milestone 0: Governance and License Research (4h) [REMEDIATED]

**Goal**: Create ADR-041, verify third-party agent licenses, create attribution file

#### Tasks

1. [ ] Create ADR-041: Prompts Artifact Type
   - Acceptance: ADR approved and merged
   - Files: `.agents/architecture/ADR-041-prompts-artifact-type.md`
   - Conditions: **BLOCKING** - Phase 3 cannot start without this
   - Effort: 2h

2. [ ] Research origin of debug.md, janitor.md, prompt-builder.md, technical-writer.md
   - Acceptance: Source repository or author identified for each with evidence trail
   - Files: N/A (research documented in THIRD-PARTY-LICENSES.txt)
   - Conditions: Check GitHub, VSCode marketplace, Anthropic repos; document search methodology
   - Effort: 1h

3. [ ] Verify all third-party agents are MIT licensed
   - Acceptance: License confirmed with URL/commit SHA, OR documented as "Original work"
   - Files: N/A (research)
   - Effort: 0.25h

4. [ ] Create `THIRD-PARTY-LICENSES.txt`
   - Acceptance: All third-party content attributed with license text and evidence
   - Files: `THIRD-PARTY-LICENSES.txt`
   - Effort: 0.5h

5. [ ] Update README.md with attribution section
   - Acceptance: Credits section added if third-party content included
   - Files: `README.md`
   - Effort: 0.25h

### Milestone 1: Add Missing Agents to Source (4h) [REMEDIATED]

**Goal**: Establish source files in `src/claude/` for all agents with content validation

#### Tasks

1. [ ] Copy adr-generator.md from .claude/agents/ to src/claude/
   - Acceptance: File exists with proper frontmatter
   - Files: `src/claude/adr-generator.md`
   - Effort: 0.25h

2. [ ] Copy context-retrieval.md from .claude/agents/ to src/claude/
   - Acceptance: File exists, MCP tool references documented
   - Files: `src/claude/context-retrieval.md`

3. [ ] Copy debug.md from .claude/agents/ to src/claude/
   - Acceptance: File exists with proper frontmatter
   - Files: `src/claude/debug.md`

4. [ ] Copy janitor.md from .claude/agents/ to src/claude/
   - Acceptance: File exists with proper frontmatter
   - Files: `src/claude/janitor.md`

5. [ ] Copy prompt-builder.md from .claude/agents/ to src/claude/
   - Acceptance: File exists with proper frontmatter
   - Files: `src/claude/prompt-builder.md`

6. [ ] Verify sync between .claude/agents/spec-generator.md and src/claude/spec-generator.md
   - Acceptance: Content aligned, differences documented if any
   - Files: `src/claude/spec-generator.md`
   - Conditions: Do NOT overwrite - compare and merge if needed

7. [ ] Copy technical-writer.md from .claude/agents/ to src/claude/
   - Acceptance: File exists with proper frontmatter
   - Files: `src/claude/technical-writer.md`

8. [ ] Update src/claude/AGENTS.md to include new agents
   - Acceptance: All 26 agents documented
   - Files: `src/claude/AGENTS.md`
   - Effort: 0.75h

9. [ ] **[NEW]** Validate user-facing content restrictions
   - Acceptance: No internal PR/Issue/Session references in any copied agent
   - Files: All files in `src/claude/` created in this milestone
   - Conditions: Run grep for patterns: `PR #\d+`, `Issue #\d+`, `Session \d+`
   - Effort: 0.5h

### Milestone 2: Create Shared Templates (20h) [REMEDIATED]

**Goal**: Create templates for all 7 missing agents with MCP audit

#### Tasks

1. [ ] Create `templates/agents/adr-generator.shared.md`
   - Acceptance: No mcp__serena__ or mcp__forgetful__ references; YAML frontmatter with tools_vscode/tools_copilot
   - Files: `templates/agents/adr-generator.shared.md`
   - Conditions: Remove Serena references
   - Effort: 2h

2. [ ] Create `templates/agents/context-retrieval.shared.md`
   - Acceptance: No mcp__* references except documented portable ones; degradation notice included
   - Files: `templates/agents/context-retrieval.shared.md`
   - Conditions: **[REMEDIATED]** Remove Forgetful, Serena, cloudmcp-manager (NOT portable); add degradation notice
   - Effort: **8h**

3. [ ] Create `templates/agents/debug.shared.md`
   - Acceptance: No vscode/ tool prefixes; no Claude-specific MCP references
   - Files: `templates/agents/debug.shared.md`
   - Conditions: Remove vscode-specific tool names if any
   - Effort: 1.5h

4. [ ] Create `templates/agents/janitor.shared.md`
   - Acceptance: No vscode/ tool prefixes; no Claude-specific MCP references
   - Files: `templates/agents/janitor.shared.md`
   - Conditions: None
   - Effort: 1.5h

5. [ ] Create `templates/agents/prompt-builder.shared.md`
   - Acceptance: No mcp__* tool syntax; uses path notation for tools
   - Files: `templates/agents/prompt-builder.shared.md`
   - Conditions: Remove Claude-specific tool syntax
   - Effort: 2h

6. [ ] Create `templates/agents/spec-generator.shared.md`
   - Acceptance: No mcp__serena__ references; document memory limitation
   - Files: `templates/agents/spec-generator.shared.md`
   - Conditions: Replace mcp__serena__ with file-based fallback
   - Effort: 2h

7. [ ] Create `templates/agents/technical-writer.shared.md`
   - Acceptance: No Claude-specific tool references; uses path notation
   - Files: `templates/agents/technical-writer.shared.md`
   - Conditions: Remove Claude-specific tool references
   - Effort: 2h

8. [ ] **[NEW]** Audit all templates for MCP patterns
   - Acceptance: Exhaustive scan complete; all blocked patterns removed
   - Files: All 7 templates created above
   - Conditions: Check patterns: mcp__*, vscode/*, Memory Router, cloudmcp-manager
   - Effort: 1h

9. [ ] Run `pwsh build/Generate-Agents.ps1`
   - Acceptance: 14 new files generated (7 for copilot-cli, 7 for vs-code-agents)
   - Files: `src/copilot-cli/*.agent.md`, `src/vs-code-agents/*.agent.md`
   - Effort: 0.5h

10. [ ] Validate with `pwsh build/Generate-Agents.ps1 -Validate`
    - Acceptance: Validation passes
    - Effort: 0.5h

### Milestone 3: Portable Prompts (3h) [REMEDIATED]

**Goal**: Create adapted prompt files for core workflows (VSCode only)

> **BLOCKING GATE**: ADR-041 must be approved before starting this milestone

#### Tasks

0. [ ] **[BLOCKING]** Verify ADR-041 approved
   - Acceptance: ADR-041 merged to main
   - Files: `.agents/architecture/ADR-041-prompts-artifact-type.md`
   - Conditions: Cannot proceed without approval

1. [ ] Create `templates/prompts/README.md`
   - Acceptance: Documents prompt file format, platform support (VSCode only), and usage
   - Files: `templates/prompts/README.md`
   - Effort: 0.5h

2. [ ] Create `templates/prompts/pr-review.prompt.md`
   - Acceptance: PR review workflow using gh CLI; no ultrathink, no skills references
   - Files: `templates/prompts/pr-review.prompt.md`
   - Conditions: Remove ultrathink, replace .claude/skills/* with gh commands
   - Effort: 1.5h

3. [ ] Create `templates/prompts/push-pr.prompt.md`
   - Acceptance: Commit/push/PR workflow using gh CLI
   - Files: `templates/prompts/push-pr.prompt.md`
   - Conditions: Replace .claude/skills/github/scripts/* with gh pr create
   - Effort: 1h

### Milestone 4: Installer Integration (2h)

**Goal**: Enable prompt installation via install.ps1

#### Tasks

1. [ ] Update `scripts/lib/Config.psd1`
   - Acceptance: PromptsSourceDir, PromptsDir, PromptFiles configured for Copilot and VSCode
   - Files: `scripts/lib/Config.psd1`

2. [ ] Update `scripts/lib/Install-Common.psm1` (if needed)
   - Acceptance: Install-PromptFiles handles templates/prompts/ with platform conditionals
   - Files: `scripts/lib/Install-Common.psm1`
   - Effort: 1.5h

3. [ ] **[NEW]** Add path traversal validation
   - Acceptance: Resolve-DestinationPath rejects paths containing `..`
   - Files: `scripts/lib/Install-Common.psm1`
   - Conditions: Security requirement
   - Effort: 0.5h

4. [ ] Test installation (VSCode repo scope)
   - Acceptance: Prompts installed to .github/prompts/
   - Files: N/A (manual test)
   - Effort: 0.25h

5. [ ] Test installation (Copilot CLI)
   - Acceptance: Document any failures due to blocking issues
   - Files: N/A (manual test)
   - Effort: 0.25h

### Milestone 5: Platform Validation (4h) [NEW]

**Goal**: Research blocking issues and validate platform compatibility

#### Tasks

1. [ ] Research Copilot CLI blocking issues beyond #452
   - Acceptance: Document #452, #760, #693, #687, #556 with status and impact
   - Files: `templates/PLATFORM-LIMITATIONS.md` (preliminary)
   - Effort: 1.5h

2. [ ] Smoke test: Invoke debug agent in VSCode Copilot
   - Acceptance: Agent loads without syntax errors; responds to basic prompt
   - Files: N/A (manual test)
   - Effort: 0.5h

3. [ ] Smoke test: Invoke debug agent in Copilot CLI
   - Acceptance: Document result (may fail due to blockers)
   - Files: N/A (manual test)
   - Effort: 0.5h

4. [ ] Create platform compatibility matrix
   - Acceptance: Table showing each agent's status per platform
   - Files: `templates/PLATFORM-LIMITATIONS.md`
   - Effort: 1h

5. [ ] Define extended test matrix
   - Acceptance: Beyond smoke tests; criteria for each agent
   - Files: `templates/PLATFORM-LIMITATIONS.md`
   - Effort: 0.5h

**Test Matrix Criteria**:

| Test | Required | Pass Criteria |
|------|----------|---------------|
| Agent parses without errors | Yes | No YAML/Markdown syntax errors |
| Agent responds to activation | Yes | Coherent response to "help me debug" |
| No blocked tool references | Yes | grep returns 0 matches for mcp__*, vscode/* |
| Handoff syntax works | Yes | @agent invocation succeeds (if applicable) |
| Memory tools documented | Yes | Limitation noted in agent header |

### Milestone 6: Documentation (4h) [REMEDIATED]

**Goal**: Document platform capabilities and limitations prominently

#### Tasks

1. [ ] Create `templates/PLATFORM-LIMITATIONS.md`
   - Acceptance: Documents hooks, skills, settings, Serena, memory incompatibilities with workarounds
   - Files: `templates/PLATFORM-LIMITATIONS.md`
   - Effort: 2h

**Required Sections**:
```markdown
# Platform Limitations

## Memory System
- Claude Code: Full (Serena + Forgetful)
- VSCode/Copilot CLI: None (no persistent memory)

## MCP Tools Availability
| Tool | Claude | VSCode | Copilot CLI |
|------|--------|--------|-------------|
| mcp__forgetful__* | Yes | No | No |
| mcp__serena__* | Yes | No | No |
| cloudmcp-manager | Yes | No | No |
| context7 | Yes | Partial | Partial |

## Hooks System
- Claude Code: 15+ hook scripts
- VSCode/Copilot CLI: No equivalent

## Skills Folder
- Claude Code: 32 skill directories
- VSCode/Copilot CLI: Not portable

## Agent Degradation
### context-retrieval
- Claude: 5-source strategy (Forgetful, Serena, Context7, DeepWiki, Web)
- Copilot: 2-source strategy (file system + web only)
```

2. [ ] Update `templates/README.md`
   - Acceptance: Feature matrix showing Claude vs VSCode vs Copilot capabilities (not "parity")
   - Files: `templates/README.md`
   - Effort: 1h

3. [ ] Update `templates/AGENTS.md`
   - Acceptance: All 25 agents documented with availability and degradation notes
   - Files: `templates/AGENTS.md`
   - Effort: 1h

### Final Milestone: Version Management (1h)

- [ ] Update CHANGELOG.md with compatibility improvements
- [ ] Version bump to v0.2.0
- [ ] Note: Changed from "parity" to "compatibility" language

## Work Breakdown Summary (Full Plan - Remediated)

| Phase | Task ID | Description | Effort | Conditions |
|-------|---------|-------------|--------|------------|
| 0 | M0-T1 | Create ADR-041 | 2h | **BLOCKING** |
| 0 | M0-T2 | Research agent origins | 1h | None |
| 0 | M0-T3 | Verify MIT licenses | 0.25h | After M0-T2 |
| 0 | M0-T4 | Create THIRD-PARTY-LICENSES.txt | 0.5h | After M0-T3 |
| 0 | M0-T5 | Update README.md | 0.25h | After M0-T4 |
| 1 | M1-T1..T7 | Copy 6 agents to src/claude/ | 1.75h | After M0 |
| 1 | M1-T8 | Update src/claude/AGENTS.md | 0.75h | After M1-T1..T7 |
| 1 | M1-T9 | Validate user-facing content | 0.5h | After M1-T8 |
| 2 | M2-T1 | Create adr-generator.shared.md | 2h | Remove Serena refs |
| 2 | M2-T2 | Create context-retrieval.shared.md | **8h** | Degraded mode |
| 2 | M2-T3 | Create debug.shared.md | 1.5h | None |
| 2 | M2-T4 | Create janitor.shared.md | 1.5h | None |
| 2 | M2-T5 | Create prompt-builder.shared.md | 2h | Remove mcp__* |
| 2 | M2-T6 | Create spec-generator.shared.md | 2h | Remove Serena |
| 2 | M2-T7 | Create technical-writer.shared.md | 2h | None |
| 2 | M2-T8 | Audit MCP patterns | 1h | All templates |
| 2 | M2-T9 | Run generation script | 0.5h | After M2-T1..T8 |
| 2 | M2-T10 | Validate generation | 0.5h | After M2-T9 |
| 3 | M3-T0 | Verify ADR-041 approved | 0h | **BLOCKING** |
| 3 | M3-T1 | Create prompts README | 0.5h | After ADR-041 |
| 3 | M3-T2 | Create pr-review.prompt.md | 1.5h | Replace Claude tools |
| 3 | M3-T3 | Create push-pr.prompt.md | 1h | Replace skills |
| 4 | M4-T1 | Update Config.psd1 | 1.5h | Platform-specific |
| 4 | M4-T2 | Update Install-Common.psm1 | 1.5h | Conditional prompts |
| 4 | M4-T3 | Add path traversal validation | 0.5h | Security |
| 4 | M4-T4..T5 | Test installation | 0.5h | After M4-T1..T3 |
| 5 | M5-T1 | Research Copilot CLI blockers | 1.5h | None |
| 5 | M5-T2..T3 | Smoke tests | 1h | After M2-T10 |
| 5 | M5-T4 | Platform compatibility matrix | 1h | After M5-T1..T3 |
| 5 | M5-T5 | Extended test matrix | 0.5h | After M5-T4 |
| 6 | M6-T1 | Create PLATFORM-LIMITATIONS.md | 2h | None |
| 6 | M6-T2 | Update templates/README.md | 1h | None |
| 6 | M6-T3 | Update templates/AGENTS.md | 1h | None |
| FM | FM-T1 | Version management | 1h | After all |
| | **Total** | | **43h** | |

## Rollback Plan [REMEDIATED]

If generated agents break existing functionality or introduce regressions:

### Immediate Rollback (< 5 min)

```powershell
# Revert template changes
git checkout HEAD~1 -- templates/agents/

# Regenerate from previous templates
pwsh build/Generate-Agents.ps1

# Verify generation
pwsh build/Generate-Agents.ps1 -Validate

# [NEW] Verify rollback succeeded
if ($LASTEXITCODE -eq 0) { Write-Host "[PASS] Rollback verified" }
```

### Partial Rollback (specific agent)

```powershell
# Revert specific template
git checkout HEAD~1 -- templates/agents/{agent-name}.shared.md

# Regenerate all (will use reverted template)
pwsh build/Generate-Agents.ps1

# Verify
pwsh build/Generate-Agents.ps1 -Validate
```

### Rollback Triggers

| Condition | Action |
|-----------|--------|
| Generated agent fails to load in VSCode | Revert that template, regenerate, verify |
| Generated agent fails to load in Copilot CLI | Revert that template, regenerate, verify |
| CI drift detection fails | Review diff, fix template or update baseline |
| User reports agent malfunction | Identify template, revert, regenerate |
| MCP pattern found in generated output | Audit, fix template, regenerate |

### Prevention

Before merging template changes:

1. Run `pwsh build/Generate-Agents.ps1 -Validate`
2. Grep for blocked patterns: `grep -r "mcp__" src/copilot-cli/ src/vs-code-agents/`
3. Test one generated agent manually in VSCode
4. Test one generated agent manually in Copilot CLI (document if blocked)
5. Verify CI passes

---

## Assumptions [REMEDIATED]

| Assumption | Status | Evidence |
|------------|--------|----------|
| VSCode supports `.prompt.md` in .github/prompts/ | **VERIFIED** | Context7 docs, GitHub blog |
| Copilot CLI supports `.agent.md` in .github/agents/ | **VERIFIED** | Config.psd1 uses this path |
| Copilot CLI does NOT support separate prompts | **VERIFIED** | Analyst investigation |
| `gh` CLI provides sufficient PR functionality | **ASSUMED** | Needs verification |
| cloudmcp-manager works across platforms | **INVALIDATED** | Analyst: NOT portable |
| Users have PowerShell 7.0+ | **ASSUMED** | Standard prerequisite |

## Open Questions [RESOLVED]

| Question | Resolution |
|----------|------------|
| Memory Tool Portability | **cloudmcp-manager is NOT portable**. No persistent memory on Copilot platforms. |
| Prompt File Location | **VSCode: .github/prompts/**, **CLI: none**. Prompts are VSCode-only. |
| MCP Server Availability | **Most are Claude-only**. Document each tool's status in PLATFORM-LIMITATIONS.md. |
| Agent Frontmatter Differences | Documented in `templates/platforms/copilot-cli.yaml` and `templates/platforms/vscode.yaml` |

## Risks [REMEDIATED]

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| context-retrieval becomes near-useless | **HIGH** | HIGH | Document as "degraded mode" prominently |
| Copilot CLI has undiscovered blockers | MEDIUM | HIGH | M5-T1: Research before heavy investment |
| MCP tool differences between platforms | **HIGH** | HIGH | Exhaustive audit in M2-T8 |
| Memory protocol unavailable | **CERTAIN** | MEDIUM | Accept no memory; document limitation |
| Agent adaptation effort underestimated | MEDIUM | MEDIUM | Start with simple agents; buffer added |
| Template drift after initial sync | LOW | LOW | Weekly drift detection CI exists |
| ADR-041 delayed/rejected | LOW | MEDIUM | Phase 3 blocked; other phases proceed |

## Not In Scope (Platform Limitations)

The following Claude Code features cannot be ported due to platform limitations:

### Hooks System

Claude Code hooks (`PreToolUse`, `PostToolUse`, `SessionStart`, etc.) have no equivalent in VSCode or Copilot CLI. Workarounds:

- Use Git pre-commit hooks for code validation
- Use CI workflows for post-push checks
- Use manual checklist for session initialization

### Serena Integration

Serena memory and symbol tools are Claude Code exclusive. No workaround available; users must use alternative memory solutions.

### Skills Folder Format

The `.claude/skills/` format with SKILL.md frontmatter is Claude-specific. The PowerShell scripts within skills (e.g., `github/scripts/`) can be used standalone but require manual invocation.

### Settings Configuration

`.claude/settings.json` format is incompatible with other platforms. Each platform requires its own configuration approach.

### Context Retrieval Agent

The context-retrieval agent is included in this plan but requires significant adaptation:

- Forgetful MCP references replaced with cloudmcp-manager or generic memory tools
- Five-source strategy may need platform-specific alternatives
- Core workflow (gather context before implementation) is portable

---

## Cross-Reference: Related Issue 858 (Codex CLI Compatibility)

**Note**: Issue 858 analyzes Codex CLI compatibility separately. Key differences from this plan:

### Codex CLI vs Copilot CLI

| Aspect | Codex CLI | Copilot CLI | Relevance |
|--------|-----------|-------------|-----------|
| Configuration Scope | Repository-level | User-level only | Codex better for teams |
| MCP Support | Similar to Claude | Limited | Codex closer to Claude |
| Open Source | Yes | No | Codex more extensible |
| Air-gapped Support | Yes | No | Enterprise consideration |

### Implications for This Plan

1. **Template approach applies**: The `templates/agents/` pattern could extend to Codex CLI
2. **Platform config needed**: Would require `templates/platforms/codex.yaml`
3. **Installer update**: `scripts/install.ps1` would need Codex environment support
4. **Skills may port**: Codex CLI's open-source nature may allow skill porting

### Deferred to Issue 858

- Codex CLI platform configuration
- Codex CLI installer integration
- Codex-specific prompt syntax transformations
- Codex compatibility testing

**Recommendation**: Coordinate with Issue 858 analysis to avoid duplication. This plan focuses on VSCode and Copilot CLI; Codex is out of scope but shares similar architecture patterns.

---

## Validation Summary [REMEDIATED - Post-Multi-Agent Review]

| Check | Original | Remediated | Finding |
|-------|----------|------------|---------|
| Strategic alignment | [PASS] | [PASS] | Prioritizes unlimited Copilot; accepts degradation |
| Agent scope | [FAIL] | [PASS] | Corrected: 7 agents (AGENTS.md is documentation) |
| Command portability | [PASS] | [PASS] | 2 prompts, VSCode only (CLI no prompts) |
| Effort justification | [FAIL] | [PASS] | Corrected: 43h (was 28.5h) |
| ADR-036 compliance | [PASS] | [PASS] | Two-source architecture maintained |
| ADR-041 requirement | N/A | [PASS] | **[NEW]** Required for prompts artifact |
| License handling | [FAIL] | [PASS] | Extended to 2h with evidence trail |
| cloudmcp-manager | [FAIL] | [PASS] | Documented as NOT portable |
| Memory availability | [FAIL] | [PASS] | Documented as unavailable on Copilot |
| Rollback plan | [WARN] | [PASS] | Added verification step |
| Acceptance criteria | [PASS] | [PASS] | Measurable criteria + MCP audit |
| Platform validation | N/A | [PASS] | **[NEW]** Phase 5 added |
| Security review | [FAIL] | [PASS] | Path traversal, content validation added |

### Blocking Gates Summary

| Gate | Phase | Status |
|------|-------|--------|
| ADR-041 approved | Before Phase 3 | [PENDING] |
| License research complete | Phase 0 | [PENDING] |
| User-facing content validated | Phase 1 | [PENDING] |
| MCP pattern audit complete | Phase 2 | [PENDING] |

### Specialist Agent Feedback Incorporated

| Agent | Verdict | Key Remediation |
|-------|---------|-----------------|
| Critic | APPROVE WITH CONDITIONS | Agent count, cloudmcp-manager, testing |
| Architect | ADR-041 REQUIRED | Prompts artifact type governance |
| Independent-Thinker | Premise challenged | Changed "parity" to "compatibility" language |
| Analyst | Claims invalidated | cloudmcp-manager, Copilot CLI blockers |
| Security | CONDITIONAL | License due diligence, path traversal |
| High-Level-Advisor | DEFER recommended | User chose to proceed; risks documented |
| Roadmap | Strategic concerns | Degradation documented prominently |
| Planner | Revised estimates | 43h total with all fixes |

**Verdict**: Full compatibility plan approved with remediations. 43h effort to enable Claude Code agents on Copilot platforms with documented degradation.

**Key Caveats**:
1. This is **compatibility**, not **parity** - 60% of Claude power does not port
2. **context-retrieval** operates in degraded mode (no persistent memory)
3. **Copilot CLI** has 5+ blocking issues beyond #452
4. **Memory system** unavailable on all non-Claude platforms

---

*Plan revised 2026-01-14 (Post-Multi-Agent Review). Ready for implementation with documented limitations.*
