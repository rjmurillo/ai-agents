# Skill Standards: Authoritative Reconciliation

**Date**: 2026-01-09
**Status**: CANONICAL REFERENCE
**Supersedes**: Fragmented documentation across memories, ADRs, and analysis documents

---

## Executive Summary

This document reconciles all skill knowledge from official standards (agentskills.io, claude.com), project ADRs, memory systems (Serena and Forgetful), and actual implementations. It resolves conflicts, documents authoritative schema, and provides clear guidance for skill authors.

**Key Finding**: The ai-agents project is 90% aligned with the official agentskills.io standard but has project-specific extensions that must be clearly distinguished from the base specification.

---

## 1. Authoritative Schema

### 1.1 Official Standard (agentskills.io + claude.com)

**Required Fields** (only 2):

| Field | Constraints | Purpose |
|-------|-------------|---------|
| `name` | Max 64 chars, lowercase letters/numbers/hyphens, no start/end hyphen, no consecutive hyphens, matches directory name | Unique identifier, discovery |
| `description` | Max 1024 chars, non-empty, no XML tags | Primary trigger mechanism for skill activation |

**Optional Fields**:

| Field | Constraints | Purpose | Source |
|-------|-------------|---------|--------|
| `license` | SPDX identifier or reference | Legal compliance | agentskills.io |
| `compatibility` | Max 500 chars | Environment requirements (product, system packages, network) | agentskills.io |
| `metadata` | Arbitrary key-value mapping | Extensibility for domain-specific fields | agentskills.io |
| `allowed-tools` | Space-delimited list | Tool permissions (experimental, Claude Code only) | agentskills.io, claude.com |
| `disable-model-invocation` | Boolean | Prevents auto-invocation via Skill tool | claude.com |
| `mode` | String | Categorizes as "mode command" that modifies behavior | claude.com |

**Formatting Requirements**:

- Frontmatter MUST start with `---` on line 1 (no blank lines before)
- Frontmatter MUST end with `---` before Markdown content
- Use spaces for indentation (tabs not allowed)
- YAML must be valid (parseable)

**Name Validation Regex**: `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$` with max 64 chars

### 1.2 ai-agents Project Extensions

**Additional Top-Level Fields** (project-specific):

| Field | Constraints | Purpose | Rationale |
|-------|-------------|---------|-----------|
| `version` | Semantic versioning (X.Y.Z) | Track skill evolution | SkillForge validator requirement |
| `model` | Claude model alias or dated ID | Specify execution model | Claude Code optimization, ADR-040 |

**Extended Metadata Fields** (in `metadata` object):

| Field | Type | Purpose |
|-------|------|---------|
| `subagent_model` | String | Model for delegated subagents (orchestrators) |
| `domains` | Array | Domain classification (architecture, security, etc.) |
| `type` | String | Skill type (orchestrator, initialization, analysis, etc.) |
| `inputs` | Array | Expected input types |
| `outputs` | Array | Produced output types |
| `file_triggers.patterns` | Array | File patterns that trigger skill |
| `file_triggers.events` | Array | File events (create, update, delete) |
| `file_triggers.auto_invoke` | Boolean | Auto-invoke on file trigger |
| `complexity` | String | Complexity level (simple, standard, advanced) |

**Additional Directories**:

- `modules/`: PowerShell .psm1 modules for shared code
- `templates/`: Renamed from standard `assets/` for semantic clarity
- `tests/`: Pester test files (.Tests.ps1)

---

## 2. Conflict Resolution

### Conflict 1: version Field Placement

**Sources**:

- **agentskills.io**: Specifies `metadata.version` (inside metadata object)
- **ADR-040**: Specifies top-level `version` field (SkillForge validator requirement)
- **Actual skills**: Mix of both approaches

**Resolution**: **TOP-LEVEL for ai-agents project**

**Rationale**:

