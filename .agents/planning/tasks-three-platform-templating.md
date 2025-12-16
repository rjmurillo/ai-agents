# Task Breakdown: Three-Platform Template Generation

## Source

- Plan: `.agents/planning/001-three-platform-templating-plan.md`
- ADR: `.agents/architecture/ADR-001-three-platform-template-generation.md`
- Design: `.agents/architecture/claude-platform-config-design.md`

## Summary

| Complexity | Count |
|------------|-------|
| XS | 4 |
| S | 8 |
| M | 5 |
| L | 2 |
| XL | 0 |
| **Total** | **19** |

---

## Tasks

### Milestone 1: Platform Configuration

**Goal**: Create Claude platform config and verify pipeline structure

---

#### Task: Create claude.yaml Platform Configuration

**ID**: TASK-001
**Type**: Feature
**Complexity**: S

**Description**
Create `templates/platforms/claude.yaml` following the pattern established by vscode.yaml and copilot-cli.yaml.

**Acceptance Criteria**
- [ ] File created at `templates/platforms/claude.yaml`
- [ ] Contains: platform, outputDir, fileExtension, frontmatter, sections
- [ ] `platform: claude` set correctly
- [ ] `outputDir: src/claude` set correctly
- [ ] `fileExtension: .md` set correctly
- [ ] `frontmatter.model: "opus"` set correctly
- [ ] `frontmatter.includeNameField: true` set correctly
- [ ] `sections.injectClaudeCodeTools: true` set correctly

**Dependencies**
- None

**Files Affected**
- `templates/platforms/claude.yaml`: Create new

---

#### Task: Verify Config Parsing

**ID**: TASK-002
**Type**: Chore
**Complexity**: XS

**Description**
Verify that `Read-PlatformConfig` in Generate-Agents.ps1 correctly parses claude.yaml.

**Acceptance Criteria**
- [ ] Script loads claude.yaml without errors
- [ ] All config values accessible as expected

**Dependencies**
- TASK-001: Requires claude.yaml to exist

**Files Affected**
- None (verification only)

---

### Milestone 2: Script Extensions

**Goal**: Extend Generate-Agents.ps1 to support Claude platform

---

#### Task: Implement Get-ClaudeToolsSection Function

**ID**: TASK-003
**Type**: Feature
**Complexity**: M

**Description**
Create PowerShell function that generates the `## Claude Code Tools` section markdown based on template frontmatter.

**Acceptance Criteria**
- [ ] Function accepts Frontmatter hashtable and AgentName
- [ ] If `claude_tools_section` in frontmatter, return it directly
- [ ] If not, generate default section from `tools_claude` array
- [ ] Output is valid markdown with tool descriptions
- [ ] Supports all common tools (Read, Grep, Glob, Bash, Write, Edit, WebSearch, WebFetch)

**Dependencies**
- None (can be developed independently)

**Files Affected**
- `build/Generate-Agents.ps1`: Add function

---

#### Task: Implement Convert-PathToMcpSyntax Function

**ID**: TASK-004
**Type**: Feature
**Complexity**: S

**Description**
Create PowerShell function that transforms path-style tool references to MCP syntax in markdown body.

**Acceptance Criteria**
- [ ] Function accepts Body string
- [ ] Converts `cognitionai/deepwiki/*` to `mcp__deepwiki__*`
- [ ] Converts `cloudmcp-manager/*` patterns to `mcp__cloudmcp-manager__*`
- [ ] Handles both inline and code block references
- [ ] Returns transformed body

**Dependencies**
- None (can be developed independently)

**Files Affected**
- `build/Generate-Agents.ps1`: Add function

---

#### Task: Implement Insert-ClaudeToolsSection Function

**ID**: TASK-005
**Type**: Feature
**Complexity**: M

**Description**
Create PowerShell function that injects the Claude Code Tools section at the correct position in the markdown body.

**Acceptance Criteria**
- [ ] Function accepts Body and ToolsSection strings
- [ ] Inserts section after `# Agent Name` header
- [ ] Inserts section before `## Core Identity` or `## Core Mission`
- [ ] Maintains proper spacing and formatting
- [ ] Returns modified body

**Dependencies**
- TASK-003: Uses output of Get-ClaudeToolsSection

**Files Affected**
- `build/Generate-Agents.ps1`: Add function

---

#### Task: Update Platform Processing Loop for Claude

**ID**: TASK-006
**Type**: Feature
**Complexity**: M

**Description**
Modify the main platform processing loop in Generate-Agents.ps1 to apply Claude-specific transformations.

**Acceptance Criteria**
- [ ] Detects when processing Claude platform
- [ ] Calls Get-ClaudeToolsSection for Claude
- [ ] Calls Insert-ClaudeToolsSection for Claude
- [ ] Calls Convert-PathToMcpSyntax for Claude
- [ ] Claude frontmatter does NOT include tools array
- [ ] Other platforms unchanged

