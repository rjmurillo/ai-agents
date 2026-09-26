---
type: task
id: TASK-050
title: Gate build validator edits on a provenance and authority record
status: implemented
priority: P1
related:
  - REQ-041
  - DESIGN-039
created: 2026-09-26
updated: 2026-09-26
author: plan
tags:
  - skills
  - build
  - routing
  - validation
---

# TASK-050: Gate build validator edits on a provenance and authority record

## Milestones

1. **Trigger tests.** Write `tests/skills/build/test_validation_trigger.py`
   first. It fails because the script does not exist.
2. **Trigger.** Write `.claude/skills/build/scripts/validation_trigger.py`
   until the tests pass.
3. **Record tests.** Write
   `tests/skills/validation-authority/test_validation_record.py` first.
4. **Record validator.** Write
   `.claude/skills/validation-authority/scripts/validation_record.py` until
   the tests pass.
5. **Compose.** Add Phase 2b to the `build` template. Add the record check
   to `test` Gate 4 and `review` Stage 1. Add the record contract to the
   `validation-authority` template. Change both routing blocks.
6. **Scenarios.** Add activation and skip scenarios to
   `tests/evals/skill-scenarios/build.json`.
7. **Render and prove.** Run `build_all.py`, the targeted tests, the
   routing-role gate, ruff, mypy, and `pre_pr.py`.

## Fixture table

| Case | Paths or effects | Expected |
|---|---|---|
| Local validator change | `scripts/validation/check_x.py`, LOCAL record | activate, record exit 0 |
| Local config fix | `.markdownlint-cli2.yaml`, `local-config-defect` | activate, record exit 0 |
| Vendored validator | `vendor/lint/rule.py` changed, VENDOR record | record exit 1 |
| Generated mirror | `src/claude/skills/x/scripts/check_x.py` changed alone | record exit 1 |
| Unjustified baseline refresh | `baseline-update` with no justification | record exit 1 |
| Unknown owner | category `UNKNOWN` | record exit 1 |
| Unrelated source change | `src/app/feature.py` | trigger skip |

## Risks

| Risk | Mitigation |
|---|---|
| The model skips the gate | Phase 2b is numbered, and the record check blocks |
| The trigger misses a new validator path | The effect cues cover semantics that paths miss |
| `build_all.py` moves | The trigger reports a null source instead of failing |
| Mirror drift | `build_all.py --check` |

## Done When

Every REQ-041 criterion maps to a passing test or a gate run.
