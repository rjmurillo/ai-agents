# AGENTS

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`|Post-compaction: re-run both

## Retrieval

|APIs: Context7, DeepWiki, WebSearch|Memory: `memory` skill
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`|ADRs: `.agents/architecture/ADR-*.md`
|Protocol: `.agents/SESSION-PROTOCOL.md`|Skills: `.claude/skills/{name}/SKILL.md`
|Rules: read `.claude/rules/*.md` by `applyTo` first|Book depth: `software-engineering-library`|Generators: `.agents/governance/GENERATOR-FILES.md`

## Gates

**Start**: Init Serena|Read HANDOFF+latest issue handoff|Resume check|Log|Search mem|Verify git
**Mid**: `git rev-list --count HEAD ^origin/main` block >20; notice 10; warn 15
**Pre-PR**: `python3 scripts/validation/pre_pr.py`|No BLOCKING|Security scan|Style `.gemini/styleguide.md`
**End**: Complete log|Keep HANDOFF|Issue handoff if open|Update Serena|Lint|Commit|Check

## Boundaries

**BLOCKING verify**: unrun gen'd artifact -> runtime test|security thread -> code fix or owner|skip validation -> `pre_pr.py`
**Always**: Python (ADR-042)|Verify branch|Check skills|Assign issues|PR template|Atomic commits <=5 files|Scoped lint|Pin Actions SHA|Run changed workflows pre-push|src/claude edit -> bump manifest (ADR-091)
**Ask First**: Architecture|New ADRs|Breaking|Security
**Autonomy Guardrail**: Internal+reversible: act|External/irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|Edit HANDOFF.md|New bash scripts|Logic in YAML (ADR-006)|Raw gh if skill exists|Force push|Skip hooks|Internal refs in src|Scratch in tree|Resolve security threads w/o fix|Ship unrun gen artifact

## Context

Knowledge -> context. Actions -> skills.

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver agent|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect|Lifecycle: /spec /plan /build /test /review /ship
|CI-feedback sub-loop: cluster, ladder build->test->review->ship. See `.agents/governance/CI-FEEDBACK-SUBLOOP.md`
|ADR-078: no skill -> autoplan; multi-step/cross-cutting -> orchestrator; no return loop
|New capability: buy-vs-build Quick BEFORE /spec+baseline; >13wk no baseline = prune. Skip: bug/doc/refactor/approved-cap-extension
|Harness work: read agent-harness-reference; mutate via ai-agents-portability-campaign

### ADR Review

Any `ADR-*.md` or `SESSION-PROTOCOL.md` edit fires adr-review.

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `uv run pytest tests/ -x`|`uv run ruff check .`|`tests/`|`.claude/skills/<name>/tests/`
Tests (BLOCKING): pos+neg+edge|branches|mock I/O|CLI exits. See `.agents/governance/TESTING-RIGOR.md`

## Stack

Py 3.14 dev; floor: pyproject|UV|PS 7.5+|Node LTS|Pester 5.7+|pytest 8+|gh 2.60+
