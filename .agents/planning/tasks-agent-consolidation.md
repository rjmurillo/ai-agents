# Task Breakdown: 2-Variant Agent Consolidation

## Source

- PRD: `.agents/planning/prd-agent-consolidation.md`
- Epic: `.agents/roadmap/epic-agent-consolidation.md`

## Summary

| Complexity | Count |
|------------|-------|
| XS | 4 |
| S | 8 |
| M | 5 |
| L | 2 |
| XL | 0 |
| **Total** | **19** |

| Phase | Estimated Effort |
|-------|-----------------|
| Phase 1: 2-Variant Consolidation | 8-10 hours |
| Phase 2: Diff-Linting CI | 4-6 hours |
| **Total** | **12-16 hours** |

---

## Phase 1: 2-Variant Consolidation

**Goal**: Consolidate VS Code and Copilot CLI agents into a single shared source per agent, reducing 36 files to 18 shared sources plus 36 generated outputs (total 54 files, but only 36 unique files to maintain).

### Milestone 1.1: Directory Structure and Configuration

---

### Task 1.1.1: Create templates directory structure

**ID**: TASK-001
**Type**: Chore
**Complexity**: XS
**Agent**: implementer
**Effort**: 30 minutes
**Dependencies**: None

**Description**
Create the `templates/` directory structure with `agents/` and `platforms/` subdirectories.

**Acceptance Criteria**

- [ ] Directory `templates/agents/` exists
- [ ] Directory `templates/platforms/` exists
- [ ] `.gitkeep` files added if needed for empty directories

**Files Affected**

- `templates/agents/.gitkeep`: Create placeholder
- `templates/platforms/.gitkeep`: Create placeholder

---

### Task 1.1.2: Define VS Code platform configuration

**ID**: TASK-002
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 45 minutes
**Dependencies**: TASK-001

**Description**
Create the platform configuration file for VS Code, defining frontmatter transformations and output settings.

**Acceptance Criteria**

- [ ] File `templates/platforms/vscode.yaml` exists
- [ ] Configuration includes: output directory (`src/vs-code-agents/`), file extension (`.agent.md`)
- [ ] Configuration includes: model value (`Claude Opus 4.5 (anthropic)`)
- [ ] Configuration includes: default tools array format
- [ ] Configuration includes: handoff syntax (`#runSubagent`)
- [ ] YAML is valid and parseable

**Files Affected**

- `templates/platforms/vscode.yaml`: Create new file

**Example Content**

```yaml
platform: vscode
outputDir: src/vs-code-agents
fileExtension: .agent.md
frontmatter:
  model: "Claude Opus 4.5 (anthropic)"
  includeNameField: false
handoffSyntax: "#runSubagent"
toolSyntax: "path"
```

---

### Task 1.1.3: Define Copilot CLI platform configuration

**ID**: TASK-003
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 45 minutes
**Dependencies**: TASK-001

**Description**
Create the platform configuration file for Copilot CLI, defining frontmatter transformations and output settings.

**Acceptance Criteria**

- [ ] File `templates/platforms/copilot-cli.yaml` exists
- [ ] Configuration includes: output directory (`src/copilot-cli/`), file extension (`.agent.md`)
- [ ] Configuration includes: name field requirement (present)
- [ ] Configuration includes: default tools array format (shell-based)
- [ ] Configuration includes: handoff syntax (`/agent`)
- [ ] YAML is valid and parseable

**Files Affected**

- `templates/platforms/copilot-cli.yaml`: Create new file

---

### Task 1.1.4: Create templates README documentation

**ID**: TASK-004
**Type**: Chore
**Complexity**: S
**Agent**: explainer
**Effort**: 45 minutes
**Dependencies**: TASK-002, TASK-003

**Description**
Document the templates directory structure, explaining the shared source format and platform configuration schema.

**Acceptance Criteria**

- [ ] File `templates/README.md` exists
- [ ] Documentation explains shared source file format
- [ ] Documentation explains placeholder syntax (`{{PLATFORM_*}}`)
- [ ] Documentation explains platform configuration schema
- [ ] Documentation includes example workflow for editing agents

**Files Affected**

- `templates/README.md`: Create new file

---

### Milestone 1.2: Build Script Development

---

### Task 1.2.1: Create Generate-Agents.ps1 script skeleton

