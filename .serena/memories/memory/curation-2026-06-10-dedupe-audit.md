# Memory Curation: 2026-06-10 Audit and Dedupe (Session 2382)

Full report: `.agents/analysis/serena-memory-audit-2026-06-10.md`.

## What changed

- 65 memory files removed (883 to 818): 5 corrupt/empty, 21 covered by rules/skills, 37 near-duplicates with content fully contained in a kept file (verified by line containment, not just similarity score).
- Misnamed `adr/adr-021-quantitative-analysis` (content was ADR-019 analysis) moved to `adr/adr-019-quantitative-analysis`.
- No-auto-generated-headers user preference promoted to `.claude/rules/universal.md` MUST NOT 6; both user-preference memories deleted.
- Stale ADR-005 "MUST NOT create Python scripts" blocks in `governance/governance-001-consolidated-constraints` and `session/session-init-constraints` corrected to ADR-042 Python-first.
- `usage-mandatory` trimmed to episodic incidents; the rule is canonical in AGENTS.md, enforced by `invoke_skill_first_guard.py`.

## Naming conventions confirmed by reference counts

- `ci/` canonical prefix: `ci-infrastructure-*`
- `workflow/` canonical prefix: `workflow-patterns-*`
- `bash/` canonical prefix: `bash-integration-*`
- Do not recreate short-name variants of these; check the index before writing.

## Open follow-ups (do not redo the analysis)

- `pr-review/pr-comment-001..006` vs `pr-review-010..015` partial overlap (6 pairs) unresolved.
- `jq/` directory has numbered plus named variants; needs its own consolidation pass.
- `retrospective-best-practices-index` 91 percent contained in `skills-retrospective-index`.
- `governance-001-consolidated-constraints` vs `session-init-constraints` both restate PROJECT-CONSTRAINTS.md.
