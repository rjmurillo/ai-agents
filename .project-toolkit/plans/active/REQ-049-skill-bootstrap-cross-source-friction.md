# Execution Plan: skill-bootstrap cross-source friction sweep

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Review |
| **Created** | 2026-11-11 |
| **Owner** | orchestrator |
| **Complexity** | Medium |

## Objectives

- [x] T1 `bootstrap_sweep.py plan`: classify ToolInventory into source classes, read-only tools, excluded tools, seeds, judge digests (AC 1 to 4).
- [x] T2 `bootstrap_sweep.py index`: validate evidence manifest and files, coverage, sensitive patterns, deterministic batches (AC 4 to 8).
- [x] T3 `bootstrap_sweep.py import`: all-or-nothing judge rows per batch, atomic accepted file (AC 9).
- [x] T4 `bootstrap_sweep.py tally`: merge incidents, corroboration, ranking, gaps, incomplete pairs (AC 10 to 12).
- [x] T5 `bootstrap_mine.py candidates --sweep-json` via `bootstrap_friction.py` (AC 13).
- [x] T6 Judge rubrics under `judges/`: `friction.md`, `knowledge-gap.md`, `human-agent.md`, `agent-friction.md`, `change-review.md`.
- [x] T7 `references/friction-sources.md` rewritten around the script; `discovery.md`, `authoring-and-gates.md`, template edits; `institutional-knowledge` lens in forms script and tables (AC 14 to 16).
- [x] T8 Tests under `tests/skills/skill-bootstrap/`: positive, negative, edge per AC, exit-code contract.
- [x] T9 `build_all.py`, `build_all.py --check`, ruff, pytest for the skill, pre-PR gates that cover changed files.

## Sequencing

T1 to T4 and T8 for them go to one implementer (one file, shared helpers). T6 and T7 run in parallel with it (docs only, no shared file). T5 after T4 fixes the sweep schema. T9 last. Independent review (code-reviewer on scripts, critic on spec and docs) before ship.

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-11-11 | Sibling script copying skill-doctor batch pattern | Skill scripts do not import across skills; rows differ | Import `audit_batches.py`; extend hosted kinds |
| 2026-11-11 | Incident keys come from judges, not script similarity | No free-text similarity as a computed claim | Script clustering |
| 2026-11-11 | Seeds stay `candidate_unverified` | Imports never satisfy bootstrap gates by themselves | Promote corroborated incidents to verified |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-11-11 | Created plan from REQ-049 | orchestrator |
| 2026-11-11 | T1 to T9 landed in rjmurillo/ai-agents#7255; code and security review findings addressed in 156d3439d; dry run of `plan` over this session's MCP tool names added `retrieve` and `extract` read verbs in fb3273ee1; skill tests 1627 passed, 1 skipped at fb3273ee1 | orchestrator |

## Blockers

- None

## Related

- Spec: `.project-toolkit/specs/requirements/REQ-049-skill-bootstrap-cross-source-friction.md`
- Issue: #7155 (complementary)
- PR: rjmurillo/ai-agents#7255
