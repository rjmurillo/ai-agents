# Execution Plan: Pilot skills compiled from mustache templates (issue #5706)

## Metadata

| Field | Value |
|-------|-------|
| **Status** | In Progress |
| **Created** | 2026-09-11 |
| **Owner** | claude (session 017M4qLAptnWDBp4aHuFUs6L) |
| **Complexity** | High |
| **Spec** | REQ-025, DESIGN-024, TASK-030 (A0), TASK-025 (A1), TASK-027 (A2), ADR-108 |

## Objectives

- [x] D1: owner chose the mustache-compile design with an ADR-107 amendment over the no-amendment excerpt design (2026-09-11).
- [ ] A0: ADR-108 reviewed through `adr-review`, ADR-107 cross-reference, REQ-003-010 amendment note, spec artifacts, regenerated ADR index; PR merged (TASK-030).
- [ ] A1: compile module, `generate_skills.py --validate`, `build_all.py` allowlist and check mode, `chevron` dev dependency, `Skill Template Drift` gate, tests, governance and rule lines; PR merged (TASK-025).
- [ ] A2: eight templates, six partials, rendered files, regenerated mirrors, contract tests, byte report; PR merged and issue #5706 closed (TASK-027).

## Milestones

### A0: the amendment before the mechanism

Exit criteria: `check_adr_lifecycle.py` passes; `adr-review` round recorded at `.agents/critique/ADR-108-debate-log.md` with every P0 and P1 resolved or deferred with an issue; `build_all.py --check` exits 0 after the ADR index regenerates; PR open with `Refs #5706`.

| Task | Size | Done when |
|------|------|-----------|
| A0-T1 ADR-108 | M | Record written; lifecycle gate passes; no dashes or banned words |
| A0-T2 cross-references | S | ADR-107 Related Decisions line; REQ-003-010 amendment note |
| A0-T3 spec artifacts | S | REQ-025, DESIGN-024, TASK-030 to 026, ontology, this plan; frontmatter validator passes |
| A0-T4 adr-review | L | Six-seat round run; findings folded; log committed |
| A0-T5 index and PR | S | README regenerated; PR opened; owner asked whether ADR-108 moves to `accepted` on merge |

### A1: the compile and its gates

Exit criteria: TASK-025 done definition; with no template on disk, `build_all.py --check` exits 0 and `pre_pr.py` reports no BLOCKING finding; positive, negative, and edge tests pass for the compile and for the guard allowlist.

| Task | Size | Done when |
|------|------|-----------|
| A1-T1 `skill_templates.py` | M | `discover`, `owned_targets`, `check_grammar`, `render`, `compile_all` per DESIGN-024 |
| A1-T2 `generate_skills.py` | S | Compile before copy; `--validate`; docstring cites ADR-108 |
| A1-T3 `build_all.py` | M | Allowlist argument; check mode runs validate; tests for allowlisted and non-allowlisted writes |
| A1-T4 dependency | S | `chevron==0.14.0` in both dev tables; `uv lock`; parity test passes; mypy override if needed |
| A1-T5 compile tests | M | Nine cases in DESIGN-024; subprocess exit codes 0, 1, 2 |
| A1-T6 pre_pr gate | S | Wrapper, `_Gate` row, facade re-export, `EXPECTED_ORDER` entry in the same commit |
| A1-T7 governance and rule lines | S | `GENERATOR-FILES.md` row and paragraph; `build/AGENTS.md` no-write line; `generated-artifacts.md` REQ-003-010 sentence; `templates.md` MUST 1; `templates/AGENTS.md`; rule mirrors regenerated |

### A2: the pilot

Exit criteria: REQ-025 acceptance criteria 1, 2, 3, 8, 9, 10, 12, 13 hold; `build_all.py --check` exits 0; `check_skill_md_portability.py` reports no new offender; PR body quotes the byte report and uses `Fixes #5706`.

| Task | Size | Done when |
|------|------|-----------|
| A2-T1 six partials | S | Each opens with a `rule-source` line; parity test passes with a negative control |
| A2-T2 eight templates | M | `@CLAUDE.md` deleted; `{{> slug}}` lines at the DESIGN-024 steps; grammar check passes |
| A2-T3 render and mirrors | S | `build_all.py` run; eight rendered files and eight mirrors committed; `git status` shows no unrelated drift |
| A2-T4 contract tests | S | Helper plus eight per-directory tests; crosslink test flipped |
| A2-T5 byte report | S | `wc -c` before and after quoted in the PR body |

## Dependency graph

