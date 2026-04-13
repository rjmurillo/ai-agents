# Architecture Review: 2-Variant Agent Consolidation

**Reviewer**: Architect Agent
**Date**: 2025-12-15
**Documents Reviewed**:
- `.agents/roadmap/epic-agent-consolidation.md`
- `.agents/planning/prd-agent-consolidation.md`
- `.agents/planning/tasks-agent-consolidation.md`

---

## Verdict: **Approved**

The proposed design is architecturally sound and aligns well with existing project patterns. Minor recommendations are provided below but do not block implementation.

---

## Review Summary

| Aspect | Assessment | Notes |
|--------|------------|-------|
| Design Patterns | Sound | Build-time generation is appropriate for this use case |
| File Structure | Appropriate | `templates/` directory follows logical separation |
| Build Script | Consistent | PowerShell aligns with existing `build/scripts/` patterns |
| Extensibility | Good | Platform configuration files enable future platforms |
| Project Consistency | Strong | Matches existing PowerShell, ADR, and CI patterns |

---

## Detailed Review

### 1. Design Patterns: Build-Time Generation

**Assessment**: Sound

**Rationale**:
- Build-time generation is the correct architectural choice for this problem. The VS Code and Copilot CLI variants differ only in YAML frontmatter and minor syntax transformations, making template-based generation appropriate.
- This approach follows the DRY principle without introducing runtime complexity.
- The decision to defer runtime generation is correct -- the overhead would not justify the benefit.

**Validated Against Principles**:
- **Simplicity**: Simple script transforms source to outputs; no complex templating engine required
- **Testability**: Generated outputs can be diffed against known-good files
- **Separation**: Clear boundary between source (`templates/`) and generated (`src/`) files

**No ADR Required**: This is an implementation pattern, not a significant architectural decision. The existing codebase already uses build-time generation for installation scripts.

---

### 2. File Structure: `templates/` Directory

**Assessment**: Appropriate

**Proposed Structure**:
```text
templates/
  agents/
    *.shared.md
  platforms/
    vscode.yaml
    copilot-cli.yaml
  README.md
```

**Strengths**:
- Clear separation between agent sources and platform configurations
- Naming convention (`*.shared.md`) distinguishes sources from outputs
- Platform configs as YAML files enable declarative configuration without code changes

**Recommendation**: The structure is sound. Consider adding a `.generated` marker file or comment header in generated files to prevent accidental edits.

---

### 3. Build Script: PowerShell Generator

**Assessment**: Consistent with Project Patterns

**Evidence of Alignment**:
- Existing scripts use PowerShell (`build/scripts/Invoke-PesterTests.ps1`)
- Script follows existing conventions:
  - `-Verbose` and `-WhatIf` parameters (standard PowerShell)
  - Clear header documentation
  - Exit codes for CI integration

**Minor Concern**: The PRD mentions `PowerShell-Yaml` module as an external dependency. This introduces a dependency that may not be present in all environments.

**Recommendation**: Document the dependency clearly in the script header and provide fallback regex parsing for environments without `PowerShell-Yaml`. Alternatively, consider using built-in `ConvertFrom-StringData` for simple key-value frontmatter parsing.

---

### 4. Extensibility: Future Platform Support

**Assessment**: Good

**Evidence**:
- Platform configuration files (`vscode.yaml`, `copilot-cli.yaml`) are decoupled from the build script
- Adding a new platform requires only:
  1. New platform config file
  2. Output directory creation
- No code changes required for new platforms with similar structure

**Future Consideration**: If a third platform (e.g., JetBrains, Neovim) is added with significantly different requirements, the build script may need refactoring. This is an acceptable tradeoff for the current 2-variant scope.

---

### 5. Consistency with Existing Patterns

**Assessment**: Strong Alignment

| Pattern | Existing | Proposed | Match |
|---------|----------|----------|-------|
| Script location | `build/scripts/*.ps1` | `build/Generate-Agents.ps1` | Yes |
| Output format | `.md` files with YAML frontmatter | Same | Yes |
| CI validation | GitHub Actions | Same | Yes |
| Documentation | `README.md` in directories | `templates/README.md` | Yes |
| Test location | `build/tests/*.Tests.ps1` | `build/tests/Generate-Agents.Tests.ps1` | Yes |

**Verified Against Existing Files**:
- VS Code agent format matches proposed generated format
- Copilot CLI agent format matches proposed generated format
- Existing differences are accurately documented in PRD Appendix A

---

## Observations

### Platform Differences Verified

I compared `src/vs-code-agents/analyst.agent.md` and `src/copilot-cli/analyst.agent.md`. The differences match the PRD documentation:

| Element | VS Code | Copilot CLI |
|---------|---------|-------------|
| `name` field | Absent | Present |
| `model` field | Present | Absent |
| `tools` array | VS Code extensions | Shell-based tools |
| Content body | Identical | Identical |

This confirms the 99%+ content overlap assumption is valid.

---

## Recommendations (Non-Blocking)

### 1. Generated File Header Comment

Add a header comment to generated files to prevent accidental edits:

```yaml
---
# AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY
# Source: templates/agents/analyst.shared.md
# Generated by: build/Generate-Agents.ps1
# To modify, edit the source file and regenerate
---
```

This aligns with common practices for generated code.

### 2. CI Fail-Fast Behavior

The PRD specifies that generated file validation should fail the PR if differences are detected. Consider adding a `--fix` mode to the build script that regenerates and commits (for local development), while CI remains strict.

### 3. Drift Detection Granularity

The drift detection script should output machine-readable JSON with section-level granularity. This enables future automation to highlight specific sections in the GitHub issue body.

---

## ADR Alignment

| ADR | Status | Notes |
|-----|--------|-------|
| ADR-001-markdown-linting | Aligns | Generated files must comply with markdown linting rules |

No new ADRs are required for this implementation. The design follows established patterns and does not introduce novel architectural decisions.

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation in Plan |
|------|-------------|--------|-------------------|
| Generated files edited directly | Medium | Low | CI validation (TASK-014) |
| PowerShell-Yaml unavailable | Low | Medium | Document in script, provide fallback |
| Drift detection false positives | Medium | Low | Configurable threshold, 90-day tuning |
| Build script complexity grows | Low | Medium | Keep transformations simple |

All identified risks have adequate mitigations in the implementation plan.

---

## Conclusion

The 2-Variant Agent Consolidation design is architecturally sound and ready for implementation. The approach:

1. **Reduces maintenance burden** by 33% (54 files to 36 unique sources)
2. **Aligns with existing patterns** for PowerShell scripts, CI workflows, and file structure
3. **Enables future extensibility** through declarative platform configurations
4. **Maintains separation of concerns** between source, configuration, and generated outputs

**Handoff**: Route to **critic** for plan validation, then proceed to **implementer** for Phase 1.

---

*Generated by Architect Agent*
