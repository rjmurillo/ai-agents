# AGENTS

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|If either call fails, halt and report; memory files are retrieval aids, not initialization substitutes.|Post-compaction: re-run both

## Retrieval

|APIs: Context7, DeepWiki, WebSearch|Memory: `memory` skill
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`|ADRs: `.agents/architecture/ADR-*.md`
|Protocol: `.agents/SESSION-PROTOCOL.md`|Skills: `.claude/skills/{name}/SKILL.md`
|Gotchas: `.agents/governance/GOTCHAS.md`|Issue handoffs: `.agents/sessions/handoffs/`
|Rule scopes: Claude honors `paths`; legacy `applyTo`/`alwaysApply` sources load unconditionally|Copilot mirrors: `applyTo`
|Book depth: `software-engineering-library`|Generators: `.agents/governance/GENERATOR-FILES.md`

## Gates

**Start**:

1. Init Serena. If BLOCKING, halt and report.
2. Read HANDOFF. Read the latest issue handoff when one exists; first-time work
   with no issue handoff is not blocking.
3. Run the resume check. If it fails, halt and report.
4. Create or update the session log. If it fails, halt and report.
5. Search memory. If the required memory source is unavailable, halt and report.
6. Verify git state. If the branch or worktree is invalid, halt and report.

**Mid**:

1. Run `git rev-list --count HEAD ^origin/main`. Block above 20, notice at 10, and warn at 15.
2. If the count exceeds 20, halt and report before continuing.

**Pre-PR**:

1. Run `uv run python scripts/validation/pre_pr.py`. If it fails, halt and report.
2. Resolve every BLOCKING result. If any remain, halt and report.
3. Run the security scan. If it fails, halt and report.
4. Run the style check from `.gemini/styleguide.md`. If it fails, halt and report.

**End**:

1. Complete the session log. If it fails, halt and report.
2. Keep HANDOFF unchanged. If circumstances require a HANDOFF update, halt, report the required change to the user, and await explicit user approval before proceeding.
3. Create an issue handoff when an issue remains open. If creation fails, halt and report.
4. Update Serena. If it fails, halt and report.
5. Run lint. If it fails, halt and report.
6. Commit. If hooks or policy checks fail, halt and report. If the commit fails for any other reason (e.g. nothing staged, detached HEAD, merge conflict), halt and report the specific git error before proceeding.
7. Check the final state. If it differs from the intended change, halt and report.

## Boundaries

**BLOCKING verify**: unrun gen'd artifact -> runtime test|security threat -> code fix or owner|skip validation -> `pre_pr.py`
**Always**: Python (ADR-042)|Verify branch|Check skills|Assign issues|PR template|Each commit MUST touch <=5 hand-authored files. Hook-generated companions listed by policy do not count. Exceeding this limit is BLOCKING.|Scoped lint|Pin Actions SHA|Run changed workflows pre-push|No manifest version (ADR-092)
**Ask First**: Architecture|New ADRs|Breaking|Security

## Autonomy Guardrail

**Autonomy Guardrail**:

1. Check Ask First triggers. If any apply, confirm before acting.
2. If none apply: internal+reversible -> act; external/irreversible -> confirm; ambiguous -> act minimal, flag rest.

**Never**: Commit secrets|Edit HANDOFF.md|New bash scripts|Logic in YAML (ADR-006)|Raw gh if skill exists|Force push|Skip hooks|Internal refs in src|Scratch in tree|Resolve security threats w/o fix|Ship unrun gen artifact

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
Tests: `uv run pytest tests/ -x`|`uv run ruff check .`|new skill tests in `tests/skills/<name>/`
Tests (BLOCKING): pos+neg+edge|branches|mock I/O|CLI exits. See `.agents/governance/TESTING-RIGOR.md`

## Stack

Py 3.14 dev; floor: pyproject|UV|PS 7.5+|Node LTS|Pester 5.7+|pytest 8+|gh 2.60+
