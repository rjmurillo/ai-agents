# AGENTS

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback `.serena/memories/<name>.md`|Post-compaction: re-run both

## Retrieval

|APIs: Context7, DeepWiki, WebSearch|Mem: `memory` skill
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`|ADRs: `.agents/architecture/README.md`->`ADR-*.md`
|Skills: `.claude/skills/{name}/SKILL.md`|Knowledge -> context. Actions -> skills.
|Rules: `.claude/rules/*.md` by `paths` first|Book depth: `software-engineering-library`|Generators: `.agents/governance/GENERATOR-FILES.md`

## Gates

**Start**:Init Serena|Latest issue handoff|Resume check|Search mem|Verify git
**Mid**: `git rev-list --count HEAD ^origin/main` notice 10; alert 15 (advisory, #5233)
**Pre-PR**: `uv run python scripts/validation/pre_pr.py`|No BLOCKING|Security scan|Style `.gemini/styleguide.md`
**End**:Issue handoff if open|Update Serena|Lint|Commit|Check

## Boundaries

**BLOCKING verify**: unrun gen'd artifact -> runtime test|security thread -> code fix or owner|skip validation -> `pre_pr.py`
**Always**: Python (ADR-042)|Verify branch|Check skills|Assign issues|PR template|Atomic commits <=5 files|Scoped lint|Pin Actions SHA|Run changed workflows pre-push|No manifest ver (ADR-092)
**Ask First**: Architecture|New ADRs|Breaking|Security
**Autonomy Guardrail**: Internal+reversible: act|External/irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|New bash|Logic in YAML (ADR-006)|Raw gh if skill exists|Force push|Skip hooks|Internal refs in src|Scratch in tree|Resolve security thread w/o fix|Ship unrun gen artifact|Report PR blocked/conflicted w/o fix
**Tokens**: rework bills edit+review+fix+re-review|Read `paths` rules + exact span BEFORE edit|Never cut gates/tests/evidence

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect|Lifecycle: /spec /plan /build /test /review /ship
|Merge blocked/conflicted: don't ask; github skill (why_pr_blocked+resolve) or merge-resolver; recheck
|CI-feedback sub-loop: cluster, ladder build->test->review->ship. `.agents/governance/CI-FEEDBACK-SUBLOOP.md`
|ADR-078: no skill -> autoplan; multi-step/cross-cutting -> orchestrator; no return loop
|New capability: buy-vs-build Quick BEFORE /spec+baseline; >13wk no baseline = prune. Skip: bug/doc/refactor/approved-cap-ext
|Harness: read agent-harness-reference; mutate via ai-agents-portability-campaign
|Any `ADR-*.md` edit fires adr-review

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `uv run pytest tests/ -x`|`uv run ruff check .`|skill tests in `tests/skills/<name>/`
Tests (BLOCKING): pos+neg+edge|branches|mock I/O|CLI exits. `.agents/governance/TESTING-RIGOR.md`

## Stack

Py 3.14 dev; floor: pyproject|UV|PS 7.5+|Node LTS|Pester 5.7+|pytest 8+|gh 2.60+
