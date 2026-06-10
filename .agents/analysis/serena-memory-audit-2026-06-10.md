# Serena Memory Audit and Cleanup (2026-06-10)

Session 2382. Audit of all 883 files under [`.serena/memories/`](../../.serena/memories/) (2.0 MB) for content that belongs in `.claude/rules/` or `.claude/skills/`, plus duplicate and corrupt-file cleanup. Detection: normalized-content MD5 hashing for exact duplicates, 8-token shingle Jaccard/containment scoring for near-duplicates (58 pairs at J >= 0.5 or containment >= 0.8), and a rules/skills overlap audit of suspect categories.

## What was removed (65 files)

### Corrupt or empty (5)

| File | Reason |
|------|--------|
| `adr/adr-014-findings.md` | 0 bytes, born empty in commit 34261da |
| `knowledge/bounded-contexts.md` | 0 bytes, born empty in commit 34261da, never had content |
| `adr/adr-021-quantitative-analysis.md` | Misnamed: content was the ADR-019 analysis. Moved to `adr/adr-019-quantitative-analysis.md` (which was 0 bytes); references rewritten |
| `CLAUDE.md`, `memory/CLAUDE.md` | claude-mem context stubs with no knowledge content, accidentally written as memories |

### Covered by always-loaded rules or skills (21)

| Files | Canonical source |
|-------|------------------|
| `serena/serena-001` through `serena-011` (11 files) plus `skills-serena-index.md` | [`.claude/rules/lsp-first.md`](../../.claude/rules/lsp-first.md) states the same three-tier navigation preference; AGENTS.md "Serena Init" covers activation |
| `session/init-001-serena-mandatory.md`, `init-001-serena-mandatory-initialization.md`, `init-001-session-initialization.md`, `session-init-serena.md` | AGENTS.md "Serena Init (BLOCKING)" plus the session-init skill |
| `session/init-002-skill-validation-gate.md` | AGENTS.md "Skill-First"; enforced by `invoke_skill_first_guard.py` hook |
| `cost/cost-005-serena-symbolic-tools.md` | `lsp-first.md` (same guidance, same rationale) |
| `knowledge/buy-vs-build-framework-skill.md` | [`buy-vs-build-framework` skill](../../.claude/skills/buy-vs-build-framework/SKILL.md) is canonical |
| `documentation-link-requirement.md` | Redundant restatement of `.agents/governance/DOCUMENTATION-LINK-REQUIREMENTS.md` |
| `user-preferences/user-preference-no-bash-python.md` | Superseded and contradicted by ADR-042 (Python-first, universal.md SHOULD 3) |
| `user-preferences/user-preference-no-auto-headers.md` and `-no-auto-generated-headers.md` | Migrated to `universal.md` MUST NOT 6 (see below) |

### Near-duplicate consolidation (37)

For each pair, the kept file fully contains the dropped file's knowledge (verified by line-level containment; the only "unique" lines lost were stale Related-link lists). Kept names favor live references (`.agents/SESSION-PROTOCOL.md`, `.claude/skills/memory/SKILL.md`, memory indexes). All links in remaining memories were rewritten to the kept names. Clusters:

- `bash/` singles folded into `bash-integration-*` (3)
- `ci/` short names folded into `ci-infrastructure-*` (10)
- `workflow/` folded into `workflow-patterns-*` (8)
- `pr-review/` `pr-review-{enum,status,anti-pattern}*` variants folded into the shorter referenced names with superset content (4)
- cross-directory duplicates: `skills/skills-{roadmap,regex,cva-refactoring,pr-validation-gates,prompt-engineering-quality-gates,dorny-paths-filter-checkout-requirement}`, `copilot/copilot-swe-anti-patterns`, `prompting/prompt-002-*`, `planning/scope-002-*`, `github/github-001-*`, `workflow/workflow-012-branch-handoffs`, `knowledge/chestertons-fence-memory-integration`, `memory/index-selection-decision-tree`, `session/session-init-003-*` (12)

## Migrations and corrections

| Change | Where |
|--------|-------|
| No-auto-generated-headers preference promoted to rule | `universal.md` MUST NOT 6; mirrors regenerated via `build/scripts/generate_rules.py` |
| Stale ADR-005 "no Python" constraint corrected to ADR-042 | `governance/governance-001-consolidated-constraints.md`, `session/session-init-constraints.md` |
| `usage-mandatory.md` trimmed to episodic incidents only | Rule text lives in AGENTS.md; enforcement is the skill-first guard hook |
| `memory-index.md` User Constraints section repointed | Now points at `universal.md` rule and `user-facing-content-restrictions` |

## Flagged, not changed (follow-up candidates)

- `pr-review/` partial-overlap series: `pr-comment-001..006` vs `pr-review-010..015` (6 pairs, containment 0.7 to 0.8). Same lessons, distinct numbering schemes; merging needs a decision on which numbering survives because both are cited by session logs.
- `jq/jq-pitfalls.md` vs `jq/jq-010-handling-pagination-results.md` (containment 0.87): the jq/ directory has both numbered and named variants throughout; a directory-wide consolidation pass is a separate lake.
- `governance/governance-001-consolidated-constraints.md` vs `session/session-init-constraints.md` (J 0.61): both restate PROJECT-CONSTRAINTS.md; candidate for deletion once PROJECT-CONSTRAINTS.md coverage is verified.
- `retrospective-best-practices-index.md` is 91 percent contained in `skills-retrospective-index.md`: index consolidation pass recommended.
- `skills/skills-bash-integration.md` consolidates the kept `bash/` memories (containment 0.85 to 0.95); intentional consolidation artifact, left in place.

## Impact

- 883 to 818 memory files (65 removed, 7.4 percent), about 134 KB of duplicate text gone from search results.
- `list_memories` output and memory-search results no longer return two near-identical hits per topic for the affected clusters.
- Two memories that actively contradicted current policy (ADR-042) corrected; one preference promoted to an always-loaded rule so it can no longer be missed by skipping memory search.