- SkillForge validator (official ai-agents validation tool) requires top-level
- Semantic versioning is fundamental metadata, not domain-specific
- Top-level placement makes version immediately visible
- Does not conflict with agentskills.io (which allows arbitrary top-level fields)

**Migration**: Projects using `metadata.version` should move to top-level.

### Conflict 2: model Field Existence

**Sources**:

- **agentskills.io**: No mention of `model` field
- **claude.com**: No mention of `model` field
- **ai-agents (ADR-040)**: Required top-level field with specific model aliases

**Resolution**: **PROJECT-SPECIFIC EXTENSION**

**Rationale**:

- The `model` field is a Claude Code-specific feature for optimizing skill execution
- Official standard is platform-agnostic (supports multiple AI platforms)
- ai-agents project exclusively uses Claude Code, so extension is justified
- Field does not conflict with standard (arbitrary top-level fields allowed)

**Guidance**:

- **ai-agents skills**: REQUIRED top-level field
- **Portable skills**: OMIT this field (use platform defaults)
- **Value format**: Use aliases (`claude-opus-4-5`) for auto-updates, dated IDs (`claude-opus-4-5-20251101`) for deterministic behavior

### Conflict 3: Required Fields Count

**Sources**:

- **Official spec (agentskills.io + claude.com)**: Only 2 required (name, description)
- **ADR-040 (ai-agents)**: 5 required (name, version, description, license, model)
- **Forgetful Memory 99**: Confirms 5 required for ai-agents

**Resolution**: **TWO-TIER REQUIREMENT SYSTEM**

| Tier | Required Fields | Scope |
|------|----------------|-------|
| **Official Standard** | `name`, `description` | Portable skills, cross-platform |
| **ai-agents Project** | `name`, `version`, `description`, `license`, `model` | Project-internal skills |

**Rationale**:

- Official standard intentionally minimal for interoperability
- ai-agents project has higher quality bar (versioning, licensing, model selection)
- Two-tier system allows both portable skills and project-optimized skills

**Validation**:

- External skills: Validate against 2-field minimum (portable)
- ai-agents skills: Validate against 5-field standard (project quality bar)

### Conflict 4: allowed-tools Format

**Sources**:

- **agentskills.io**: Space-delimited list (`allowed-tools: Read Write Bash`)
- **claude.com**: Space-delimited list (matches agentskills.io)
- **ADR-040 example**: Comma-separated list (`allowed-tools: Read, Write, Bash`)

**Resolution**: **SPACE-DELIMITED (official standard)**

**Rationale**:

- ADR-040 comma format was an error in example code
- Official specification from both agentskills.io and claude.com is authoritative
- YAML list syntax would be `[Read, Write, Bash]` if comma-separated was intended
- Space-delimited aligns with YAML string list convention

**Correction Required**:

- ADR-040 Section 6 example must be updated:

```yaml
# WRONG (ADR-040 example)
allowed-tools: Read, Grep, Glob

# CORRECT (official standard)
allowed-tools: Read Grep Glob
```

### Conflict 5: metadata.subagent_model vs Top-Level model

**Sources**:

- **adr-review skill**: Uses `metadata.subagent_model` for delegated agent model
- **skillforge, session-init**: Use top-level `model` for skill execution model
- **ADR-040**: Specifies top-level `model` per SkillForge validator

**Resolution**: **BOTH, DIFFERENT PURPOSES**

| Field | Location | Purpose | When to Use |
|-------|----------|---------|-------------|
| `model` | Top-level | Model that executes THIS skill | Always (ai-agents requirement) |
| `metadata.subagent_model` | In metadata | Model for agents THIS skill delegates to | Orchestrator skills only |

**Rationale**:

- These fields serve different purposes and are not in conflict
- Orchestrator skills may use a different model than the agents they invoke
- Example: adr-review uses Opus for orchestration, but may delegate to Sonnet agents

**Example (orchestrator)**:

```yaml
---
name: adr-review
model: claude-opus-4-5           # Orchestrator runs on Opus
metadata:
  subagent_model: claude-opus-4-5  # Delegates to Opus agents
```

**Example (non-orchestrator)**:

```yaml
---
name: session-init
model: claude-sonnet-4-5         # Skill runs on Sonnet
metadata:
  domains: [session-protocol]    # No subagent_model (not an orchestrator)
```

---

## 3. Authoritative Field Reference

### 3.1 Complete Schema

```yaml
---
# REQUIRED (Official Standard)
name: skill-identifier               # Max 64 chars, lowercase+hyphens
description: What and when to use    # Max 1024 chars, trigger keywords

# REQUIRED (ai-agents Project)
version: 1.0.0                       # Semantic versioning
license: MIT                         # SPDX identifier
model: claude-sonnet-4-5             # Model alias or dated ID

# OPTIONAL (Official Standard)
compatibility: Requires network      # Max 500 chars, env requirements
allowed-tools: Read Grep Glob        # Space-delimited tool list

# OPTIONAL (Claude Code)
disable-model-invocation: false      # Prevent auto-invoke
mode: context                        # Mode command category

# OPTIONAL (ai-agents Extensions)
metadata:
  # Orchestrator-specific
  subagent_model: claude-opus-4-5    # Model for delegated agents

  # Classification
  domains: [architecture, planning]  # Domain categories
  type: orchestrator                 # Skill type
  complexity: advanced               # Complexity level

  # I/O Specification
  inputs: [adr-file-path]            # Expected inputs
  outputs: [debate-log, updated-adr] # Produced outputs

  # File Triggers
  file_triggers:
    patterns:
      - ".agents/architecture/ADR-*.md"
    events: [create, update, delete]
    auto_invoke: true
---
```

### 3.2 Field Definitions

#### name (REQUIRED)

- **Type**: String
- **Constraints**:
  - Max 64 characters
  - Lowercase letters, numbers, hyphens only
  - No start/end with hyphen
  - No consecutive hyphens
  - Must match parent directory name
- **Regex**: `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$`
- **Example**: `session-init`, `adr-review`, `fix-markdown-fences`

#### description (REQUIRED)

- **Type**: String
- **Constraints**:
  - Max 1024 characters
  - Non-empty
  - No XML tags
- **Purpose**: Primary skill triggering mechanism
- **Best Practice**: Include WHAT (capability) + WHEN (triggers) + KEYWORDS (natural language)
- **Good Example**: `Execute Pester tests with coverage analysis. Use when asked to "run tests", "check coverage", or "verify test suite".`
- **Bad Example**: `Helps with testing` (too generic)

#### version (REQUIRED for ai-agents)

- **Type**: String
- **Format**: Semantic versioning (X.Y.Z)
- **Example**: `1.0.0`, `2.3.1`
- **Location**: Top-level (not in metadata)

#### license (REQUIRED for ai-agents)

- **Type**: String
- **Format**: SPDX identifier or reference
- **Example**: `MIT`, `Apache-2.0`, `GPL-3.0-only`
- **Purpose**: Legal compliance

#### model (REQUIRED for ai-agents)

- **Type**: String
- **Format**: Model alias or dated snapshot ID
- **Aliases** (recommended):
  - `claude-opus-4-5` - Maximum reasoning, orchestration ($5/$25 per MTok)
  - `claude-sonnet-4-5` - Standard workflows ($3/$15 per MTok)
  - `claude-haiku-4-5` - Speed, lightweight ($1/$5 per MTok)
- **Dated IDs** (deterministic behavior):
  - `claude-opus-4-5-20251101`
  - `claude-sonnet-4-5-20250929`
  - `claude-haiku-4-5-20251015`
- **Selection Criteria**:

| Characteristic | Haiku | Sonnet | Opus |
|----------------|-------|--------|------|
| Reasoning Depth | Simple rules | Standard logic | Complex multi-step |
| Orchestration | None | Single agent | Multi-agent |
| Latency | <1s critical | <5s acceptable | <30s acceptable |
| Cost | Minimal | Standard | Premium justified |