```text
D1 (done) ──> A0 (T1 ──> T2, T3 ──> T4 ──> T5) ──> merge ──> A1 (T1 ──> T2 ──> T3; T4, T6, T7 parallel after T1; T5 after T3) ──> merge ──> A2 (T1, T2 ──> T3 ──> T4, T5) ──> merge
```

A1 code can be written in a worktree while A0 is in review, since it does not touch the ADR; it must not merge before A0. A2 needs A1 on the trunk because rendering needs the compile.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `adr-review` blocks ADR-108 on a factual citation | Medium | Medium (extra round) | Every `repo-observed` line was read on `cd0f9561d`; fold findings, do not argue |
| Owner keeps ADR-108 `proposed` and A1 is asked to wait for `accepted` | Medium | Medium (schedule) | Ask in the A0 PR body; A1 branch waits in a worktree |
| `tests/validation/test_pre_pr_sequence_registry.py` hardcodes gate order (`EXPECTED_ORDER`, line 52) | High | Medium (red A1 push) | Add the gate name in the same commit as the `_Gate` row |
| `tests/test_frontgate_crosslink_1927.py:163` asserts `@CLAUDE.md` is present in the plan source | High | Medium (red A2 push) | Flip the assertion in the same commit that lands the plan template |
| `build_all.py --check` writes a rendered file and the restore misses `.claude/` | Medium | High (dirty canonical tree in CI) | Check mode never writes; test asserts every `.claude/` file is unchanged after a drifted check |
| A partial span carries a repository path and trips the portability ratchet | Low | Medium | Spans chosen path-free; A2-T3 done-when includes the ratchet run |
| `chevron` renders a typo as empty text | High without the grammar check | High (silent content loss) | Grammar check and post-render `{{` scan, both tested |
| `tests/validation/test_always_on_corpus_claims.py` pins figures a skill change does not touch | Low | Low | Rule files untouched; run once to confirm |
| Bot reviewers file one thread per dash or banned word | Medium | Low | Dash guard and prose self-check before each push |
| Editing eight always-loaded skills changes behavior an eval pins | Low | Medium | Templates are the current text minus one line plus partials; run `test_spec_step0.py` and `test_generate_skills.py` |

## Decision Log

| Date | Decision | Rationale | Alternatives Considered |
|------|----------|-----------|------------------------|
| 2026-09-11 | D1: mustache compile into `.claude/skills/` with an ADR-107 and REQ-003-010 amendment (owner) | Owner wants templates as the canonical source, matching issue #5706 and the path to migrating all 111 skills | Excerpt blocks pinned by a validator, no amendment (recommended by the session, declined); hold |
| 2026-09-11 | Amend by a new record, ADR-108, rather than editing ADR-107 in place | Repository precedent: ADR-090 amends ADR-076, ADR-061 amends REQ-003-007; issue #5706 forbids a second ADR-107 and a silent rewrite | In-place edit of ADR-107 through `adr-review` |
| 2026-09-11 | Guard keeps running with a run-time allowlist, compile inside the guarded window | A compile bug writing elsewhere under `.claude/` is still caught; running before the baseline would hide it | Compile before the baseline snapshot (rejected as implementing around the guard) |
| 2026-09-11 | Restricted mustache grammar: partial and comment tags only | `chevron` renders unknown variables and missing partials as empty text silently (probed) | Full mustache grammar |
| 2026-09-11 | `chevron==0.14.0` as a dev dependency | Pure Python, MIT, no dependencies; issue #5706 names it | In-tree expander (about 40 lines); Jinja2 |
| 2026-09-11 | Three PRs: A0 amendment, A1 pipeline, A2 pilot | Each has its own reviewers and its own gate; A0 through `adr-review`, A1 through generator tests, A2 through the byte report | One PR; two PRs |

## Progress Log

| Date | Update | Agent |
|------|--------|-------|
| 2026-09-11 | Spec written for the no-amendment design; critic and analyst reviews folded | claude |
| 2026-09-11 | D1 asked; owner chose the amendment path | claude |
| 2026-09-11 | ADR-108 written; ADR-107 and REQ-003 cross-referenced; spec and tasks revised for A0/A1/A2 | claude |

## Blockers

- None. A0 proceeds to `adr-review`.

## Deferred items

- Migrating the other 103 skills to templates (owner's word after the pilot byte report).
- Cutting always-on rule text (issues #5400, #5492, #4871) once the pilot lands.
- Templates for `references/*.md`.
- Sub-section partials with an in-rule marker pair.
- Issue #5657 (`references/` translation, multi-line prompt bodies): untouched.
- Replacing `chevron` with an in-tree expander.

## Related

- Issue: #5706 (epic #5698)
- PR: (pending, A0)
- ADR: ADR-108 (amends ADR-107 property 1 and REQ-003-010)
