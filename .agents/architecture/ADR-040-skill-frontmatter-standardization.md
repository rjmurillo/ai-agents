# ADR-040: Skill Frontmatter Standardization and Model Identifier Strategy

## Status

Accepted (pending owner approval)

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

**Use aliases by default** (`claude-{tier}-4-5`) for most skills:

```yaml
model: claude-opus-4-5      # Default: auto-updates
model: claude-sonnet-4-5    # Default: auto-updates
model: claude-haiku-4-5     # Default: auto-updates
```

**Exception: Security-Critical Skills** may use dated snapshots when deterministic behavior is required:

```yaml
model: claude-sonnet-4-5-20250929  # Pinned version
```

**Current Security-Critical Skills** (eligible for snapshot pinning):
- `security-detection`: Triggers security reviews (false negatives = security incidents)
- `session-log-fixer`: Validates session protocol (deterministic per ADR-033)

**Rationale**:
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
model: claude-{tier}-4-5    # Required (SkillForge): model alias or snapshot
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
| `name` | Required | Top-level | Official Anthropic spec |
| `version` | Required | Top-level | SkillForge validator |
| `description` | Required | Top-level | Official Anthropic spec |
| `license` | Required | Top-level | SkillForge validator |
| `model` | Required | Top-level | SkillForge validator |
| `allowed-tools` | Optional | Top-level | Official Anthropic spec |
| `metadata` | Optional | Top-level | SkillForge convention |
| `metadata.*` | Optional | In metadata | Domain-specific fields |

**Rationale**:
- SkillForge validate-skill.py defines the authoritative structure
- Required fields (name, version, description, license, model) at top-level
- Metadata reserved for domain-specific extensions
- Consistent structure improves validation and packaging compatibility

### 3. Three-Tier Model Selection Strategy

Allocate models based on skill complexity:

| Tier | Model | Cost | Use Cases | ai-agents Skills |
|------|-------|------|-----------|------------------|
| **Tier 1: Opus** | `claude-opus-4-5` | $5/$25 per MTok | Maximum reasoning, multi-agent orchestration, architectural decisions, meta-programming | 11 skills (40.7%): adr-review, skillcreator, planner, merge-resolver, github, analyze, decision-critic, research-and-incorporate, session-log-fixer, incoherence, memory |
| **Tier 2: Sonnet** | `claude-sonnet-4-5` | $3/$15 per MTok | Standard workflows, coding, documentation, memory operations, security detection | 12 skills (44.4%): doc-sync, memory systems, pr-comment-responder, programming-advisor, prompt-engineer, security-detection, serena-code-architecture |
| **Tier 3: Haiku** | `claude-haiku-4-5` | $1/$5 per MTok | Speed-critical, simple pattern matching, high-frequency execution (hooks, validators) | 4 skills (14.8%): fix-markdown-fences, steering-matcher, session |

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

**Session #S356** (2026-01-03):
- Update all 27 skills to use model aliases
- Restructure frontmatter (version/model into metadata object, per SkillForge validator)
- Validate against SkillForge packaging requirements
- Branch: `fix/update-skills-valid-frontmatter`

**Changes Required**:
- 11 skills: Move `model: claude-opus-4-5` from top-level to `metadata.model`
- 12 skills: Move `model: claude-sonnet-4-5` from top-level to `metadata.model`
- 4 skills: Move `model: claude-haiku-4-5` from top-level to `metadata.model`
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
- **ADR-033**: Everything Deterministic Evaluation (security-critical skills may need snapshot pinning)
- **ADR-036**: Two-Source Agent Template Architecture (establishes that Claude skills are manually maintained)
- **ADR-039**: Agent Model Cost Optimization (agent-level model selection; this ADR addresses skill-level)

### Verification

Frontmatter validation checklist:
- [ ] Frontmatter starts with `---` on line 1 (no blank lines)
- [ ] `name`: lowercase, alphanumeric + hyphens, < 64 chars
- [ ] `description`: includes trigger keywords, < 1024 chars
- [ ] `model`: valid alias (`claude-{tier}-4-5`) if present
- [ ] `allowed-tools`: comma-separated valid tools if present
- [ ] YAML uses spaces (not tabs) for indentation

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

**Validation Script Criteria**:
- Frontmatter starts with `---` on line 1
- Required fields present (`name`, `description`)
- Model identifier matches pattern `^claude-(opus|sonnet|haiku)-4-5(-\d{8})?$`
- Description length <=1024 characters
- YAML syntax valid (no tabs, proper indentation)

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
