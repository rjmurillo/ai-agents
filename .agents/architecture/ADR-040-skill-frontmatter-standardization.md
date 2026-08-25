---
id: ADR-040
status: accepted
date: 2026-07-11
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-040: Skill Frontmatter Standardization and Model Identifier Strategy

## Status

Accepted. **Section 1 (Model Identifier Format), the `model` row of the Section 2
field table, and Section 3 (Three-Tier Model Selection Strategy) are superseded
by [ADR-080](./ADR-080-model-pin-justification-policy.md) (2026-07-11).** Under
ADR-080 a skill or command may not carry a versioned model id at all: omit
`model:` and inherit the harness model, or use a bare rolling alias priced below
the default (today `haiku`) with a `model-rationale:` line.
`scripts/validation/check_model_pins.py` enforces this. The superseded text
below is kept as record, with the copyable examples corrected so no reader
lifts a pin the gate rejects.

## Date

2026-01-03

## Context

The ai-agents repository contains 27 Claude Code skills with inconsistent frontmatter configuration:

1. **Model Identifier Inconsistency**: Skills used mix of dated snapshots (`claude-opus-4-5-20251101`) and aliases (`claude-opus-4-5`)
2. **Frontmatter Structure Variance**: Some skills had `version` and `model` in top-level YAML, others in `metadata` object
3. **Validation Failures**: 404 errors from invalid model identifiers during skill invocation
4. **Documentation Gap**: No authoritative guidance on frontmatter requirements or model selection criteria

### Research Findings

Analysis of official Anthropic documentation (January 2026) revealed:

**Minimal Required Schema**:
- Only two fields mandatory: `name` (lowercase alphanumeric + hyphens, max 64 chars) and `description` (max 1024 chars, primary trigger mechanism)
- All other fields (`model`, `version`, `license`, `allowed-tools`, `metadata`) are optional

**Model Identifier Formats**:
- **Aliases** (e.g., `claude-opus-4-5`): Auto-update to latest snapshot within ~1 week of release
- **Dated Snapshots** (e.g., `claude-opus-4-5-20251101`): Fixed versions for reproducible behavior
- **CLI Shortcuts** (e.g., `opus`, `sonnet`, `haiku`): Convenient for interactive use

**Official Recommendation**:
- Use aliases for experimentation and skills (benefit from automatic improvements)
- Use dated snapshots for production APIs (ensure consistent reproducible behavior)

### Current State Analysis

Distribution before standardization:
- Mixed formats create confusion and maintenance burden
- No clear model selection criteria
- Frontmatter structure inconsistent across skills

## Decision

Adopt the following standardization for all 27 Claude Code skills:

### 1. Model Identifier Format