**ID**: TASK-005
**Type**: Feature
**Complexity**: M
**Agent**: implementer
**Effort**: 1.5 hours
**Dependencies**: TASK-002, TASK-003

**Description**
Create the PowerShell script that reads shared sources and generates platform-specific outputs. This task covers the script structure, parameter handling, and main loop.

**Acceptance Criteria**

- [ ] File `build/Generate-Agents.ps1` exists
- [ ] Script has `-Verbose` parameter for detailed logging
- [ ] Script has `-WhatIf` parameter for dry-run mode
- [ ] Script discovers all `*.shared.md` files in `templates/agents/`
- [ ] Script loads platform configurations from `templates/platforms/`
- [ ] Script has clear error handling for missing files
- [ ] Script includes usage instructions in header comment

**Files Affected**

- `build/Generate-Agents.ps1`: Create new file

---

### Task 1.2.2: Implement frontmatter transformation logic

**ID**: TASK-006
**Type**: Feature
**Complexity**: M
**Agent**: implementer
**Effort**: 1.5 hours
**Dependencies**: TASK-005

**Description**
Implement the core transformation logic that reads shared source frontmatter and applies platform-specific values.

**Acceptance Criteria**

- [ ] Function parses YAML frontmatter from shared source
- [ ] Function replaces `{{PLATFORM_MODEL}}` placeholder
- [ ] Function replaces `{{PLATFORM_TOOLS}}` placeholder
- [ ] Function adds/removes `name` field based on platform config
- [ ] Function preserves all other frontmatter fields unchanged
- [ ] Unit tests cover transformation edge cases

**Files Affected**

- `build/Generate-Agents.ps1`: Add transformation functions
- `build/tests/Generate-Agents.Tests.ps1`: Create test file

---

### Task 1.2.3: Implement handoff syntax transformation

**ID**: TASK-007
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 45 minutes
**Dependencies**: TASK-005

**Description**
Implement body content transformation that converts handoff syntax between platforms.

**Acceptance Criteria**

- [ ] Function transforms handoff syntax in markdown body
- [ ] VS Code output uses `#runSubagent` syntax
- [ ] Copilot CLI output uses `/agent` syntax
- [ ] Function handles multiple handoff occurrences in single file
- [ ] Transformation preserves surrounding content exactly

**Files Affected**

- `build/Generate-Agents.ps1`: Add body transformation functions

---

### Task 1.2.4: Implement file output and validation

**ID**: TASK-008
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 45 minutes
**Dependencies**: TASK-006, TASK-007

**Description**
Implement file writing with validation, ensuring generated files have correct paths and extensions.

**Acceptance Criteria**

- [ ] Script writes output to correct platform directory
- [ ] Output files have correct extension (`.agent.md`)
- [ ] Script creates output directories if missing
- [ ] Script reports success/failure per file processed
- [ ] Script completes in under 5 seconds for all 18 agents
- [ ] Script exits with code 0 on success, code 1 on failure

**Files Affected**

- `build/Generate-Agents.ps1`: Add file output functions

---

### Milestone 1.3: Agent Migration (Proof of Concept)

---

### Task 1.3.1: Migrate analyst agent to shared source

**ID**: TASK-009
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 30 minutes
**Dependencies**: TASK-008

**Description**
Create the first shared source file by consolidating VS Code and Copilot CLI analyst agents.

**Acceptance Criteria**

- [ ] File `templates/agents/analyst.shared.md` exists
- [ ] Shared source includes header comment indicating it is a source file
- [ ] Shared source uses placeholder syntax for platform-specific values
- [ ] Running build script generates output matching existing `src/vs-code-agents/analyst.agent.md`
- [ ] Running build script generates output matching existing `src/copilot-cli/analyst.agent.md`
- [ ] Diff comparison shows zero differences (byte-identical)

**Files Affected**

- `templates/agents/analyst.shared.md`: Create new file

---

### Task 1.3.2: Migrate implementer agent to shared source

**ID**: TASK-010
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 30 minutes
**Dependencies**: TASK-009

**Description**
Create shared source for implementer agent, validating the migration pattern works for a second agent.

**Acceptance Criteria**

- [ ] File `templates/agents/implementer.shared.md` exists
- [ ] Generated outputs match existing files exactly
- [ ] No manual adjustments needed to build script

