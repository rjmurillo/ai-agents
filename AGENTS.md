# AGENTS

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`|Post-compaction: re-run 1+2

## Retrieval

Read first.

|APIs: Context7, DeepWiki, WebSearch|Memory: `memory` skill
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`|ADRs: `.agents/architecture/ADR-*.md`
|Protocol: `.agents/SESSION-PROTOCOL.md`|Skills: `.claude/skills/{name}/SKILL.md`
|Rules: read `.claude/rules/*.md` by `applyTo` first|Generators: `.agents/governance/GENERATOR-FILES.md`

## Gates

**Start**: Init Serena|Read HANDOFF.md + latest issue handoff + resume verify|Session log|Search memories|Verify git
**Mid**: `git rev-list --count HEAD ^origin/main` <=20, warn >15 (ADR-008)
**Pre-PR**: `python3 scripts/validation/pre_pr.py`|No BLOCKING|Security scan|Style `.gemini/styleguide.md`
**End**: Complete log|Preserve HANDOFF.md|Issue handoff if open|Update Serena|Lint|Commit|Validate

## Boundaries

**BLOCKING verify**: unrun gen'd artifact -> runtime test|security thread -> code fix or owner|skip validation -> `pre_pr.py`
**Always**: Python (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|PR template|Atomic commits <=5 files|Scoped lint|Pin Actions SHA|Run changed workflows pre-push|Bump `plugin.json` on plugin-source change
**Ask First**: Architecture|New ADRs|Breaking|Security
**Autonomy Guardrail**: Internal+reversible: act|External/irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|Update HANDOFF.md|Use bash|Logic in YAML (ADR-006)|Raw gh when skills exist|Force push|Skip hooks|Internal refs in src/|Scratch in tree|Resolve security threads without vuln fix|Ship unrun gen'd artifact

## Context

Knowledge -> passive context (@imports, every turn, outside training, <8KB). Actions -> skills (tools, workflows, mutation).

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect|Lifecycle: /spec /plan /build /test /review /ship
|CI-feedback sub-loop: cluster, ladder build->test->review->ship. See `.agents/governance/CI-FEEDBACK-SUBLOOP.md`
|New capability (Context/module/scanner/validator/pipeline): buy-vs-build Quick tier BEFORE spec-generator + baseline; >13wk no baseline = prune. Skip: bug, doc, refactor, approved extension

### ADR Review

Any `ADR-*.md` or `SESSION-PROTOCOL.md` create/edit fires adr-review.

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `uv run pytest tests/ -x`|`uv run ruff check .`|`tests/`|`.claude/skills/<name>/tests/`
Tests (BLOCKING): pos+neg+edge|branches|mock I/O|CLI exits. See `.agents/governance/TESTING-RIGOR.md`

## Stack

Python 3.14 (floor per pyproject)|UV|PowerShell 7.5.4+|Node LTS|Pester 5.7.1|pytest 8+|gh 2.60+