**Dependencies**
- TASK-001: Requires claude.yaml
- TASK-003: Requires Get-ClaudeToolsSection
- TASK-004: Requires Convert-PathToMcpSyntax
- TASK-005: Requires Insert-ClaudeToolsSection

**Files Affected**
- `build/Generate-Agents.ps1`: Modify main loop

---

#### Task: Update Format-FrontmatterYaml for Claude

**ID**: TASK-007
**Type**: Feature
**Complexity**: S

**Description**
Ensure frontmatter formatting handles Claude's requirements (name required, no tools array).

**Acceptance Criteria**
- [ ] Claude output has `name:` field
- [ ] Claude output has `description:` field
- [ ] Claude output has `model:` field (value "opus")
- [ ] Claude output does NOT have `tools:` field
- [ ] Field order matches existing Claude agents

**Dependencies**
- TASK-001: Requires claude.yaml config

**Files Affected**
- `build/Generate-Agents.ps1`: Modify Format-FrontmatterYaml or Convert-FrontmatterForPlatform

---

### Milestone 3: Template Updates

**Goal**: Update all 18 templates with Claude-specific fields

---

#### Task: Define tools_claude Arrays for All Templates

**ID**: TASK-008
**Type**: Feature
**Complexity**: L

**Description**
Add `tools_claude` field to all 18 template frontmatters with appropriate tool lists for each agent.

**Acceptance Criteria**
- [ ] All 18 templates have `tools_claude` field
- [ ] Tool lists match current Claude agents' capabilities
- [ ] Array syntax correct (JSON array in YAML)

**Dependencies**
- None (can parallel with script work)

**Files Affected**
- `templates/agents/analyst.shared.md`
- `templates/agents/architect.shared.md`
- `templates/agents/critic.shared.md`
- `templates/agents/devops.shared.md`
- `templates/agents/explainer.shared.md`
- `templates/agents/high-level-advisor.shared.md`
- `templates/agents/implementer.shared.md`
- `templates/agents/independent-thinker.shared.md`
- `templates/agents/memory.shared.md`
- `templates/agents/orchestrator.shared.md`
- `templates/agents/planner.shared.md`
- `templates/agents/pr-comment-responder.shared.md`
- `templates/agents/qa.shared.md`
- `templates/agents/retrospective.shared.md`
- `templates/agents/roadmap.shared.md`
- `templates/agents/security.shared.md`
- `templates/agents/skillbook.shared.md`
- `templates/agents/task-generator.shared.md`

---

#### Task: Add Custom claude_tools_section Where Needed

**ID**: TASK-009
**Type**: Feature
**Complexity**: S

**Description**
For agents needing custom Claude Code Tools sections (beyond default generation), add `claude_tools_section` to frontmatter.

**Acceptance Criteria**
- [ ] Agents with specialized tool needs have custom sections
- [ ] Custom sections match current Claude agent content
- [ ] Multiline YAML strings properly formatted

**Dependencies**
- TASK-008: Should know which agents need custom sections

**Files Affected**
- Selected templates (based on audit)

---

#### Task: Replace Hardcoded Platform Content with Placeholders

**ID**: TASK-010
**Type**: Chore
**Complexity**: S

**Description**
Audit templates for hardcoded platform-specific content and replace with placeholders or conditional markers.

**Acceptance Criteria**
- [ ] No hardcoded `mcp__` prefixes in shared content
- [ ] No hardcoded `cloudmcp-manager/` paths in shared content
- [ ] Placeholders like `{{MEMORY_PREFIX}}` used consistently
- [ ] Tool syntax agnostic in shared sections

**Dependencies**
- None (audit and update)

**Files Affected**
- Various templates (based on audit)

---

### Milestone 4: Content Migration

**Goal**: Merge valuable Claude-specific content into templates

---

#### Task: Audit Claude Agents for Unique Content

**ID**: TASK-011
**Type**: Spike
**Complexity**: M

**Description**
Compare each Claude agent to its template counterpart and identify content unique to Claude that should be preserved.

**Acceptance Criteria**
- [ ] All 18 agents compared
- [ ] Unique content documented per agent
- [ ] Content categorized: preserve / discard / merge

**Dependencies**
- TASK-008: Templates should have structure in place

**Files Affected**
- Documentation only (audit report)

---

#### Task: Merge Preserved Content into Templates

**ID**: TASK-012
**Type**: Feature
**Complexity**: L

**Description**
Based on audit, merge valuable Claude-specific content into templates so generated output retains it.

**Acceptance Criteria**
- [ ] All preserved content merged
- [ ] Content placed in appropriate sections
- [ ] No duplication with existing template content
- [ ] Template remains platform-agnostic

**Dependencies**
- TASK-011: Requires audit results

**Files Affected**
- Various templates (based on audit)

---

#### Task: Verify No Semantic Loss

**ID**: TASK-013
**Type**: Chore
**Complexity**: S

**Description**
After merging, verify that generated Claude agents have same semantic capabilities as current agents.