**Files Affected**

- `templates/agents/implementer.shared.md`: Create new file

---

### Task 1.3.3: Migrate orchestrator agent to shared source

**ID**: TASK-011
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 30 minutes
**Dependencies**: TASK-010

**Description**
Create shared source for orchestrator agent, completing the proof of concept with 3 agents.

**Acceptance Criteria**

- [ ] File `templates/agents/orchestrator.shared.md` exists
- [ ] Generated outputs match existing files exactly
- [ ] Build script handles all 3 agents without modification

**Files Affected**

- `templates/agents/orchestrator.shared.md`: Create new file

---

### Task 1.3.4: Validate proof of concept outputs

**ID**: TASK-012
**Type**: Chore
**Complexity**: XS
**Agent**: qa
**Effort**: 30 minutes
**Dependencies**: TASK-011

**Description**
Validate that all 3 proof of concept agents generate byte-identical outputs compared to existing files.

**Acceptance Criteria**

- [ ] Diff comparison for all 3 VS Code outputs shows no differences
- [ ] Diff comparison for all 3 Copilot CLI outputs shows no differences
- [ ] Build script runs without errors
- [ ] Build script completes in under 2 seconds for 3 agents

**Files Affected**

- None (validation only)

---

### Milestone 1.4: Full Agent Migration

---

### Task 1.4.1: Migrate remaining 15 agents to shared sources

**ID**: TASK-013
**Type**: Feature
**Complexity**: L
**Agent**: implementer
**Effort**: 2 hours
**Dependencies**: TASK-012

**Description**
Apply the validated migration pattern to the remaining 15 agents: architect, critic, devops, explainer, high-level-advisor, independent-thinker, memory, planner, pr-comment-responder, qa, retrospective, roadmap, security, skillbook, task-generator.

**Acceptance Criteria**

- [ ] All 18 shared source files exist in `templates/agents/`
- [ ] Build script generates all 36 output files (18 VS Code + 18 Copilot CLI)
- [ ] All generated outputs match existing files exactly
- [ ] Build completes in under 5 seconds

**Files Affected**

- `templates/agents/*.shared.md`: Create 15 new files

**Agent List**

1. architect
2. critic
3. devops
4. explainer
5. high-level-advisor
6. independent-thinker
7. memory
8. planner
9. pr-comment-responder
10. qa
11. retrospective
12. roadmap
13. security
14. skillbook
15. task-generator

---

### Milestone 1.5: CI Integration

---

### Task 1.5.1: Create CI workflow for generated file validation

**ID**: TASK-014
**Type**: Feature
**Complexity**: M
**Agent**: devops
**Effort**: 1 hour
**Dependencies**: TASK-013

**Description**
Create a GitHub Actions workflow that regenerates agent files and fails if they differ from committed files.

**Acceptance Criteria**

- [ ] File `.github/workflows/validate-generated-agents.yml` exists
- [ ] Workflow triggers on PR and push to main
- [ ] Workflow only runs when agent-related files change
- [ ] Workflow regenerates all agent files
- [ ] Workflow compares regenerated to committed files
- [ ] Workflow fails with clear error message if differences detected
- [ ] Error message identifies which files were manually modified

**Files Affected**

- `.github/workflows/validate-generated-agents.yml`: Create new file

**Trigger Paths**

```yaml
paths:
  - 'templates/**'
  - 'src/vs-code-agents/**'
  - 'src/copilot-cli/**'
  - 'build/Generate-Agents.ps1'
```

---

### Task 1.5.2: Update CONTRIBUTING.md with generation workflow

**ID**: TASK-015
**Type**: Chore
**Complexity**: XS
**Agent**: explainer
**Effort**: 30 minutes
**Dependencies**: TASK-014

**Description**
Update contributor documentation to explain the shared source workflow: edit templates, run build, commit generated files.

**Acceptance Criteria**

- [ ] CONTRIBUTING.md or relevant doc updated
- [ ] Documentation explains which files are sources vs generated
- [ ] Documentation includes command to regenerate: `pwsh build/Generate-Agents.ps1`
- [ ] Documentation warns against editing generated files directly

**Files Affected**

- `CONTRIBUTING.md`: Update with generation workflow (or create if missing)

---

## Phase 2: Diff-Linting CI