#### compatibility (OPTIONAL)

- **Type**: String
- **Constraints**: Max 500 characters
- **Purpose**: Environment requirements (product, system packages, network access)
- **Example**: `Requires PowerShell 7.4+, network access to GitHub API`
- **Source**: agentskills.io specification

#### allowed-tools (OPTIONAL, EXPERIMENTAL)

- **Type**: String (space-delimited list)
- **Format**: `Read Grep Glob` (space-separated, NOT comma-separated)
- **Purpose**: Tool permission restrictions (least privilege)
- **Supported**: Claude Code only (experimental feature)
- **Example**:

```yaml
# Read-only analysis
allowed-tools: Read Grep Glob

# GitHub operations
allowed-tools: Bash(gh:*) Bash(pwsh:*) Read Write

# Unrestricted (document justification)
# Omit allowed-tools field entirely
```

#### disable-model-invocation (OPTIONAL)

- **Type**: Boolean
- **Purpose**: Prevents Claude from auto-invoking skill via Skill tool
- **Default**: false
- **Use Case**: Mode commands, context modifiers
- **Source**: claude.com specification

#### mode (OPTIONAL)

- **Type**: String
- **Purpose**: Categorizes skill as "mode command" that modifies behavior/context
- **Example**: `context`, `behavior`, `workflow`
- **Source**: claude.com specification

#### metadata (OPTIONAL)

- **Type**: Object (key-value mapping)
- **Purpose**: Arbitrary domain-specific fields
- **ai-agents Common Fields**:
  - `subagent_model`: Model for delegated agents (orchestrators)
  - `domains`: Array of domain categories
  - `type`: Skill type (orchestrator, initialization, analysis, etc.)
  - `complexity`: simple | standard | advanced
  - `inputs`: Array of expected input types
  - `outputs`: Array of produced output types
  - `file_triggers`: Object with patterns, events, auto_invoke

---

## 4. Directory Structure

### 4.1 Official Standard (agentskills.io)

```text
skill-name/
├── SKILL.md          # Required: frontmatter + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: detailed documentation
└── assets/           # Optional: templates, resources
```

### 4.2 ai-agents Extensions

```text
skill-name/
├── SKILL.md          # Required: frontmatter + instructions
├── modules/          # Optional: PowerShell .psm1 modules
├── scripts/          # Optional: PowerShell .ps1 scripts
├── templates/        # Optional: templates (renamed from assets)
├── references/       # Optional: detailed documentation
└── tests/            # Optional: Pester .Tests.ps1 files
```

**Differences Explained**:

- `modules/`: PowerShell module support (project-specific, for shared code)
- `templates/`: Semantic rename of `assets/` (clearer purpose)
- `tests/`: Pester test coverage (quality requirement for ai-agents)

---

## 5. Progressive Disclosure Model

Skills should follow token-efficient loading:

| Tier | Content | Token Budget | When Loaded |
|------|---------|--------------|-------------|
| **Metadata** | name + description | ~100 tokens | Startup (all skills) |
| **Instructions** | SKILL.md body | <5000 tokens | Skill activation |
| **Resources** | references/, scripts/, templates/ | As needed | On-demand reference |

**Best Practices**:

- Keep SKILL.md under 500 lines
- Move detailed content to `references/` directory
- Use clear, descriptive reference file names
- Link from SKILL.md rather than embedding large content
- Add table of contents for files >100 lines

---

## 6. Validation Rules

### 6.1 Frontmatter Validation

Checklist for all skills:

- [ ] Frontmatter starts with `---` on line 1 (no blank lines before)
- [ ] Frontmatter ends with `---` before Markdown content
- [ ] Uses spaces for indentation (no tabs)
- [ ] YAML is valid (parseable)
- [ ] `name`: matches regex `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$`, max 64 chars
- [ ] `name`: matches parent directory name exactly
- [ ] `description`: non-empty, max 1024 chars, includes trigger keywords
- [ ] `model` (ai-agents): valid alias or dated ID matching `^claude-(opus|sonnet|haiku)-4-5(-\d{8})?$`
- [ ] `version` (ai-agents): semantic versioning format `^\d+\.\d+\.\d+$`
- [ ] `license` (ai-agents): valid SPDX identifier
- [ ] `allowed-tools` (if present): space-delimited (not comma-separated)

### 6.2 Validation Tools

#### Official Validation (agentskills.io)

```bash
# Install skills-ref library
npm install -g @agentskills/skills-ref

# Validate against official standard
skills-ref validate ./my-skill

# Generate prompt XML for discovery
skills-ref to-prompt ./skills/*
```

**Source**: https://github.com/agentskills/agentskills/tree/main/skills-ref

#### ai-agents Validation (project-specific)

```bash
# Validate against ai-agents standard (SkillForge validator)
python3 .claude/skills/SkillForge/scripts/validate-skill.py ./my-skill

# Quick validation
python3 .claude/skills/SkillForge/scripts/quick_validate.py ./my-skill
```

**Additional Validation**: Session protocol validation runs `npx markdownlint-cli2` on all Markdown files, including SKILL.md.

---

## 7. Migration Guidance

### 7.1 From Metadata to Top-Level (version field)

**Before** (agentskills.io pattern):

```yaml
---
name: my-skill
description: Does something useful
metadata:
  version: 1.0.0
---
```

**After** (ai-agents standard):

```yaml
---
name: my-skill
version: 1.0.0  # Moved to top-level
description: Does something useful
license: MIT
model: claude-sonnet-4-5
metadata:
  domains: [analysis]  # Domain-specific fields remain
---
```

### 7.2 From Dated IDs to Aliases

**Before** (dated snapshot):

```yaml
---
model: claude-opus-4-5-20251101
---
```

**After** (alias for auto-updates):

```yaml
---
model: claude-opus-4-5  # Auto-updates within ~1 week of release
---
```

**When to Keep Dated IDs**:

- Security-critical skills requiring deterministic behavior
- Skills where behavioral change could cause incidents
- Compliance requirements for reproducible behavior

**Examples**: `security-detection`, `session-log-fixer` (per ADR-040)

### 7.3 Comma-Separated to Space-Delimited (allowed-tools)

**Before** (incorrect):

```yaml
---
allowed-tools: Read, Grep, Glob
---
```

**After** (correct):

```yaml
---
allowed-tools: Read Grep Glob
---
```

---

## 8. Platform Compatibility

### 8.1 Official Standard Compliance

**Portable Skills** (work across all platforms):

- Use ONLY official required fields: `name`, `description`
- Use ONLY official optional fields: `license`, `compatibility`, `metadata`, `allowed-tools`
- Omit ai-agents extensions: `version`, `model`
- Store platform-specific logic in `metadata` object

**Supported Platforms**:

- Claude Code (Anthropic)
- Claude AI (Anthropic)
- Gemini CLI (Google)
- GitHub Copilot (Microsoft)
- VS Code (Microsoft)
- Cursor
- OpenCode
- Amp
- Letta
- Goose
- Factory
- OpenAI Codex

### 8.2 ai-agents Project Extensions

**Project-Optimized Skills** (ai-agents only):

- Include all 5 required fields: `name`, `version`, `description`, `license`, `model`
- Use ai-agents metadata fields: `domains`, `type`, `subagent_model`, etc.
- Leverage PowerShell in `modules/` and `scripts/`
- Add Pester tests in `tests/`

**Trade-off**: Higher quality bar but reduced portability.

---

## 9. Official Sources and References

### 9.1 Official Standards

