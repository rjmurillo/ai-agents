# PRD: 2-Variant Agent Consolidation

**Version**: 1.0
**Date**: 2025-12-15
**Author**: Explainer Agent
**Status**: Draft

## Introduction/Overview

This document defines the requirements for consolidating the agent system from 3 platform variants to 2 variants. Currently, 18 agents exist across 3 platforms (Claude Code, VS Code Copilot, and GitHub Copilot CLI), resulting in 54 total files. Analysis shows that VS Code and Copilot CLI agents are 99%+ identical, differing only in YAML frontmatter. This feature consolidates VS Code and Copilot CLI into a single shared source, reducing maintenance burden by 33%.

### Problem Statement

Maintaining 54 agent files creates three problems:

1. **Duplication**: VS Code and Copilot CLI files are nearly identical, requiring redundant edits
2. **Sync Risk**: Manual synchronization across platforms risks drift and inconsistencies
3. **Maintenance Burden**: 18 additional files must be kept in sync for no functional benefit

### Solution Overview

**Phase 1**: Consolidate VS Code and Copilot CLI agents into a single source file per agent. A build script generates platform-specific outputs from the shared source.

**Phase 2**: Implement diff-linting CI to detect semantic drift between Claude and shared variants, alerting maintainers when content diverges meaningfully.

---

## Goals

1. Reduce agent file count from 54 to 36 (33% reduction)
2. Eliminate manual synchronization between VS Code and Copilot CLI variants
3. Establish CI-based drift detection between Claude and shared variants
4. Collect 90 days of drift data to inform future templating decisions
5. Maintain identical output functionality for all platforms

---

## Non-Goals (Out of Scope)

1. **Full Templating System**: Consolidating all 3 platforms into a single canonical template (deferred to v1.2+ pending drift data)
2. **Runtime Generation**: All generation happens at build time, not runtime
3. **Breaking Changes**: Output files must remain functionally identical to current files
4. **Claude Variant Changes**: Claude agents remain separate; only VS Code/Copilot are consolidated
5. **Automated Drift Fixing**: CI alerts on drift; humans decide how to resolve

---

## User Stories

### US-1: Maintainer Edits Shared Agent Source

**As a** repository maintainer
**I want to** edit a single source file for VS Code and Copilot CLI agents
**So that** both platforms receive the same update without manual duplication

**Acceptance Criteria**:

- Single source file exists at `templates/agents/[agent-name].shared.md`
- Editing the shared source updates both VS Code and Copilot CLI outputs
- Build script generates `src/vs-code-agents/[agent].agent.md` and `src/copilot-cli/[agent].agent.md`
- Generated files are byte-identical to manually-maintained files (during migration)

**INVEST Validation**:

- Independent: Does not depend on other stories
- Negotiable: Source location and naming can be discussed
- Valuable: Eliminates 18 redundant files
- Estimable: Clear scope with known file patterns
- Small: One agent can be migrated in isolation
- Testable: Compare generated output to existing files

---

### US-2: Build Script Generates Platform Outputs

**As a** developer running the build
**I want to** execute a single command to generate all platform-specific agent files
**So that** I don't need to understand the generation logic

**Acceptance Criteria**:

- Build command: `pwsh build/Generate-Agents.ps1` or `npm run generate-agents`
- Script processes all `*.shared.md` files in `templates/agents/`
- Script applies platform-specific YAML frontmatter transformations
- Script outputs to `src/vs-code-agents/` and `src/copilot-cli/`
- Script completes in under 5 seconds for all 18 agents
- Script reports success/failure for each agent processed

**INVEST Validation**:

- Independent: Build script is self-contained
- Negotiable: PowerShell vs Node.js is flexible
- Valuable: Enables the consolidation workflow
- Estimable: Similar to existing install scripts
- Small: Single script with clear inputs/outputs
- Testable: Run script, verify outputs exist and match expected content

---

### US-3: CI Validates Generated Files Match Source

**As a** CI system
**I want to** verify that generated agent files match the shared source
**So that** manual edits to generated files are detected and rejected

**Acceptance Criteria**:

- GitHub Actions workflow runs on every PR
- Workflow regenerates all agent files
- Workflow fails if regenerated files differ from committed files
- Error message identifies which files were manually modified
- PR cannot merge if generated file drift detected

**INVEST Validation**:

- Independent: CI workflow is separate from generation
- Negotiable: Specific workflow implementation is flexible
- Valuable: Prevents drift from manual edits
- Estimable: Standard CI pattern
- Small: Single workflow file
- Testable: Manually edit a generated file, verify CI fails

---

### US-4: CI Detects Semantic Drift Between Claude and Shared Variants

**As a** repository maintainer
**I want to** receive alerts when Claude and shared agent variants drift semantically
**So that** I can decide whether to synchronize them or document intentional differences

**Acceptance Criteria**:

- PowerShell script compares Claude variant to shared variant
- Script ignores expected differences (YAML frontmatter, tool syntax, handoff syntax)
- Script identifies semantic differences in content sections
- CI workflow runs weekly (not on every PR)
- Alert threshold is configurable (default: any semantic difference)
- Output includes file name, section, and diff snippet

**INVEST Validation**:

- Independent: Drift detection is separate from generation
- Negotiable: Alert threshold and frequency are adjustable
- Valuable: Enables data-driven templating decisions
- Estimable: Pattern-based comparison is straightforward
- Small: Single script + workflow
- Testable: Intentionally modify a Claude agent section, verify detection

---

### US-5: Contributor Understands the Generation Workflow

**As a** new contributor
**I want to** understand where to edit agents and how generation works
**So that** I can contribute without breaking the system

**Acceptance Criteria**:

- README or CONTRIBUTING.md documents the workflow
- Documentation explains: "Edit `templates/agents/*.shared.md`, run build, commit generated files"
- Documentation lists which files are generated (do not edit) vs source (edit here)
- Build script header includes usage instructions

**INVEST Validation**:

- Independent: Documentation is standalone
- Negotiable: Location and format flexible
- Valuable: Reduces contributor confusion
- Estimable: Known documentation scope
- Small: 1-2 documentation updates
- Testable: New contributor can follow docs to make a change

---

## Functional Requirements

### FR-1: Shared Source File Format

1. The system MUST store shared agent sources in `templates/agents/[agent-name].shared.md`
2. The shared source MUST contain all content common to VS Code and Copilot CLI variants
3. The shared source MUST use placeholder syntax for platform-specific values (e.g., `{{PLATFORM_TOOLS}}`)
4. The shared source MUST include a header comment indicating it is a source file

### FR-2: Platform Configuration

1. The system MUST maintain platform configuration in `templates/platforms/vscode.yaml` and `templates/platforms/copilot-cli.yaml`
2. Platform configuration MUST define:
   - Output directory path
   - File extension pattern
   - YAML frontmatter values (name, tools, model)
   - Handoff syntax transformation rules
3. Platform configuration MUST be editable without modifying the build script

### FR-3: Build Script Generation

1. The build script MUST read all `*.shared.md` files from `templates/agents/`
2. The build script MUST apply platform configuration to generate platform-specific outputs
3. The build script MUST transform:
   - YAML frontmatter (tools array, model field)
   - Tool invocation syntax (if any remain in body)
   - Handoff syntax (`#runSubagent` vs `/agent`)
4. The build script MUST preserve all other content exactly
5. The build script MUST create output files with correct extensions (`.agent.md`)

### FR-4: CI Generated File Validation

1. The CI workflow MUST run the build script on every PR
2. The CI workflow MUST compare generated files to committed files
3. The CI workflow MUST fail if any differences are detected
4. The CI workflow MUST output a clear error message identifying modified files

### FR-5: Drift Detection Script

1. The drift detection script MUST compare Claude variants to shared variants
2. The script MUST ignore known structural differences:
   - YAML frontmatter schema
   - `## Claude Code Tools` section (Claude-only)
   - MCP tool syntax (`mcp__` prefix vs path syntax)
   - Task handoff syntax
3. The script MUST identify differences in:
   - Core Identity
   - Core Mission
   - Responsibilities
   - Handoff Options content
   - Constraints
   - Output Location
   - Templates and examples