**Goal**: Implement semantic drift detection between Claude agents and shared (VS Code/Copilot) variants, enabling data-driven decisions about future consolidation.

### Milestone 2.1: Drift Detection Script

---

### Task 2.1.1: Create Detect-AgentDrift.ps1 script skeleton

**ID**: TASK-016
**Type**: Feature
**Complexity**: M
**Agent**: implementer
**Effort**: 1 hour
**Dependencies**: TASK-013

**Description**
Create the PowerShell script that compares Claude agent variants to shared variants, identifying semantic differences.

**Acceptance Criteria**

- [ ] File `build/Detect-AgentDrift.ps1` exists
- [ ] Script accepts agent name parameter (or processes all)
- [ ] Script has `-OutputFormat` parameter (JSON, YAML, Text)
- [ ] Script outputs structured report of differences
- [ ] Script exits with code 0 if no drift, code 1 if drift detected
- [ ] Script includes usage instructions in header comment

**Files Affected**

- `build/Detect-AgentDrift.ps1`: Create new file

---

### Task 2.1.2: Implement section extraction logic

**ID**: TASK-017
**Type**: Feature
**Complexity**: S
**Agent**: implementer
**Effort**: 1 hour
**Dependencies**: TASK-016

**Description**
Implement markdown section extraction using regex to compare specific content sections between variants.

**Acceptance Criteria**

- [ ] Function extracts sections by `## Section Name` headers
- [ ] Function handles nested sections (`### Subsection`)
- [ ] Function normalizes whitespace and line endings
- [ ] Sections extracted: Core Identity, Core Mission, Key Responsibilities, Constraints, Output Location
- [ ] Function returns structured section map for comparison

**Files Affected**

- `build/Detect-AgentDrift.ps1`: Add section extraction functions

---

### Task 2.1.3: Implement drift comparison logic

**ID**: TASK-018
**Type**: Feature
**Complexity**: M
**Agent**: implementer
**Effort**: 1 hour
**Dependencies**: TASK-017

**Description**
Implement comparison logic that ignores known structural differences while detecting semantic drift.

**Acceptance Criteria**

- [ ] Comparison ignores YAML frontmatter differences
- [ ] Comparison ignores `## Claude Code Tools` section (Claude-only)
- [ ] Comparison ignores tool syntax differences (`mcp__` vs path syntax)
- [ ] Comparison ignores handoff syntax differences
- [ ] Comparison detects differences in core content sections
- [ ] Output includes: file name, section name, diff snippet, severity

**Files Affected**

- `build/Detect-AgentDrift.ps1`: Add comparison functions

**Known Exclusions**

| Pattern | Reason |
|---------|--------|
| YAML frontmatter | Schema differs by design |
| `## Claude Code Tools` | Claude-only section |
| `mcp__*` tool syntax | Platform-specific |
| `Task(subagent_type=` | Claude handoff syntax |
| `#runSubagent` / `/agent` | Shared handoff syntax |

---

### Milestone 2.2: CI Workflow Integration

---

### Task 2.2.1: Create weekly drift detection workflow

**ID**: TASK-019
**Type**: Feature
**Complexity**: S
**Agent**: devops
**Effort**: 1 hour
**Dependencies**: TASK-018

**Description**
Create a GitHub Actions workflow that runs drift detection on a weekly schedule and creates issues for detected drift.

**Acceptance Criteria**

- [ ] File `.github/workflows/drift-detection.yml` exists
- [ ] Workflow runs on weekly schedule (cron)
- [ ] Workflow also runs on manual dispatch
- [ ] Workflow runs drift detection script
- [ ] Workflow creates GitHub issue if drift detected
- [ ] Issue includes drift report in body
- [ ] Issue labeled with `drift-detected`
- [ ] Workflow does not fail the run (alerting only)

**Files Affected**

- `.github/workflows/drift-detection.yml`: Create new file

**Cron Schedule**

```yaml
schedule:
  - cron: '0 9 * * 1'  # Monday at 9 AM UTC
```

---

### Task 2.2.2: Create drift alert issue template

**ID**: TASK-020
**Type**: Chore
**Complexity**: XS
**Agent**: devops
**Effort**: 30 minutes
**Dependencies**: TASK-019

**Description**
Create an issue template for drift alerts, ensuring consistent formatting and actionable information.