> **Superseded 2026-07-11 by [ADR-080](./ADR-080-model-pin-justification-policy.md)**:
> the decision recorded here was "use aliases such as `claude-opus-4-6` by
> default, with dated snapshots (`claude-sonnet-4-6-20260101`) allowed for
> security-critical skills". ADR-080 rule 1 bans both spellings on a skill or a
> command, because both are versioned ids: the harness cannot sweep a skill, so
> no evidence can justify one, and a retired id breaks CI (issue #2839). The
> conformant states are shown below; the original text is preserved in this
> note.

**Omit `model:` and inherit the harness model.** That is the default and needs
no justification:

```yaml
---
name: skill-identifier
description: What the skill does and when to use it
---
```

**Exception: cost.** A bare rolling alias that prices below the harness default
`claude-sonnet-4-6` may be pinned with a `model-rationale:` line. Today only
`haiku` qualifies:

```yaml
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
```

**Skills once listed here as snapshot-pinning candidates**: `security-detection`
ships `model: haiku` with a cost rationale today, and `session-log-fixer`
carries no `model:` line. Determinism is no longer a reason to pin; ADR-033 is
satisfied by the skill's own logic, not by a frozen model id.

**Rationale (superseded)**:
- Most skills benefit from automatic model improvements
- Security-critical skills may need deterministic behavior
- Hybrid approach balances improvement vs stability
- Dated IDs create maintenance burden but may be justified for compliance

### 2. Frontmatter Structure

Adopt consistent structure per SkillForge validation standards:

```yaml
---
name: skill-identifier       # Required (Official): matches directory name
version: X.Y.Z              # Required (SkillForge): semantic versioning
description: ...            # Required (Official): trigger mechanism with keywords
license: MIT                # Required (SkillForge): SPDX identifier
# model:                    # Optional (ADR-080): omit to inherit; bare cost alias only, never a versioned id
allowed-tools: Read, Grep   # Optional (Official): tool restrictions
metadata:                   # Optional (SkillForge): domain-specific fields
  domains: [...]
  type: ...
  complexity: ...
---
```

**Field Status**:

| Field | Status | Location | Source |
|-------|--------|----------|--------|
| `name` | Required | Top-level | Official Anthropic spec; SkillForge `REQUIRED_PROPERTIES` |
| `version` | Required by ai-agents convention | Top-level | Project convention; SkillForge lists it under `OPTIONAL_PROPERTIES` |
| `description` | Required | Top-level | Official Anthropic spec; SkillForge `REQUIRED_PROPERTIES` |
| `license` | Required by ai-agents convention | Top-level | Project convention; SkillForge lists it under `OPTIONAL_PROPERTIES` and `RECOMMENDED_PROPERTIES` |
| `model` | Optional (ADR-080) | Top-level | Omit to inherit; bare cost alias only |
| `model-rationale` | Optional (ADR-080) | Top-level | Required whenever `model` is set |
| `allowed-tools` | Optional | Top-level | Official Anthropic spec |
| `metadata` | Optional | Top-level | SkillForge convention |
| `metadata.*` | Optional | In metadata | Domain-specific fields |

**Rationale**:
- SkillForge validate-skill.py defines the authoritative structure
- The validator itself requires only `name` and `description`
  (`.claude/skills/SkillForge/scripts/_constants.py`:
  `REQUIRED_PROPERTIES = {'name', 'description'}`). `version` and `license` are
  an ai-agents project convention this ADR added on top; `license` is in
  `RECOMMENDED_PROPERTIES`. `model` was a fifth required field when this ADR was
  accepted; ADR-080 made it optional, and `_constants.py` now lists it under
  `OPTIONAL_PROPERTIES` with the comment "Optional model alias; omit to inherit,
  bare alias only, no versioned id"
- Metadata reserved for domain-specific extensions
- Consistent structure improves validation and packaging compatibility

### 3. Three-Tier Model Selection Strategy

> **Superseded 2026-07-11 by [ADR-080](./ADR-080-model-pin-justification-policy.md)**:
> the tier table below assigned each skill a versioned model id. Those
> assignments no longer exist in the tree: skills either omit `model:` or carry
> the bare `haiku` cost alias. Read the table as historical tier reasoning, not
> as values to copy into frontmatter. The "authoritative list" parentheticals
> describe a state that the ADR-080 migration removed.

Allocate models based on skill complexity:

| Tier | Model | Cost | Use Cases | ai-agents Skills |
|------|-------|------|-----------|------------------|
| **Tier 1: Opus** | `claude-opus-4-6` | $5/$25 per MTok | Maximum reasoning, multi-agent orchestration, architectural decisions, meta-programming | Examples: `adr-review`, `SkillForge`, `planner`, `merge-resolver`, `github`, `decision-critic`, `research-and-incorporate`, `slashcommandcreator`. (Authoritative list: skills with `model: claude-opus-4-6` in their SKILL.md frontmatter.) |
| **Tier 2: Sonnet** | `claude-sonnet-4-6` | $3/$15 per MTok | Standard workflows, coding, documentation, memory operations, security detection | Examples: `doc-accuracy`, `analyze`, `code-qualities-assessment`, `cva-analysis`, `incoherence`, `memory`, `memory-documentary`, `memory-enhancement`, `pr-comment-responder`, `prompt-engineer`, `security-scan`, `serena-code-architecture`, `threat-modeling`. (Authoritative list: skills with `model: claude-sonnet-4-6` in their SKILL.md frontmatter.) |
| **Tier 3: Haiku** | `claude-haiku-4-5` | $1/$5 per MTok | Speed-critical, simple pattern matching, high-frequency execution (hooks, validators) | Examples: `fix-markdown-fences`, `steering-matcher`, `metrics`, `observability`, `security-detection`, `stuck-detection`. (Authoritative list: skills with `model: claude-haiku-4-5` in their SKILL.md frontmatter.) |

**Selection Matrix**:

| Characteristic | Haiku | Sonnet | Opus |
|----------------|-------|--------|------|
| Reasoning Depth | Simple rules | Standard logic | Complex multi-step |
| Orchestration | None | Single agent | Multi-agent coordination |
| Latency Sensitivity | <1s critical | <5s acceptable | <30s acceptable |
| Frequency | Very high (hooks) | High (workflows) | Moderate (orchestration) |
| Cost Tolerance | Minimal | Standard | Premium justified |
| Error Impact | Low (cosmetic) | Medium (workflow) | High (architectural) |

### 4. Skill Quality Standards

**Required Elements**:
- YAML frontmatter with `name` and `description`
- Markdown instructions (body content)

**Description Quality** (YAML frontmatter):
- MUST include what the skill does AND when to use it (triggers)
- ALL "when to use" information in description, not body
- Include keywords users would naturally say
- Max 1024 characters

**Example**:
```yaml
# ❌ Too generic
description: Helps with testing

# ✅ Specific with what + when + keywords
description: Execute Pester tests with coverage analysis. Use when asked to "run tests", "check coverage", or "verify test suite".
```

**Body Quality** (Markdown content):
- Concise (< 500 lines preferred)
- Only include what Claude doesn't already know
- Use imperative/infinitive form ("Use this tool...", "Run the script...")
- No extraneous documentation

**Structure Requirements**:
- No README.md, INSTALLATION_GUIDE.md, or similar meta-documents
- Use `references/` subdirectory for detailed content
- References must be one level deep from SKILL.md
- Add table of contents (TOC) for files > 100 lines

**Progressive Disclosure**:
- Keep SKILL.md lean and focused
- Split content when approaching 500 lines
- Reference files must have clear, descriptive names
- Link from SKILL.md rather than embedding large content

### 6. Security: Tool Restrictions (allowed-tools)

Apply principle of least privilege:

```yaml
# Read-only analysis skills
allowed-tools: Read, Grep, Glob

# GitHub operations
allowed-tools: Bash(gh:*), Bash(pwsh:*), Read, Write

# Unrestricted (security risk - document justification)
# No allowed-tools field = full tool access
```

**Security Guidelines**:
- Skills without `allowed-tools` have unrestricted access (document why)
- Avoid `Bash` without path restrictions for untrusted input
- Security-sensitive skills MUST have explicit tool restrictions
- Review tool combinations for privilege escalation paths

## Consequences

### Positive

1. **Automatic Model Improvements**: Skills benefit from Anthropic's model enhancements without manual updates
2. **Consistent Structure**: Easier to understand, validate, and maintain skills across repository
3. **Clear Selection Criteria**: Model allocation based on documented complexity tiers
4. **Reduced Technical Debt**: No need to update 27 skills on each model release
5. **Better Performance**: Appropriate model selection optimizes cost/intelligence trade-off
6. **Validated Against Official Docs**: Aligned with Anthropic's current (2026-01) recommendations

### Negative

1. **Automatic Updates**: Skills may change behavior when aliases migrate to new snapshots (mitigated by Anthropic's <1 week gradual rollout)
2. **Platform Dependency**: Aliases work on Anthropic API; AWS Bedrock/GCP Vertex AI require platform-specific formats
3. **Cost Variability**: Model pricing may change with new releases (historically stable)

### Neutral

1. **Migration Required**: One-time update of all 27 skills (completed in Session #S356, commit 303c6d2)
2. **Documentation Maintenance**: Must update guidance when Claude 5 releases (anticipated 2026 H2)

## Implementation

### Phase 1: Standardization (In Progress)

> **Superseded 2026-04-30**: The "move into metadata" steps below were reversed. SkillForge validator now requires `name`, `version`, `description`, `license`, and `model` at **top level** (see Field Status table in Section 2 and the validator at `scripts/validation/skill_frontmatter.py`). Skills that ship today have `model` and `version` top-level. The bullets below are retained as historical record of the original Phase 1 plan.

> **Correction 2026-07-11 ([ADR-080](./ADR-080-model-pin-justification-policy.md))**:
> `model` is no longer required. `.claude/skills/SkillForge/scripts/_constants.py`
> sets `REQUIRED_PROPERTIES = {'name', 'description'}` and lists `model` under
> `OPTIONAL_PROPERTIES` with the comment "Optional model alias; omit to inherit,
> bare alias only, no versioned id". As of 2026-08-14, 7 of the 99 shipped
> skills carry a `model:` line and all 7 use the bare `haiku` alias.
> The 2026-04-30 note above is retained as written.

**Session #S356** (2026-01-03):
- Update all 27 model-tier-assigned skills to use model aliases (catalog count of skills WITH explicit `model:` frontmatter at that time; broader catalog included additional skills without tier assignment)
- ~~Restructure frontmatter (version/model into metadata object, per SkillForge validator)~~ Reversed; top-level retained.
- Validate against SkillForge packaging requirements
- Branch: `fix/update-skills-valid-frontmatter`

**Changes Required** (original plan; superseded, see note above; counts reflect S356 model-tier-assigned skills, not full catalog):
- 11 skills: Move `model: claude-opus-4-6` from top-level to `metadata.model`
- 12 skills: Move `model: claude-sonnet-4-6` from top-level to `metadata.model`
- 4 skills: Move `model: claude-haiku-4-5` from top-level to `metadata.model`

**Post-2026-05-09 M1 prune note:** of the 3 skills deleted in M1 (`doc-coverage`, `doc-sync`, `workflow`), only `doc-sync` was on the S356 model-tier-assigned list (Tier 2 Sonnet). `doc-coverage` and `workflow` either lacked explicit `model:` frontmatter or were added to the catalog after S356. Net effect on the model-tier-assigned population: 27 → 26 (Tier 2 Sonnet 12 → 11). The current-state table at lines 118-120 reflects this post-prune state.
- All skills: Move `version` from top-level to `metadata.version`
- All skills: Convert dated snapshots to aliases where appropriate

### Phase 2: Documentation (Completed)

**Artifacts Created**:
1. Comprehensive analysis: `.agents/analysis/claude-code-skill-frontmatter-2026.md` (4,847 words)
2. Serena memory: `claude-code-skill-frontmatter-standards`
3. Forgetful memories: 10 atomic memories (IDs 100-109) in knowledge graph

### Phase 3: Validation (Future)

**Recommended Actions**:
1. Create pre-commit validation script for skill frontmatter
2. Add skill model distribution metrics to `/metrics` skill
3. Create `docs/SKILL-AUTHORING.md` guide
4. Monitor Anthropic changelog for model lifecycle announcements
5. Plan migration strategy for Claude 5 family (when released)

## Compliance

### Related ADRs

- **ADR-007**: Memory-First Architecture (analysis stored in Serena + Forgetful for retrieval)
- **ADR-033**: Everything Deterministic Evaluation (security-critical skills may need snapshot pinning; superseded as a pinning rationale by ADR-080)
- **ADR-036**: Two-Source Agent Template Architecture (establishes that Claude skills are manually maintained)
- **ADR-039**: Agent Model Cost Optimization (agent-level model selection; this ADR addresses skill-level)
- **ADR-080**: Model Pins Require Cited Eval Evidence (supersedes this ADR's model identifier strategy: skills and commands may not carry a versioned id)

### Verification

Frontmatter validation checklist:

- [ ] Frontmatter starts with `---` on line 1 (no blank lines)
- [ ] `name`: lowercase, alphanumeric + hyphens, < 64 chars
- [ ] `description`: includes trigger keywords, < 1024 chars
- [ ] `model`: absent (inherit), or the bare cost alias `haiku` with a `model-rationale` line. Never a versioned id (ADR-080 rule 1)
- [ ] `allowed-tools`: comma-separated valid tools if present
- [ ] `tools`: uses block-style array format (hyphen-bulleted), not inline
- [ ] YAML uses spaces (not tabs) for indentation

### YAML Array Format

**Required Format**: Block-style arrays (hyphen-bulleted)

```yaml
# CORRECT: Block-style (cross-platform compatible)
tools:
  - read
  - edit
  - search

# INCORRECT: Inline/flow-style (causes Windows parsing errors)
tools: ['read', 'edit', 'search']
```

**Rationale**: Some YAML parsers on Windows systems cannot handle inline array syntax in frontmatter, causing "Unexpected scalar at node end" errors during agent installation. Block-style arrays ensure cross-platform compatibility.

**Implementation**: The `build/Generate-Agents.ps1` script parses templates with block-style `tools_vscode:` and `tools_copilot:` arrays and outputs them as block-style `tools:` arrays in generated files.

### Rollback Plan

If alias auto-updates cause issues:
1. Revert to dated snapshots: `git revert 303c6d2`
2. Update frontmatter with specific snapshot IDs
3. Document rationale in ADR amendment
4. Accept manual update burden on model releases

### Confirmation

Frontmatter compliance will be verified through:

1. **Pre-commit validation**: `scripts/Validate-SkillFrontmatter.ps1` (blocking gate)
2. **PR review checklist**: Frontmatter validation checkbox required
3. **Quarterly audit**: Model distribution metrics from `/metrics` skill

**Validation Script Criteria** (as specified in 2026-01; the PowerShell script
named above no longer exists, and the model rule is superseded, see below):

- Frontmatter starts with `---` on line 1
- Required fields present (`name`, `description`)
- ~~Model identifier matches pattern `^claude-((opus|sonnet)-4-6|haiku-4-5)(-\d{8})?$`~~
  Superseded by ADR-080: a versioned id is rejected on a skill or command.
  `scripts/validation/check_model_pins.py` is the current gate, and
  `.claude/skills/SkillForge/scripts/validate-skill.py` (Lefthook's `skillforge`
  job, staged `SKILL.md` files) validates the rest of the frontmatter.
- Description length <=1024 characters
- YAML syntax valid (no tabs, proper indentation)
- Arrays use block-style format (not inline `['...']` syntax)

### Reversibility Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| **Rollback capability** | Yes | `git revert 303c6d2` |
| **Vendor lock-in** | HIGH | Aliases are Anthropic-only; AWS Bedrock/GCP Vertex AI need platform-specific IDs |
| **Exit strategy** | Defined | Replace aliases with platform-specific dated IDs (2-4 hours for 27 skills) |
| **Legacy impact** | None | All 27 skills updated atomically |
| **Data migration** | N/A | Configuration files only, no data storage |

**Accepted Trade-off**: HIGH vendor lock-in is acceptable because:
1. Anthropic Claude Code is primary platform (no AWS Bedrock/GCP Vertex AI plans)
2. Auto-update benefit outweighs portability for this use case
3. Migration path is mechanical (bulk find/replace)

### Model Behavior Monitoring

To detect behavioral regression from model alias updates:

1. **Weekly smoke tests**: Run skill validation suite
2. **Alert threshold**: >5% failure rate increase triggers investigation
3. **Reversion policy**: Security-critical skill regression triggers immediate snapshot pinning
4. **Notification**: Monitor Anthropic Engineering blog for model update announcements

## References

### Official Documentation

- [Agent Skills - Claude Code Docs](https://code.claude.com/docs/en/skills)
- [Models overview - Claude Docs](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Model configuration - Claude Code Docs](https://code.claude.com/docs/en/model-config)
- [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [What's new in Claude 4.5](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-5)
- [GitHub - anthropics/skills](https://github.com/anthropics/skills)

### Project Artifacts

- Analysis: `.agents/analysis/claude-code-skill-frontmatter-2026.md`
- Memory: `.serena/memories/claude-code-skill-frontmatter-standards.md`
- Implementation commit: 303c6d2
- Session log: `.agents/sessions/2026-01-03-session-356.md` (pending)

### Future Monitoring

- Anthropic Engineering blog: https://www.anthropic.com/engineering
- Claude 5 announcements (anticipated 2026 H2)
- Model pricing updates: https://platform.claude.com/docs/en/about-claude/pricing
- Agent Skills standard evolution: https://agentskills.io

## Decision Makers

- **Analyst**: Claude Sonnet 4.5 (research and analysis)
- **Implementer**: Claude Sonnet 4.5 (standardization execution)
- **Architect**: Pending (ADR review via multi-agent debate)
- **Final Approval**: Richard Murillo (project owner)

## Amendments

### 2026-01-03: Multi-Agent Debate Resolution

**Debate Log**: `.agents/critique/ADR-040-debate-log.md`

**Changes from debate**:
1. **Hybrid model strategy**: Added exception for security-critical skills to use dated snapshots
2. **Field status table**: Distinguished official spec vs ai-agents convention
3. **Security guidance**: Added Section 6 with allowed-tools least-privilege guidance
4. **Confirmation section**: Added enforcement mechanism
5. **Reversibility assessment**: Added vendor lock-in analysis
6. **Model monitoring**: Added behavioral regression detection
7. **Related ADRs**: Added cross-references to ADR-033, ADR-039

**Dissent recorded**: Independent-thinker disagrees with aliases-by-default but commits to decision.

**Consensus**: 5 ACCEPT, 1 DISAGREE AND COMMIT

### 2026-01-13: YAML Array Format Standardization

**Issue**: Windows YAML parsers failed to parse inline array syntax in agent frontmatter, causing "Unexpected scalar at node end" errors during agent installation.

**Changes**:

1. **Block-style arrays required**: All `tools`, `tools_vscode`, and `tools_copilot` arrays must use block-style (hyphen-bulleted) format instead of inline arrays
2. **Parser update**: `build/Generate-Agents.Common.psm1` updated to parse block-style arrays in templates and output block-style arrays in generated files
3. **Verification checklist**: Added array format validation to frontmatter checklist

**Rationale**: Block-style YAML arrays are universally compatible across YAML parsers, while inline arrays with single quotes can cause parsing errors on some Windows systems.

**Files updated**:

- 18 template files in `templates/agents/`
- 54 generated files across 3 platforms (18 each in `.github/agents/`, `src/copilot-cli/`, and `src/vs-code-agents/`)
- `build/Generate-Agents.Common.psm1`

**Session**: 2026-01-13-session-826

### 2026-04-30: Opus/Sonnet 4-5 to 4-6 Migration

**Trigger**: Anthropic shipped Claude Opus 4.6 and Sonnet 4.6. No Haiku 4.6 released.

**Changes**:

1. Validator (`scripts/validation/skill_frontmatter.py`) tightened: `claude-opus-4-5` and `claude-sonnet-4-5` aliases removed from allowlist. Dated 4-5 snapshots for Opus/Sonnet also rejected.
2. All 69 source skills and 81 generated copies updated to `claude-{opus,sonnet}-4-6`. Haiku stays at `claude-haiku-4-5`.
3. ADR-040 prescriptive sections updated in place (Sections 1, 3, verification checklist, validation pattern).
4. `docs/SKILL-AUTHORING.md`, `.agents/architecture/SKILL-STANDARDS-RECONCILED.md`, `.agents/steering/claude-skills.md` updated to match.

**Unchanged**: Five-required-fields structure, alias-vs-snapshot strategy, three-tier model approach, security-critical snapshot pinning policy.

**ADR review**: Architect agent ACCEPT, zero blocking findings. Amendment is a version-string update, not a governance or structural change.

**Reversibility**: Revert the validator commit and bulk-replace 4-6 back to 4-5.
