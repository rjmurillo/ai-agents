# ADR-Style Review: Skill Description and Trigger Standard

**Document**: `.agents/governance/skill-description-trigger-standard.md`
**Date**: 2026-01-03
**Session**: 372
**Rounds**: 1

## Executive Summary

**Final Verdict: NEEDS_REVISION (4/6 agents)**

The standard addresses a real problem (skill discoverability) with sound structure, but has critical gaps that must be addressed before adoption.

## Verdict Summary

| Agent | Verdict | Key Concern |
|-------|---------|-------------|
| **Architect** | ACCEPT | Minor clarity issues (P1-P2) |
| **Critic** | NEEDS_REVISION | Metadata field inconsistency, description length conflicts (P0) |
| **Independent-Thinker** | NEEDS_REVISION | Static triggers don't capture context; maturity levels missing |
| **Security** | NEEDS_REVISION | Trigger injection risk, no operation allowlist (P0) |
| **Analyst** | NEEDS_REVISION | 150-250 char range unsupported; validator checks words not chars |
| **High-Level-Advisor** | ACCEPT | Sound standard, but enforcement plan incomplete |

## Consolidated Issues

### P0 (Blocking)

| ID | Issue | Raised By | Impact |
|----|-------|-----------|--------|
| P0-1 | **CONFLICT WITH ANTHROPIC GUIDANCE**: Standard mandates `## Triggers` section, but Claude Code spec says description is "primary trigger" with no required section | User, Serena Memory | Standard contradicts upstream |
| P0-2 | **Description length mismatch**: Standard says 150-250 chars, validator checks 10+ words | Analyst, Critic | Skills pass/fail unpredictably |
| P0-3 | **Trigger injection vulnerability**: No input validation on trigger phrases | Security | CWE-94 code injection risk |
| P0-4 | **Operation allowlist missing**: Trigger tables can reference arbitrary scripts | Security | Supply chain attack vector |
| P0-5 | **3 skills have empty descriptions**: github, merge-resolver, programming-advisor | Critic, Analyst | Standard can't be enforced until fixed |

### Critical Conflict: Triggers Section Requirement

**Source**: Serena memory `claude-code-skill-frontmatter-standards`

**Anthropic/Claude Code Specification**:
```yaml
# Only TWO fields are mandatory:
name: skill-identifier
description: What the skill does and when to use it  # max 1024 chars, PRIMARY TRIGGER
```

> "Description: non-empty, max 1024 chars, **include trigger keywords**"

**Our Standard (Line 118)**:
> "Every skill MUST have a `## Triggers` section immediately after the frontmatter and title."

**Resolution Options**:
1. **REMOVE Triggers MUST** - Make triggers section OPTIONAL (RECOMMENDED for complex skills)
2. **CHANGE to description-first** - Triggers in description, section for discoverability
3. **DOCUMENT exception** - Note that our project adds this requirement beyond Anthropic spec

**Recommendation**: Option 2 - Keep triggers section as RECOMMENDED (not REQUIRED), but mandate trigger keywords in description per Anthropic spec.

### P1 (Must Resolve or Defer)

| ID | Issue | Raised By | Impact |
|----|-------|-----------|--------|
| P1-1 | **"Natural language" undefined**: No criteria for what passes | Critic, Analyst | Subjective enforcement |
| P1-2 | **Validator path wrong**: References `scripts/validate-skill.py` but actual path is `.claude/skills/SkillForge/scripts/validate-skill.py` | Architect | Broken documentation |
| P1-3 | **Trigger collision resolution undefined**: What happens when two skills match same phrase? | High-Level-Advisor | Discovery ambiguity |
| P1-4 | **Migration timeline missing**: 28 skills need updates, no schedule | High-Level-Advisor, Analyst | Enforcement date unclear |
| P1-5 | **Provenance metadata missing**: No source, author, or integrity fields | Security | Cannot verify skill origin |

### P2 (Should Fix)

| ID | Issue | Raised By |
|----|-------|-----------|
| P2-1 | Trigger placement rule contradicts examples | Critic |
| P2-2 | Part 5 patterns incomplete (missing meta-skills, analysis types) | Architect |
| P2-3 | Maturity levels missing (experimental vs stable) | Independent-Thinker |
| P2-4 | Typosquatting detection absent | Security |
| P2-5 | Trigger format not standardized (table vs list) | Critic |

## Strategic Assessment

### What's Right

- Formula (verb + what + when + outcome) is teachable and measurable
- Examples are clear before/after comparisons
- Trigger patterns (command+context, question, problem, request) are concrete
- Evidence base exists (28-skill analysis)

### What's Wrong