4. The script MUST output a machine-readable report (JSON or YAML)
5. The script MUST exit with code 0 if no semantic drift, code 1 if drift detected

### FR-6: Drift Detection CI Workflow

1. The workflow MUST run on a weekly schedule (cron)
2. The workflow MUST run the drift detection script
3. The workflow MUST create a GitHub issue if drift is detected
4. The workflow MUST include drift report in the issue body
5. The workflow MUST label the issue with `drift-detected` label

---

## Non-Functional Requirements

### NFR-1: Performance

- Build script MUST complete in under 5 seconds for all 18 agents
- Drift detection script MUST complete in under 30 seconds

### NFR-2: Maintainability

- Build script MUST be written in PowerShell (primary) or Node.js (alternative)
- All scripts MUST include inline documentation
- Configuration MUST be separate from logic

### NFR-3: Compatibility

- Generated files MUST be byte-identical to current manually-maintained files during migration
- No changes to file paths or names for downstream consumers

### NFR-4: Observability

- Build script MUST log which files it processes
- Build script MUST log transformation steps at verbose level
- Drift detection MUST produce structured output for analysis

---

## Design Considerations

### Directory Structure

```text
templates/
  agents/
    analyst.shared.md
    implementer.shared.md
    orchestrator.shared.md
    ... (18 agents)
  platforms/
    vscode.yaml
    copilot-cli.yaml
  README.md

build/
  Generate-Agents.ps1
  Detect-AgentDrift.ps1

src/
  claude/           # Unchanged (manual maintenance)
  vs-code-agents/   # Generated
  copilot-cli/      # Generated
```

### Frontmatter Transformation Example

**Shared Source** (`templates/agents/analyst.shared.md`):

```yaml
---
description: Pre-implementation research, root cause analysis, feature request review
model: {{PLATFORM_MODEL}}
tools: {{PLATFORM_TOOLS}}
---
```

**VS Code Output** (`src/vs-code-agents/analyst.agent.md`):

```yaml
---
description: Pre-implementation research, root cause analysis, feature request review
model: Claude Opus 4.5 (anthropic)
tools: ['vscode', 'read', 'write', 'glob', 'grep', 'cloudmcp-manager/memory-search_nodes']
---
```

**Copilot CLI Output** (`src/copilot-cli/analyst.agent.md`):

```yaml
---
name: analyst
description: Pre-implementation research, root cause analysis, feature request review
tools: ['shell', 'read', 'write', 'glob', 'grep', 'cloudmcp-manager/memory-search_nodes']
---
```

---

## Technical Considerations

### Build Script Technology

**Recommended**: PowerShell

Rationale:

- Existing scripts use PowerShell (`scripts/*.ps1`)
- Native YAML parsing via `ConvertFrom-Yaml` (PowerShell-Yaml module)
- Consistent with team patterns
- Cross-platform via PowerShell Core

**Alternative**: Node.js

If Node.js preferred for ecosystem consistency:

- Use `gray-matter` for frontmatter parsing
- Use `js-yaml` for YAML processing
- Add to existing `package.json` scripts

### Drift Detection Approach

The drift detection script compares sections by:

1. Extracting markdown sections using regex (`## Section Name`)
2. Normalizing whitespace and line endings
3. Comparing section content after removing platform-specific syntax
4. Reporting sections with differences above threshold

---

## Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| File count reduction | 54 to 36 files | `find src -name "*.md" | wc -l` |
| Build time | < 5 seconds | Script timing |
| CI validation | 0 manual edit escapes | CI failure rate |
| Drift alerts | Baseline established in 90 days | GitHub issue count |
| Contributor onboarding | < 30 min to first contribution | Documentation feedback |

---

## Open Questions

1. **Should generated files be committed or gitignored?**
   - Option A: Commit generated files (easier for consumers, requires CI validation)
   - Option B: Gitignore and generate at install time (cleaner repo, more complex install)
   - **Recommendation**: Option A - commit generated files with CI validation

2. **What drift threshold triggers an alert?**
   - Any semantic difference (strict)
   - >5% content change (lenient)
   - **Recommendation**: Start strict (any difference), tune based on data