**Acceptance Criteria**
- [ ] Generated agents have all tool documentation
- [ ] Memory protocol sections complete
- [ ] Handoff options complete
- [ ] Constraints sections complete
- [ ] No missing sections

**Dependencies**
- TASK-012: Requires content merge complete

**Files Affected**
- None (verification only)

---

### Milestone 5: Validation & Cleanup

**Goal**: Validate generated output and update documentation

---

#### Task: Run Full Generation and Verify Output

**ID**: TASK-014
**Type**: Chore
**Complexity**: S

**Description**
Execute Generate-Agents.ps1 and verify all 54 files generated correctly.

**Acceptance Criteria**
- [ ] Script runs without errors
- [ ] 18 files in `src/claude/`
- [ ] 18 files in `src/vs-code-agents/`
- [ ] 18 files in `src/copilot-cli/`
- [ ] All files have correct structure

**Dependencies**
- TASK-006: Script must support Claude
- TASK-012: Templates must have content

**Files Affected**
- All generated files (54 total)

---

#### Task: Fix Discrepancies in Generated Output

**ID**: TASK-015
**Type**: Bug
**Complexity**: M

**Description**
Address any issues found during validation - formatting, missing content, incorrect transforms.

**Acceptance Criteria**
- [ ] All validation issues resolved
- [ ] Generated files match expected output
- [ ] No regressions in VS Code/Copilot output

**Dependencies**
- TASK-014: Requires initial validation

**Files Affected**
- `build/Generate-Agents.ps1` or templates (based on issues)

---

#### Task: Update templates/README.md

**ID**: TASK-016
**Type**: Chore
**Complexity**: XS

**Description**
Update documentation to reflect 3-platform architecture.

**Acceptance Criteria**
- [ ] Generation flow diagram updated
- [ ] Claude platform documented
- [ ] Drift detection section removed/updated
- [ ] Usage instructions current

**Dependencies**
- TASK-014: System must be working

**Files Affected**
- `templates/README.md`

---

#### Task: Update CI Workflow for 3 Platforms

**ID**: TASK-017
**Type**: Feature
**Complexity**: XS

**Description**
Ensure CI workflow validates all 54 generated files.

**Acceptance Criteria**
- [ ] CI runs `Generate-Agents.ps1 -Validate`
- [ ] Validation covers all 3 platforms
- [ ] Failure if any file differs

**Dependencies**
- TASK-014: Generation must work

**Files Affected**
- `.github/workflows/validate-generated-agents.yml`

---

#### Task: Remove Obsolete Drift Detection

**ID**: TASK-018
**Type**: Chore
**Complexity**: XS

**Description**
Remove or archive drift detection script and workflow (no longer needed when all platforms are generated).

**Acceptance Criteria**
- [ ] `build/scripts/Detect-AgentDrift.ps1` removed or archived
- [ ] `.github/workflows/drift-detection.yml` removed or archived
- [ ] `templates/README.md` drift section removed

**Dependencies**
- TASK-014: Must confirm 3-platform generation works

**Files Affected**
- `build/scripts/Detect-AgentDrift.ps1`
- `.github/workflows/drift-detection.yml`
- `templates/README.md`

---

#### Task: Delete Manual Claude Agent Files

**ID**: TASK-019
**Type**: Chore
**Complexity**: XS

**Description**
After verifying generated Claude agents work, delete the old manual files (they'll be regenerated).

**Acceptance Criteria**
- [ ] Old `src/claude/*.md` files committed as deletions
- [ ] New generated files committed
- [ ] Git history shows transition

**Dependencies**
- TASK-014: Generation must work
- TASK-013: Semantic verification complete

**Files Affected**
- `src/claude/*.md` (18 files)

---

## Dependency Graph

```text
TASK-001 (claude.yaml)
    |
    +---> TASK-002 (verify parsing)
    |
    +---> TASK-006 (loop update)
              |
              +---> TASK-003 (Get-ClaudeToolsSection)
              +---> TASK-004 (Convert-PathToMcpSyntax)
              +---> TASK-005 (Insert-ClaudeToolsSection)
              +---> TASK-007 (frontmatter format)

TASK-008 (tools_claude arrays)
    |
    +---> TASK-009 (custom sections)
    +---> TASK-010 (placeholders)
    +---> TASK-011 (audit)
              |
              +---> TASK-012 (merge content)
                        |
                        +---> TASK-013 (verify no loss)

TASK-006 + TASK-012 --> TASK-014 (full generation)
    |
    +---> TASK-015 (fix discrepancies)
    +---> TASK-016 (update README)
    +---> TASK-017 (update CI)
    +---> TASK-018 (remove drift detection)
    +---> TASK-019 (delete manual files)
```

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Section injection regex fails on edge cases | Medium | Test against all 18 templates |
| MCP syntax transform misses patterns | Medium | Audit all Claude agents for patterns |
| Custom tool sections get out of sync | Low | Document which agents have custom sections |

---

**Task Breakdown By**: Task Generator (methodology applied by orchestrator)
**Date**: 2025-12-15
