---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5056-pr-autofix-round-cap.json
qaCommit: 4e21dd9b568aa17edc008f5a00945e1554cc25e0
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
