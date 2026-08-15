---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5056-pr-autofix-round-cap.json
qaCommit: a62a2cbf6e275c328ec62d9697876c929838df04
---

# Issue #5056 Round-Cap Circuit Breaker QA Report

## Scope

Validates `check_pr_round_cap.py`, its wiring into `src/copilot-cli/skills/pr-autofix/SKILL.md`
Phase 2 Step 2.5, and its mirror at `src/copilot-cli/skills/github/scripts/pr/check_pr_round_cap.py`.

## Evidence

| Check | Result |
|---|---|
| `uv run pytest tests/skills/pr-autofix/test_check_pr_round_cap.py -q` | 26 passed |
| `uv run ruff check` on both script copies + test file | All checks passed |
| `check_skill_md_portability.py` (whole-corpus scan) | No drift; 242 grandfathered refs across 96 files (baseline 242) |
| `check_skill_md_exec_portability.py` (whole-corpus scan) | No drift; 675 grandfathered invocations across 153 files (baseline 699) |
| `check_plugin_frontmatter_self_containment.py` | No outward frontmatter references; 931 files scanned |
| `check_skill_contract_tests.py` | OK; 64 in-scope skills, 9 grandfathered |
| `npx markdownlint-cli2 src/copilot-cli/skills/pr-autofix/SKILL.md` | 0 issues |
| Byte-identical mirror check (`.claude/` vs `src/copilot-cli/` copy of `check_pr_round_cap.py`) | IDENTICAL |
| Manual smoke of `evaluate_round_cap` (round 1..5, wall-clock-only escalation) | Matches expected ACT/ESCALATE transitions |
| `uv run python scripts/validation/pre_pr.py` (full suite, background run) | Caught two real defects: 6 mypy `[type-arg]` errors and a taste-ratchet file-size REGRESSION (584 > baseline 583). Both fixed; see below |
| `uv run mypy .../check_pr_round_cap.py` after fix | 0 errors |
| `uv run python scripts/ci/taste_count_ratchet.py` after fix | OK, count == baseline 583 |
| `uv run python scripts/ci/merge_tree_ratchet_check.py` after merging `origin/main` | OK, merged tree passes all registered ratchets |

## Acceptance Criteria (task items 3 and 5)

| Criterion | Status |
|---|---|
| Cap not yet reached proceeds (ACT) | PASS: `test_round_below_cap_is_act` |
| Cap exactly reached escalates | PASS: `test_round_exactly_at_cap_escalates`, `test_cap_exactly_reached_escalates_and_exits_one` |
| Wall-clock budget exceeded independent of round count | PASS: `test_wall_clock_budget_exceeded_independent_of_round_count`, `test_wall_clock_exceeded_escalates_regardless_of_round_count` |
| Envelope JSON shape | PASS: `test_envelope_shape_has_all_documented_fields` |
| ESCALATE leaves a human-readable note, not a silent stop | PASS: `render_escalation_comment` posts a distinct visible PR comment; `test_escalation_note_not_duplicated_on_repeat_call` proves idempotency |
| Existing safety mechanisms (lease, live-state gate) unmodified | PASS: diff touches only new files plus an insertion in `SKILL.md`'s Phase 2 loop; no existing gate logic altered |

## Known limitations

- No end-to-end smoke against a live GitHub PR was run (would require a disposable PR
  and `gh` write access outside this task's scope); coverage is unit-level against the
  pure decision function (`evaluate_round_cap`) and `main()` with mocked comment I/O,
  matching how `check_pr_live_state.py` itself is tested (`tests/test_check_pr_live_state.py`).
- `check_skill_md_exec_portability.py`'s reported `[IMPROVED]` rows (`github-url-intercept`,
  `session-end`, `session-init`) are pre-existing changes on this worktree from other work,
  unrelated to this PR; not investigated further as out of scope.

## Refresh note (2026-08-15, landing coordinator)

Merged `origin/main` (merge commit `a62a2cbf6`) to pick up PR #5055's early lease check, PR #5088's staleness gate, and the CI-triage step, resolving two conflicts in `.claude/commands/pr-autofix.md`. The resolution also fixed a live defect in the branch: the round-cap gate read its tier from `check_pr_live_state.py` output, which carries no tier field, so `TIER` was always `UNKNOWN`, the T3/T4 gate never fired, and the auto-merge disarm gate would have treated every armed PR as non-T1. The tier now comes from `test_pr_merge_ready.py` (the authoritative source), computed once above the round-cap gate and reused by the disarm gate. The Copilot mirror was regenerated with `sync_plugin_lib.py` + `build_all.py`, not hand-edited, and `check_generated_staleness.py` reports rc=0. Re-verified on the merged tree: 56/56 pr-autofix tests (26 round-cap + 30 race-gate), taste (583), ruff (27), and type-ignore (44) ratchets unchanged.