**Acceptance Criteria**

- [ ] File `.github/ISSUE_TEMPLATE/drift-alert.md` exists
- [ ] Template includes: agent name, section, diff summary
- [ ] Template includes checklist: review, intentional?, sync/document
- [ ] Template assigns default label `drift-detected`

**Files Affected**

- `.github/ISSUE_TEMPLATE/drift-alert.md`: Create new file

---

### Task 2.2.3: Document intentional differences tracking

**ID**: TASK-021
**Type**: Chore
**Complexity**: XS
**Agent**: explainer
**Effort**: 30 minutes
**Dependencies**: TASK-018

**Description**
Create documentation for tracking intentional differences between Claude and shared variants, providing a place to document deliberate divergence.

**Acceptance Criteria**

- [ ] Section in `templates/README.md` documents intentional differences
- [ ] Documentation explains when Claude differs intentionally
- [ ] Documentation lists current known intentional differences
- [ ] Clear guidance on when to sync vs document

**Files Affected**

- `templates/README.md`: Update with intentional differences section

---

## Dependency Graph

```text
Phase 1: 2-Variant Consolidation
================================

TASK-001 (directories)
    |
    +---> TASK-002 (vscode config)
    |         |
    +---> TASK-003 (copilot config)
              |
              v
         TASK-004 (templates README)
              |
              v
         TASK-005 (build script skeleton)
              |
              +---> TASK-006 (frontmatter transform)
              |         |
              +---> TASK-007 (handoff transform)
                          |
                          v
                     TASK-008 (file output)
                          |
                          v
                     TASK-009 (migrate analyst)
                          |
                          v
                     TASK-010 (migrate implementer)
                          |
                          v
                     TASK-011 (migrate orchestrator)
                          |
                          v
                     TASK-012 (validate PoC) [QA checkpoint]
                          |
                          v
                     TASK-013 (migrate remaining 15)
                          |
                          +---> TASK-014 (CI validation workflow)
                          |         |
                          |         v
                          |    TASK-015 (update CONTRIBUTING)
                          |
                          v
Phase 2: Diff-Linting CI
========================
                          |
                     TASK-016 (drift script skeleton)
                          |
                          v
                     TASK-017 (section extraction)
                          |
                          v
                     TASK-018 (drift comparison)
                          |
                          +---> TASK-019 (weekly workflow)
                          |         |
                          |         v
                          |    TASK-020 (issue template)
                          |
                          v
                     TASK-021 (document intentional diffs)
```

---

## Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Generated files accidentally edited | CI blocks PR | Medium | TASK-014 validates on every PR |
| VS Code/Copilot differences missed | Incorrect output | Low | TASK-012 validates proof of concept |
| Drift detection false positives | Alert fatigue | Medium | Start strict, tune threshold with data |
| PowerShell-Yaml module unavailable | Build fails | Low | Document prerequisite, fallback to regex parsing |
| Complex agents require special handling | Migration delays | Low | Validate with 3 agents first (TASK-009-012) |

---

## Quality Gates

| Gate | Checkpoint | Criteria |
|------|------------|----------|
| PoC Validation | After TASK-012 | 3 agents generate byte-identical outputs |
| Full Migration | After TASK-013 | All 18 agents generate byte-identical outputs |
| CI Integration | After TASK-014 | PR with manual edit to generated file fails |
| Drift Detection | After TASK-018 | Intentional Claude difference detected |

---

## Agent Assignments Summary

| Agent | Tasks | Estimated Effort |
|-------|-------|-----------------|
| **implementer** | TASK-001, 002, 003, 005, 006, 007, 008, 009, 010, 011, 013, 016, 017, 018 | 10-12 hours |
| **devops** | TASK-014, 019, 020 | 2-2.5 hours |
| **explainer** | TASK-004, 015, 021 | 1.5-2 hours |
| **qa** | TASK-012 | 0.5 hours |

---

## Next Steps

1. **Handoff to critic**: Validate this task breakdown before implementation
2. **After critic approval**: Begin with Milestone 1.1 (directory structure)
3. **Quality gate at TASK-012**: Validate PoC before full migration
4. **Phase 2 can begin in parallel**: TASK-016 can start once TASK-013 is in progress

---

**Handoff**: Route to **critic** for task breakdown validation.
