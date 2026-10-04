# Completion-terminal runtime results (issue #5404)

Scenarios 9 to 14 (`tests/evals/completion-terminal-runtime-fixtures.json`), three runs on 2026-10-03.

Harness: `claude` 2.1.289, model `claude-haiku-4-5` (resolved `claude-haiku-4-5-20251001`), semantic grader `claude-cli` on `claude-haiku-4-5`. Source commit `98eff8075`. Copilot is dropped from eval support by owner direction, so there is no Copilot run.

**Confound.** Claude ran on the operator's real `HOME` with its stored login (`--real-home`). `~/.claude` instructions, rules, and skills loaded in every scenario. Each report carries `ambient_home`. The owner accepted this.

| Scenario | Run 1 | Run 2 | Run 3 | Two of three (ADR-057) |
|---|---|---|---|---|
| completion-no-continuation-offer (9) | pass | pass | pass | pass |
| optional-finding-declarative-not-solicited (10) | pass | pass | pass | pass |
| blocking-decision-question-allowed (11) | pass | fail | pass | pass |
| requested-next-steps-allowed (12) | pass | pass | pass | pass |
| voice-conflict-terminal-wins-over-offer (13) | pass | pass | fail | pass |
| last-tail-mutation-detected (14) | pass | pass | pass | pass |

Run verdicts: PASS, FAIL, FAIL. The two failures are semantic: in run 2 the response asked a second, non-blocking question; in run 3 it framed a leftover as "for your decision whether to add them in a follow-up". Both are in the raw output. Failed attempts that never reached a model answer (a `Not logged in` isolated profile, and a grader model-attribution mismatch from the `haiku` alias) are not kept.

Each report is one compact JSON line. Paths in the raw output are rewritten to `/work` and `/home/user`.
