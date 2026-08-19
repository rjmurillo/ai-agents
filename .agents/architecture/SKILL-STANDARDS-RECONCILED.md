# Skill Standards: Authoritative Reconciliation

**Date**: 2026-01-09
**Status**: CANONICAL REFERENCE
**Supersedes**: Fragmented documentation across memories, ADRs, and analysis documents

> **Model policy ([ADR-080](./ADR-080-model-pin-justification-policy.md),
> accepted 2026-07-11)**: a skill or command may not carry a versioned id. Omit
> `model:` and inherit the harness model, or use the bare cost alias `haiku`
> with a `model-rationale:` line. Every `model:` example below follows that
> rule. Enforced by `scripts/validation/check_model_pins.py`.

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
| `model` | Omitted (inherit), or a bare rolling alias priced below the default (`haiku`) | Override the harness-inherited model | ADR-080; versioned ids banned on skills |
| `model-rationale` | One line; required whenever `model` is set | Justify the cheaper tier | ADR-080 rule 3 |

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

**Guidance** (rewritten 2026-08-14; [ADR-080](./ADR-080-model-pin-justification-policy.md) supersedes the ADR-040-era rule that made `model` required and allowed dated ids):

- **ai-agents skills**: OPTIONAL. Omit it and inherit the harness model. That is
  the default and needs no justification.
- **Portable skills**: OMIT this field (use platform defaults)
- **Value format**: never a versioned id (`claude-opus-4-6`, `claude-haiku-4-5`,
  `claude-opus-4-6-20251015`). A skill cannot be swept by the eval harness, so
  no evidence can justify a version pin, and
  `scripts/validation/check_model_pins.py` rejects one. The only allowed pin is
  a bare rolling alias that prices below the harness default (today `haiku`)
  carrying a `model-rationale:` line.

### Conflict 3: Required Fields Count

**Sources**:

- **Official spec (agentskills.io + claude.com)**: Only 2 required (name, description)
- **ADR-040 (ai-agents)**: 5 required (name, version, description, license, model)
- **Forgetful Memory 99**: Confirms 5 required for ai-agents

**Resolution**: **TWO-TIER REQUIREMENT SYSTEM**

| Tier | Required Fields | Scope |
|------|----------------|-------|
| **Official Standard** | `name`, `description` | Portable skills, cross-platform |
| **ai-agents Project** | `name`, `version`, `description`, `license` | Project-internal skills |

> **Superseded 2026-07-11 by [ADR-080](./ADR-080-model-pin-justification-policy.md)**:
> `model` was the fifth required field in the ADR-040 era. It is now optional
> and usually absent. `.claude/skills/SkillForge/scripts/_constants.py` lists
> `model` under `OPTIONAL_PROPERTIES` with the comment "Optional model alias;
> omit to inherit, bare alias only, no versioned id".

**Rationale**:

- Official standard intentionally minimal for interoperability
- ai-agents project has higher quality bar (versioning, licensing)
- Two-tier system allows both portable skills and project-optimized skills

**Validation**:

- External skills: Validate against 2-field minimum (portable)
- ai-agents skills: Validate against the 4-field project standard

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
| `model` | Top-level | Model that executes THIS skill | Only as a bare cost alias with `model-rationale` (ADR-080); otherwise omit |
| `metadata.subagent_model` | In metadata | Model for agents THIS skill delegates to | Never carry a value; omit the key. `check_model_pins.py` has no alias-rule coverage for nested keys, so any value here, versioned or bare alias, is a hard violation (ADR-080). |

**Rationale**:

- These fields serve different purposes and are not in conflict
- Orchestrator skills may use a different model than the agents they invoke
- Example: adr-review omits both `model` and `subagent_model` (both inherit)