- Enforcement is aspirational (references SkillForge rejection, but SkillForge not fully implemented)
- Security implications not considered
- Validator-standard alignment gaps create confusion
- Migration burden hidden (who updates 28 existing skills?)

### Recommendations for Acceptance

**Minimum Required for ACCEPT:**

1. Add P0 security mitigations:
   - Define trigger phrase character whitelist: `[a-zA-Z0-9 \-:,]`
   - Require operation paths be relative, no `..`
   - Add to Part 4 validation rules

2. Align description validation:
   - Document that validator checks 10+ WORDS, not chars
   - Update checklist to reflect actual enforcement
   - Keep 150-250 as "recommended" not "enforced"

3. Define "natural language":
   - Replace with: "Triggers must match one of 4 patterns: command+context, question, problem statement, request+goal"

4. Add migration section:
   - List 3 skills with empty descriptions
   - Define ownership for updating them
   - Set enforcement date (e.g., 2026-02-01)

5. Fix validator path reference

**Deferred for Future:**

- Skill maturity levels (Independent-Thinker)
- Trigger collision resolution (High-Level-Advisor)
- Provenance metadata (Security)
- Typosquatting detection (Security)

## Agent Dissent Record

### Independent-Thinker Dissent (Disagree-and-Commit)

> "Static triggers don't capture context. A skill valid for 'fix PR conflicts' also works for 'resolve rebase issues' - these aren't variations, they're contextual equivalences the static table can't capture."

**Acknowledgment**: This is valid. Static triggers are a first approximation. Accept with understanding that context-aware routing is a future improvement, not a v1.0 requirement.

### Security Dissent (Blocking until P0 addressed)

> "Mark standard as DRAFT until P0 mitigations (trigger validation, operation allowlist) are implemented. Current version exposes code injection and supply chain risks."

**Acknowledgment**: P0 security mitigations are non-negotiable. Must be addressed before marking standard as Canonical.

## Next Steps

1. **Author** updates standard with P0 fixes (30-45 min)
2. **Security** re-reviews trigger validation rules
3. **Round 2** vote if P0 addressed: target ACCEPT or D&C
4. If ACCEPT: Add to CLAUDE.md index via doc-sync
5. Create enforcement timeline (issue or ADR)

## Appendix: Full Agent Reviews

### Architect Review

**Verdict**: ACCEPT

Structure is solid. Coherence with ADR-040 is strong. Minor P1-P2 issues around path references and pattern completeness. Ready for publication with edits.

Key points:
- P1: Validator path reference incorrect
- P1: Description length guidance should reference ADR-040
- P2: Part 5 patterns incomplete (missing meta-skills)

### Critic Review

**Verdict**: NEEDS_REVISION

Three critical gaps:
1. Metadata field locations inconsistent
2. Description length spec (150-250) conflicts with validator (10+ words)
3. PowerShell-only constraint not mentioned

Subjectivity risk: "Natural language" undefined.

### Independent-Thinker Review

**Verdict**: NEEDS_REVISION

Challenged assumptions:
1. Triggers enable discoverability - agents use routing, not triggers
2. 3-5 phrases sufficient - contexts vary, static triggers stale
3. 150-250 chars arbitrary - no cognitive load research cited
4. Uniform format forces all skills into same mold

Alternative proposed: Context-aware triggers, outcome-first descriptions, maturity levels.

### Security Review

**Verdict**: NEEDS_REVISION

Critical findings:
- CWE-94: Trigger injection via unsanitized user input
- CWE-78: Command injection if trigger text used in shell
- CWE-434: No skill signature verification
- CWE-200: Error messages in triggers expose internal logic

P0 mitigations required:
- Trigger character whitelist
- Operation path allowlist
- Provenance metadata

### Analyst Review

**Verdict**: NEEDS_REVISION

Evidence gaps:
- 150-250 char range unsupported by data
- Validator checks WORDS (10+), not chars - misalignment
- "Natural language" undefined
- Migration path incomplete for 3 empty-description skills

Feasibility: 45 min to fix, low complexity.

### High-Level-Advisor Review

**Verdict**: ACCEPT (with enforcement caveat)

Strategic assessment positive:
- Solves real problem (skill discovery broken)
- Formula is teachable
- Evidence base exists

Concerns:
- Enforcement undefined (SkillForge not built)
- Migration burden hidden
- Trigger collision unaddressed

Priority: P1 (not P0). Publish now, enforce after SkillForge validated.

## Debate Metadata

| Attribute | Value |
|-----------|-------|
| Document | skill-description-trigger-standard.md |
| Type | Governance Standard |
| Review Date | 2026-01-03 |
| Rounds | 1 |
| Consensus | NOT REACHED (4 NEEDS_REVISION, 2 ACCEPT) |
| Next Action | Author addresses P0, Round 2 vote |
