# AGENTS.md

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`|Post-compaction: re-run 1+2

## Retrieval-Led Reasoning

Read first, reason second. Pre-training last resort.

|APIs: Context7, DeepWiki, WebSearch
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
|Memory: `memory` skill, not `list_memories`
|ADRs: `.agents/architecture/ADR-*.md`|Protocol: `.agents/SESSION-PROTOCOL.md`|Skills: `.claude/skills/{name}/SKILL.md`
|Path rules: read matching `.claude/rules/*.md` by `applyTo` first|Generators (edit source): `.agents/governance/GENERATOR-FILES.md`

## Session Gates

**Start**: Init Serena|Read HANDOFF.md + latest issue handoff + Verify-on-Resume|Session log|Search memories|Verify git
**Mid**: Commits `git rev-list --count HEAD ^origin/main` ≤20, warn 15 (ADR-008)
**Pre-PR**: `python3 scripts/validation/pre_pr.py`|No BLOCKING|Security scan|Style: `.gemini/styleguide.md`
**End**: Complete log|Preserve HANDOFF.md|Issue handoff|Update Serena|Lint|Commit|Validate JSON

## Boundaries

**BLOCKING (verify)**: unrun gen'd artifact→runtime-contract test|security thread unfixed (CWE/OWASP/CVE)→security agent|skip validation→`pre_pr.py`
**Always**: Python scripts (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|PR template|Atomic commits ≤5 files|Scoped lint|Pin Actions SHA|Run changed workflows|Bump `plugin.json` on plugin change
**Ask First**: Architecture|New ADRs|Breaking|Security-sensitive
**Autonomy Guardrail**: Internal+reversible: act|External/irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|Update HANDOFF.md|Use bash|Logic in YAML (ADR-006)|Raw gh when skills exist|Force push|Skip hooks|Internal refs in src/|Scratch in tree (use `$TMPDIR`)

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect|Lifecycle: /spec /plan /build /test /review /ship
|CI-feedback sub-loop: cluster, ladder build->test->review->ship/cluster. See `.agents/governance/CI-FEEDBACK-SUBLOOP.md`
|New capability (module/scanner/validator/pipeline): buy-vs-build Quick tier BEFORE spec-generator + effectiveness baseline; >13wk no baseline = prune. Skip: bug fix, doc-only, refactor

### ADR Review (BLOCKING)

Any `ADR-*.md` or `SESSION-PROTOCOL.md` create/edit fires adr-review.

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `tests/`|`.claude/skills/<name>/tests/`|`.agents/security/benchmarks/`|`uv run pytest tests/ -x`|`uv run ruff check .`
Tests (BLOCKING): pos+neg+edge|every branch|mock I/O|CLI argv exits. See `.agents/governance/TESTING-RIGOR.md`

## Stack

Python 3.14|UV|PowerShell 7.5.4+|Node LTS|Pester 5.7.1|pytest 8+|gh 2.60+