**Scope note (2026-08-18, issue #4936)**: ADR-080 now governs every key in
`MODEL_BEARING_KEYS` (`scripts/validation/check_model_pins.py`), currently
`{"model", "subagent_model"}`. `_collect_nested_pins` and `_nested_pins` match
`key in MODEL_BEARING_KEYS`, and any value under a nested model-bearing key is
a hard violation with no alias-rule exception: `_unit_rule_failure` returns
immediately whenever `unit.nested_pins` is non-empty, before the code path
that lets a top-level bare alias pass with a `model-rationale`. So a nested
`subagent_model` cannot even carry `opus`; the conformant state is to omit the
key entirely, same as `model`. This supersedes the prior scope note, which
predated issue #4936 and described `subagent_model` as outside the gate and
"inert metadata"; that was true only until this fix (PR #5098) closed the gap.
Four files carried a versioned `subagent_model` pin under the stale guidance
and were fixed in the same PR: `.claude/skills/adr-review/SKILL.md`,
`.claude/skills/skillforge/SKILL.md`, and their `src/copilot-cli` mirrors.

**Example (orchestrator)**: abridged from `.claude/skills/adr-review/SKILL.md`.

```yaml
---
name: adr-review
# No model: line. The orchestrator inherits the harness model (ADR-080).
metadata:
  # No subagent_model: line either. A nested model-bearing key has no
  # alias-rule coverage, so any value here is a hard ADR-080 violation
  # (issue #4936). Omit it; delegated agents inherit the harness model.
```

**Example (non-orchestrator)**: abridged from `.claude/skills/session-init/SKILL.md`.

```yaml
---
name: session-init
# No model: line. Inherits the harness model (ADR-080).
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

# OPTIONAL (ADR-080 model policy; omit both lines to inherit the harness model)
model: haiku                         # Bare cost alias only, never a versioned id
model-rationale: cost. ...           # Required whenever model is set

# OPTIONAL (Official Standard)
compatibility: Requires network      # Max 500 chars, env requirements
allowed-tools: Read Grep Glob        # Space-delimited tool list

# OPTIONAL (Claude Code)
disable-model-invocation: false      # Prevent auto-invoke
mode: context                        # Mode command category

# OPTIONAL (ai-agents Extensions)
metadata:
  # Orchestrator-specific
  # subagent_model omitted: ADR-080 forbids any value on a nested
  # model-bearing key (issue #4936), so delegated agents inherit the
  # harness model with no pin to write here.

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

#### model (OPTIONAL; omit to inherit, per ADR-080)

- **Type**: String
- **Format**: bare rolling alias (`sonnet`, `opus`, `haiku`). A versioned id
  (`claude-opus-4-6`, `claude-haiku-4-5`, or any dated snapshot) is rejected on
  a skill or command by `scripts/validation/check_model_pins.py`:
  `skill carries versioned id '...'; skills and commands may not pin a version (ADR-080 rule 1)`
- **Default**: absent. The skill inherits the harness model, which is correct
  and needs no justification.
- **Allowed pin**: only an alias that resolves, through `model_tiers` in
  `templates/platforms/copilot-cli.yaml`, to a model priced below the harness
  default `claude-sonnet-4-6`. Today that is `haiku` alone
  (`claude-haiku-4.5`, $1/$5 per MTok versus $3/$15). `sonnet` and `opus` fail
  with `cost rationale on '...' but it does not price below the default`.
- **Companion field**: `model-rationale` is required whenever `model` is set.
- **Agents differ**: ADR-080 rule 2 allows a versioned pin on an *agent* backed
  by a KEEP_PIN sweep entry in `.agents/governance/model-pin-evidence.json`.
  That path does not exist for skills or commands.
- **Selection Criteria** (historical tier guidance; use it to judge whether the
  cheap tier suffices, not to write a versioned id):

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
  - `subagent_model`: Model for delegated agents (orchestrators). ADR-080
    forbids a value here (issue #4936); omit the key so delegates inherit
    the harness model.
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
- [ ] `model` (ai-agents): absent, or the bare cost alias `haiku` with a `model-rationale` line (ADR-080). Never a versioned id such as `claude-opus-4-6`
- [ ] `model-rationale` (ai-agents): present whenever `model` is set
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
metadata:
  domains: [analysis]  # Domain-specific fields remain
---
```

### 7.2 From a Versioned Pin to Inherit or a Cost Alias

Rewritten 2026-08-14. This section previously told authors to convert dated
snapshots into versioned aliases (`claude-opus-4-6-20251015` to
`claude-opus-4-6`). [ADR-080](./ADR-080-model-pin-justification-policy.md)
rule 1 bans both spellings on a skill or command: each is a versioned id, each
breaks when that model retires (issue #2839), and no sweep can justify either
because the harness cannot evaluate a skill.

**Before** (versioned id, dated or not):

```yaml
---
model: claude-opus-4-6-20251015
---
```

**After, default** (delete the line and inherit the harness model):

```yaml
---
name: my-skill
description: Does something useful
---
```

**After, cost exception** (bare alias priced below the default, with its
rationale; today only `haiku` qualifies):

```yaml
---
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
---
```

**Determinism is no longer a reason to pin.** The ADR-040-era exception for
security-critical skills (`security-detection`, `session-log-fixer`) is
superseded: `.claude/skills/security-detection/SKILL.md` ships `model: haiku`
with a cost rationale, `.claude/skills/session-log-fixer/SKILL.md` carries no
`model:` line at all, and a versioned pin on either would fail the gate.

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

- Include the 4 required fields: `name`, `version`, `description`, `license`
- Leave `model` out unless a cost alias is justified (ADR-080)
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
# No model: line. Inherits the harness model (ADR-080), as the shipped skill does.
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

```bash
python3 .claude/skills/session-init/scripts/new_session_log.py
```

## References

See [references/workflow.md](references/workflow.md) for detailed workflow.
```

### A.3 Orchestrator Skill (Delegated Agents Inherit The Harness Model)

```yaml
---
name: adr-review
version: 1.0.0
description: Multi-agent debate orchestration for Architecture Decision Records. Automatically triggers on ADR create/edit/delete. Coordinates architect, critic, independent-thinker, security, analyst, and high-level-advisor agents in structured debate rounds until consensus.
license: MIT
# No model: line. Orchestration is not a reason to pin (ADR-080).
metadata:
  # No subagent_model: line either (issue #4936). A nested model-bearing
  # key has no alias-rule coverage, so any value is a hard ADR-080
  # violation; the delegated agents inherit the harness model.
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
| `model` | ⚪ Optional | Top-level | Bare cost alias (`haiku`) or absent; no versioned id | - | ADR-080 |
| `model-rationale` | ⚪ Optional | Top-level | Free text; required when `model` is set | - | ADR-080 |
| `compatibility` | ⚪ Optional | Top-level | Free text | 500 chars | agentskills.io |
| `allowed-tools` | ⚪ Optional | Top-level | Space-delimited | - | agentskills.io |
| `disable-model-invocation` | ⚪ Optional | Top-level | Boolean | - | claude.com |
| `mode` | ⚪ Optional | Top-level | String | - | claude.com |
| `metadata.*` | ⚪ Optional | In metadata | Arbitrary KV | - | agentskills.io |

---

**END OF DOCUMENT**

This document is the single source of truth for skill standards in the ai-agents project. All conflicts have been resolved, all sources reconciled, and clear guidance provided for skill authors.
