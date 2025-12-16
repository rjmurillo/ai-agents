# Plan: Three-Platform Template Generation

## Overview

Implement three-platform template generation where `templates/agents/*.shared.md` serves as the single source of truth, generating agent files for Claude, VS Code, and Copilot CLI platforms.

## Objectives

- [ ] Templates are the single source of truth (18 shared files)
- [ ] Generate all 54 agent files from templates (18 x 3 platforms)
- [ ] Eliminate drift by design
- [ ] CI validates generated files match templates

## Scope

### In Scope

- Create `templates/platforms/claude.yaml` configuration
- Extend `Generate-Agents.ps1` with Claude-specific transforms
- Add `tools_claude` and `claude_tools_section` to all 18 templates
- Merge valuable Claude-specific content into templates
- Update CI validation for 3 platforms

### Out of Scope

- Runtime platform detection (rejected alternative)
- Keeping Claude agents manual (failed 2-variant approach)
- New agent creation
- Agent behavioral changes

## Milestones

### Milestone 1: Platform Configuration

**Goal**: Create Claude platform config and verify pipeline structure

**Deliverables**:
- [ ] `templates/platforms/claude.yaml` created
- [ ] Config follows existing pattern from vscode.yaml/copilot-cli.yaml
- [ ] Platform-specific settings defined (model, fileExtension, memoryPrefix)

**Acceptance Criteria**:
- [ ] Config file parses correctly by `Read-PlatformConfig`
- [ ] All required fields present (platform, outputDir, fileExtension, frontmatter, sections)

**Dependencies**: None

**Effort**: 0.5 hours

---

### Milestone 2: Script Extensions

**Goal**: Extend Generate-Agents.ps1 to support Claude platform

**Deliverables**:
- [ ] `Get-ClaudeToolsSection` function implemented
- [ ] `Convert-PathToMcpSyntax` function implemented
- [ ] `Insert-ClaudeToolsSection` function implemented
- [ ] Platform processing loop updated for Claude

**Acceptance Criteria**:
- [ ] Script generates Claude output to `src/claude/`
- [ ] Generated files have `.md` extension
- [ ] Generated files have `name:`, `model: opus` frontmatter
- [ ] Generated files have `## Claude Code Tools` section
- [ ] MCP syntax (`mcp__*`) used throughout

**Dependencies**: Milestone 1

**Effort**: 3-4 hours

---

### Milestone 3: Template Updates

**Goal**: Update all 18 templates with Claude-specific fields

**Deliverables**:
- [ ] `tools_claude` field added to all 18 template frontmatters
- [ ] `claude_tools_section` added where custom content needed
- [ ] Existing template content reviewed for Claude compatibility
- [ ] Path-style tool references use placeholders

**Acceptance Criteria**:
- [ ] All templates have valid `tools_claude` arrays
- [ ] Template content is platform-agnostic (no hardcoded platform specifics)
- [ ] Placeholders used for platform-variable content

**Dependencies**: None (can parallel with Milestone 2)

**Effort**: 2-3 hours

---

### Milestone 4: Content Migration

**Goal**: Merge valuable Claude-specific content into templates

**Deliverables**:
- [ ] Audit current Claude agents for unique content
- [ ] Identify content to preserve vs. discard
- [ ] Merge preserved content into templates
- [ ] Verify no semantic loss

**Acceptance Criteria**:
- [ ] No functional capability lost in generated Claude agents
- [ ] Claude Code Tools sections match current agents
- [ ] Tool syntax and examples preserved
- [ ] Memory protocol documentation preserved

**Dependencies**: Milestone 2, Milestone 3

**Effort**: 4-6 hours

---

### Milestone 5: Validation & Cleanup

**Goal**: Validate generated output and update documentation

**Deliverables**:
- [ ] Run `Generate-Agents.ps1` and verify 54 files generated
- [ ] Compare generated Claude agents to current agents
- [ ] Fix any discrepancies
- [ ] Update `templates/README.md`
- [ ] Update CI workflow for 3 platforms
- [ ] Remove drift detection (obsolete)

**Acceptance Criteria**:
- [ ] `Generate-Agents.ps1 -Validate` passes
- [ ] CI validates all 54 generated files
- [ ] Documentation reflects 3-platform architecture
- [ ] No manual Claude agent files remain

**Dependencies**: Milestone 4

**Effort**: 2-3 hours

---

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Claude agents lose functionality | Medium | High | Detailed content audit in Milestone 4 |
| Script complexity increases significantly | Low | Medium | Follow existing patterns, modular functions |
| Contributors confused by template system | Medium | Low | Update documentation, add contributor guide |
| CI validation becomes slow | Low | Low | Parallel validation, incremental checks |

## Dependencies

- Existing `Generate-Agents.ps1` (works)
- Existing platform configs (vscode.yaml, copilot-cli.yaml)
- 18 shared templates (already exist)

## Technical Approach

1. **Follow existing patterns**: Claude config mirrors vscode.yaml structure
2. **Modular functions**: Each transform is a separate function
3. **Testable transforms**: Each function can be unit tested
4. **Backward compatible**: VS Code/Copilot generation unchanged

## Work Breakdown Summary

| Milestone | Effort | Dependencies |
|-----------|--------|--------------|
| 1. Platform Configuration | 0.5 hrs | None |
| 2. Script Extensions | 3-4 hrs | M1 |
| 3. Template Updates | 2-3 hrs | None |
| 4. Content Migration | 4-6 hrs | M2, M3 |
| 5. Validation & Cleanup | 2-3 hrs | M4 |
| **Total** | **12-17 hrs** | |

## Success Criteria

How we know the plan is complete:

- [ ] `pwsh build/Generate-Agents.ps1` produces 54 files without errors
- [ ] `pwsh build/Generate-Agents.ps1 -Validate` passes in CI
- [ ] All Claude agents work correctly (manual verification)
- [ ] No drift detection needed (templates are source of truth)
- [ ] Documentation updated to reflect 3-platform architecture

---

## References

- ADR: `.agents/architecture/ADR-001-three-platform-template-generation.md`
- Design Spec: `.agents/architecture/claude-platform-config-design.md`
- Independent Thinker Review: `.agents/analysis/independent-thinker-review-three-platform.md`
- High-Level Advisor Verdict: `.agents/analysis/high-level-advisor-verdict-three-platform.md`

---

**Plan By**: Planner (methodology applied by orchestrator)
**Date**: 2025-12-15