3. **How should intentional differences be documented?**
   - Comments in source files
   - Separate `intentional-differences.yaml` manifest
   - **Recommendation**: Document in templates README initially

---

## Implementation Plan

### Phase 1: 2-Variant Consolidation (8-10 hours)

| Task | Effort | Deliverable |
|------|--------|-------------|
| Create templates directory structure | 1h | `templates/agents/`, `templates/platforms/` |
| Define platform configuration schema | 1h | `vscode.yaml`, `copilot-cli.yaml` |
| Migrate first 3 agents as proof of concept | 2h | `analyst`, `implementer`, `orchestrator` |
| Build `Generate-Agents.ps1` script | 2h | Working generation script |
| Validate generated output matches existing | 1h | Diff comparison passes |
| Migrate remaining 15 agents | 2h | All 18 agents consolidated |
| Add CI generated file validation | 1h | GitHub Actions workflow |

### Phase 2: Diff-Linting CI (4-6 hours)

| Task | Effort | Deliverable |
|------|--------|-------------|
| Build `Detect-AgentDrift.ps1` script | 2h | Working drift detection |
| Define section extraction patterns | 1h | Regex patterns for all sections |
| Add weekly CI workflow | 1h | Scheduled GitHub Actions |
| Create issue template for drift alerts | 0.5h | `.github/ISSUE_TEMPLATE/drift-alert.md` |
| Documentation update | 1h | README, CONTRIBUTING updates |

### Phase 3: Validation and Monitoring (Ongoing)

- Monitor drift alerts for 90 days
- Collect data on false positive rate
- Tune detection thresholds based on findings
- Decide on full templating based on drift patterns

---

## Dependencies

| Dependency | Type | Status |
|------------|------|--------|
| Existing agent files | Internal | Available |
| PowerShell Core | External | Installed |
| GitHub Actions | External | Available |
| PowerShell-Yaml module | External | May need installation |

---

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Generated files accidentally edited | Medium | Medium | CI validation blocks PRs |
| Drift detection false positives | Medium | Low | Tune threshold, add ignore patterns |
| Build script complexity grows | Low | Medium | Keep transformations simple |
| Contributors confused by workflow | Medium | Low | Clear documentation |
| Platform configuration diverges | Low | Low | Regular review of configs |

---

## References

- [Ideation Research: Agent Templating System](D:\src\GitHub\rjmurillo\ai-agents\.agents\analysis\ideation-agent-templating.md)
- [Critique: Agent Templating System](D:\src\GitHub\rjmurillo\ai-agents\.agents\critique\001-agent-templating-critique.md)
- [Product Roadmap](D:\src\GitHub\rjmurillo\ai-agents\.agents\roadmap\product-roadmap.md)
- [Agent Consolidation Process](D:\src\GitHub\rjmurillo\ai-agents\.agents\governance\agent-consolidation-process.md)

---

## Appendix A: Known Differences Between VS Code and Copilot CLI

| Element | VS Code | Copilot CLI |
|---------|---------|-------------|
| `name` field | Absent | Present |
| `model` field | `Claude Opus 4.5 (anthropic)` | Absent |
| `tools` array | VS Code extensions | Shell-based tools |
| Handoff syntax | `#runSubagent` | `/agent` |

All other content is identical.

---

## Appendix B: Known Differences Between Claude and Shared Variants

| Element | Claude | VS Code/Copilot |
|---------|--------|-----------------|
| File extension | `.md` | `.agent.md` |
| Tools section | `## Claude Code Tools` in body | YAML frontmatter only |
| Tool syntax | `mcp__cloudmcp-manager__*` | `cloudmcp-manager/*` |
| Handoff syntax | `Task(subagent_type="*")` | `#runSubagent` or `/agent` |
| Memory Protocol header | `## Memory Protocol` | `## Memory Protocol (cloudmcp-manager)` |

These structural differences are expected and excluded from drift detection. Semantic differences in core content sections trigger alerts.

---

**Handoff**: Route to **critic** for validation, then **task-generator** for atomic task breakdown.
