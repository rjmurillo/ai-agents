# Phase 3 Prompt Discipline Audit Status

## Status: ACTIVE (2026-05-26)

Phase 2 audit shipped as PR #2076 (merged 2026-05-25). 73 files audited; zero A-tier.
Phase 3 is the rewrite cycle. Each improvement ships as its own PR off main.

## Phase 3 Decisions (answered 2026-05-26)

1. **Scope**: Top-10 priority list (D/F files + top-3 leverage templates). B-to-A pass on all 73 deferred to Phase 4.
2. **Sequencing**: Template-first (cascades via `python3 build/generate_agents.py`). Quick wins (pr-quality clones, default-ai-review) in same pass.
3. **Verification per PR**: rubric rescore (target 32+/35) + `python3 scripts/validation/pre_pr.py` + `python3 build/generate_agents.py` round-trip.
4. **Owner**: Autonomous subagent, one PR per target, human review via GitHub PR.

## PR Progress

| PR | Target | Score Before | Score After | GitHub PR | Status |
|----|--------|-------------|-------------|-----------|--------|
| PR 0 | Audit doc Phase 3 decisions + stale cmd fix | docs | docs | #2082 | open |
| PR 1 | orchestrator.shared.md | 27/35 B | 33/35 A | #2083 | open |
| PR 2 | implementer.shared.md | 27/35 B | 32/35 A | #2084 | open |
| PR 3 | critic.shared.md | 26/35 B | 33/35 A | #2085 | open |
| PR 4 | security.shared.md | 26/35 B | 33/35 A | #2086 | open |
| PR 5 | qa.shared.md | 25/35 C | 32/35 A | #2087 | open |
| PR 6 | analyst.shared.md | 25/35 C | 31-32/35 A | #2088 | open |
| PR 7 | architect.shared.md | 25/35 C | 32/35 A | #2089 | open |
| PR 8 | pr-quality.*.prompt.md (7 clones) | 21/30 C | 27-29/30 A | #2090 | open |
| PR 9 | default-ai-review.md (F-tier) | 11/30 F | 28-30/30 A | #2091 | open |
| PR 10 | D-tier freestanding agents (code-simplifier, comment-analyzer, pr-test-analyzer) | 15-18/35 D | 32-34/35 A | TBD | implementing |

## Key Facts

- Generator: `python3 build/generate_agents.py` (NOT pwsh; ADR-042 migrated)
- Each template fix cascades to `src/vs-code-agents/` + `src/copilot-cli/` (2x generated)
- Rubric source: `~/Documents/Mobile/wiki/concepts/Prompting/Claude 4.7 Prompting Model.md`
- Audit doc: `.agents/analysis/2003-claude-47-prompt-discipline-audit.md`
- Pre-existing pre_pr.py failures: merge-resolver agent drift (20.9%) + lint on non-.agents/ files
- Session logs: sessions 1837-1847 cover PR 0-10 work
- `.github/agents/*.agent.md` is NOT a generator target; freestanding files edited directly
- Phase 3 cycle complete after PRs 8-10 merge; Phase 4 (B-to-A on ~50 files) deferred

## Phase 3 Close-Out (when all 10 PRs land)

- Run rubric rescore script across the 73 audited files to confirm tier shifts.
- Update `.agents/analysis/2003-claude-47-prompt-discipline-audit.md` with the after-scores.
- Open Phase 4 issue for the B-to-A long-tail.
- Write Phase 3 retrospective covering: pacing, completion-gate friction on commit messages, lint-config gap on agent files, validator strictness on session logs.
