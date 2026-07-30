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
**Mid**: `git rev-list --count HEAD ^origin/main` <=20, warn >15 (ADR-008)
**Pre-PR**: `python3 scripts/validation/pre_pr.py`|No BLOCKING|Security scan|Style `.gemini/styleguide.md`
**End**: Complete log|Keep HANDOFF|Issue handoff if open|Update Serena|Lint|Commit|Check

## Boundaries

**BLOCKING verify**: unrun gen'd artifact -> runtime test|security thread -> code fix or owner|skip validation -> `pre_pr.py`
**Always**: Python (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|PR template|Atomic commits <=5 files|Scoped lint|Pin Actions SHA|Run changed workflows pre-push|Bump plugin manifest
**Ask First**: Architecture|New ADRs|Breaking|Security
**Autonomy Guardrail**: Internal+reversible: act|External/irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|Edit HANDOFF.md|Use bash|Logic in YAML (ADR-006)|Raw gh if skill exists|Force push|Skip hooks|Internal refs in src|Scratch in tree|Resolve security threads w/o fix|Ship unrun gen artifact

## Context

Always-on context is for what the model can't know: repo gotchas, local conventions, non-obvious tool behavior. Pre-trained engineering knowledge doesn't earn a slot; restating it bills every edit forever. Depth -> progressive disclosure. Actions -> skills.
Budget is measured, not asserted: `python3 scripts/validation/instruction_budget.py`. This line used to claim <8KB, which was Vercel's compressed-context figure adopted in #1022; the always-on corpus is now ~95KB on a `.py` edit, roughly 12x that. Ceilings ratchet to measured size, so a passing gate is not evidence the corpus is small.

## Gotchas

Non-obvious, cost real time to learn, cannot be inferred from the code.

|Session log: create it untracked in the worktree BEFORE the first commit. `branch-context-policy` reads the worktree; `session-policy` rejects a staged log with incomplete `sessionEnd`. Stage it only at session end. Following the protocol literally (create + stage at start) cannot pass both.
|Copilot CLI token counts are non-monotonic (109k reported from `/tmp` vs 96k in-repo for the same trivial prompt). Not a measurement. Use `instruction_budget.py`.
|Evals without an API key: `EVAL_PROVIDER=copilot-cli`. The provider must run in an empty cwd, because the CLI loads `AGENTS.md`, `CLAUDE.md`, and `.github/instructions/**` from its working directory and would contaminate the control cell.
|Instruction-budget ceilings ratchet to measured size, so a passing gate is not evidence the corpus is small. Compare against the goal, not the ceiling.

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver agent|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect|Lifecycle: /spec /plan /build /test /review /ship
|CI-feedback sub-loop: cluster, ladder build->test->review->ship. See `.agents/governance/CI-FEEDBACK-SUBLOOP.md`
|ADR-078: no skill -> autoplan; multi-step/cross-cutting -> orchestrator; no return loop
|New capability: buy-vs-build Quick BEFORE /spec+baseline; >13wk no baseline = prune. Skip: bug/doc/refactor/approved-capability-extension
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