- [Agent Skills Specification](https://agentskills.io/specification) - Primary standard
- [Agent Skills - Claude Code Docs](https://code.claude.com/docs/en/skills) - Claude implementation
- [Agent Skills - Claude Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) - Overview
- [Skill Authoring Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) - Official guidance
- [agentskills GitHub Repo](https://github.com/agentskills/agentskills) - Specification source
- [anthropics/skills GitHub Repo](https://github.com/anthropics/skills) - Example skills

### 9.2 Validation Tools

- [skills-ref Library](https://github.com/agentskills/agentskills/tree/main/skills-ref) - Official validation

### 9.3 ai-agents Project Documentation

- **ADR-040**: Skill Frontmatter Standardization (`.agents/architecture/ADR-040-skill-frontmatter-standardization.md`)
- **Analysis**: Claude Code Skill Frontmatter 2026 (`.agents/analysis/claude-code-skill-frontmatter-2026.md`)
- **Analysis**: agentskills.io Standard (`.agents/analysis/agentskills-io-standard-2026-01.md`)
- **Serena Memory**: claude-code-skill-frontmatter-standards (`.serena/memories/claude-code-skill-frontmatter-standards.md`)
- **Serena Memory**: agentskills-io-standard-integration (`.serena/memories/agentskills-io-standard-integration.md`)
- **Forgetful Memories**: IDs 99-110, 128-135, 167-174 (skill-related atomic memories)

---

## 10. Conflict Resolution Decision Matrix

When conflicts arise, use this priority order:

| Priority | Source | When to Apply |
|----------|--------|---------------|
| 1 | Official spec (agentskills.io + claude.com) | Portable skills, interoperability |
| 2 | ai-agents ADR (ADR-040) | Project-internal skills |
| 3 | SkillForge validator | Quality enforcement |
| 4 | Actual skill implementations | Pattern validation |
| 5 | Memory systems (Serena/Forgetful) | Historical context |

**Example Decision**: If official spec says space-delimited but ADR example shows comma-separated, official spec wins (Priority 1 > Priority 2).

---

## 11. Version History

### Version 1.0.0 (2026-01-09)

**Created**: Comprehensive reconciliation of all skill knowledge sources

**Resolved Conflicts**:

1. version field placement: TOP-LEVEL for ai-agents
2. model field existence: PROJECT-SPECIFIC EXTENSION
3. Required fields count: TWO-TIER SYSTEM (2 official, 5 ai-agents)
4. allowed-tools format: SPACE-DELIMITED (official standard)
5. metadata.subagent_model vs top-level model: BOTH (different purposes)

**Sources Reconciled**:

- Official standards (agentskills.io, claude.com)
- ADR-040 (ai-agents)
- Forgetful memories (IDs 99-110, 128-135, 167-174)
- Serena memories (claude-code-skill-frontmatter-standards, agentskills-io-standard-integration)
- Actual skill implementations (27 skills in `.claude/skills/`)
- Web research (agentskills.io, claude.com, GitHub repos)

---

## 12. Future Maintenance

### 12.1 Monitoring

Track these for standard evolution:

- [agentskills.io changelog](https://github.com/agentskills/agentskills/releases)
- [Anthropic Engineering blog](https://www.anthropic.com/engineering)
- Claude 5 announcements (anticipated 2026 H2)
- Model lifecycle updates (family alias migrations)

### 12.2 Update Triggers

This document should be updated when:

- Official specification changes (agentskills.io or claude.com)
- Claude 5 family releases (new model identifiers)
- New ai-agents extensions are standardized
- Conflicts are discovered in actual implementations
- Validation tools change requirements

### 12.3 Ownership

**Maintainer**: ai-agents project architecture team
**Review Frequency**: Quarterly or on standard update
**Related ADRs**: ADR-040 (must stay synchronized)

---

## Appendix A: Complete Example Skills

### A.1 Portable Skill (Official Standard Only)

```yaml
---
name: pdf-processing
description: Extract text and tables from PDF files, fill forms, merge documents. Use when asked to process PDFs, extract tables, or combine documents.
license: MIT
compatibility: Requires poppler-utils system package
allowed-tools: Bash Read Write
metadata:
  author: example-org
  category: document-processing
---

# PDF Processing

Process PDF files using poppler-utils.

## Usage

Ask me to extract text, tables, or merge PDFs.

## Requirements

System package: `poppler-utils`

Installation:
- Ubuntu/Debian: `apt-get install poppler-utils`
- macOS: `brew install poppler`
- Windows: Download from poppler.freedesktop.org
```

### A.2 ai-agents Optimized Skill (With Extensions)

```yaml
---
name: session-init
version: 1.0.0
description: Create protocol-compliant session logs with verification-based enforcement. Prevents recurring CI validation failures by reading canonical template from SESSION-PROTOCOL.md and validating immediately. Use when starting any new session.
license: MIT
model: claude-sonnet-4-5
metadata:
  domains:
    - session-protocol
    - compliance
    - automation
  type: initialization
  inputs:
    - session-number
    - objective
  outputs:
    - session-log
    - validation-report
---

# Session Init

Create protocol-compliant session logs.

## Quick Start

```powershell
pwsh .claude/skills/session-init/scripts/New-SessionLog.ps1
```

## References

See [references/workflow.md](references/workflow.md) for detailed workflow.
```

### A.3 Orchestrator Skill (With subagent_model)

```yaml
---
name: adr-review
version: 1.0.0
description: Multi-agent debate orchestration for Architecture Decision Records. Automatically triggers on ADR create/edit/delete. Coordinates architect, critic, independent-thinker, security, analyst, and high-level-advisor agents in structured debate rounds until consensus.
license: MIT
model: claude-opus-4-5
metadata:
  subagent_model: claude-opus-4-5  # Model for delegated agents
  domains:
    - architecture
    - governance
    - multi-agent
    - consensus
  type: orchestrator
  inputs:
    - adr-file-path
    - change-type
  outputs:
    - debate-log
    - updated-adr
    - recommendations
  file_triggers:
    patterns:
      - ".agents/architecture/ADR-*.md"
    events: [create, update, delete]
    auto_invoke: true
---

# ADR Review

Multi-agent debate pattern for rigorous ADR validation.

## Agent Roles

| Agent | Focus |
|-------|-------|
| architect | Structure, governance, coherence |
| critic | Gaps, risks, alignment |
| independent-thinker | Challenge assumptions |
| security | Threat models |
| analyst | Evidence, feasibility |
| high-level-advisor | Priority, conflict resolution |

## References

See [references/debate-protocol.md](references/debate-protocol.md) for full protocol.
```

---

## Appendix B: Field Quick Reference Table

| Field | Required | Location | Format | Max Length | Source |
|-------|----------|----------|--------|------------|--------|
| `name` | ✅ Official | Top-level | `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$` | 64 chars | agentskills.io |
| `description` | ✅ Official | Top-level | Free text, no XML | 1024 chars | agentskills.io |
| `version` | ✅ ai-agents | Top-level | Semantic versioning | - | ADR-040 |
| `license` | ✅ ai-agents | Top-level | SPDX identifier | - | ADR-040 |
| `model` | ✅ ai-agents | Top-level | Alias or dated ID | - | ADR-040 |
| `compatibility` | ⚪ Optional | Top-level | Free text | 500 chars | agentskills.io |
| `allowed-tools` | ⚪ Optional | Top-level | Space-delimited | - | agentskills.io |
| `disable-model-invocation` | ⚪ Optional | Top-level | Boolean | - | claude.com |
| `mode` | ⚪ Optional | Top-level | String | - | claude.com |
| `metadata.*` | ⚪ Optional | In metadata | Arbitrary KV | - | agentskills.io |

---

**END OF DOCUMENT**

This document is the single source of truth for skill standards in the ai-agents project. All conflicts have been resolved, all sources reconciled, and clear guidance provided for skill authors.
