# ADR-057 claims ledger, 2026-11-25

Claims in the 2026-11-25 amendment or edited sentences of ADR-057. The owner-statement row is `NOT RUN`: it names a source this ledger did not re-query, so the amendment attributes it to the owner and does not assert it as a measurement.

Commands ran in the working tree of branch `ci/delete-agent-env-jobs` at head `7cfb378901` with the ADR amendments uncommitted. The deletion commit is `3f145f26fd` on base `e74b842786`.

| Claim | Kind | Command | Result |
|---|---|---|---|
| slash-command-quality.yml no longer exists | absence | `test ! -e .github/workflows/slash-command-quality.yml && echo absent` | VERIFIED: absent |
| advisory_agent_workflows no longer lists slash-command-quality | absence | `grep -c 'slash-command-quality' src/claude/skills/pr-review/pr-review-config.yaml` | VERIFIED: 0 |
| No workflow invokes eval-prompt-change.py | absence | `grep -rln 'eval-prompt-change' .github \| wc -l` | VERIFIED: 0 |
| The acceptance gate returns FAIL on a regression when run | behavior | `uv run pytest tests/eval/test_eval_prompt_change.py -q -k test_regression_fails_gate` (asserts `gate["passed"] is False` at test line 1004) | VERIFIED: 1 passed, 149 deselected in 0.16s |
| tests/evals/spec-scenarios.json still exists (scenario set cited in the edited sentence) | path | `test -f tests/evals/spec-scenarios.json && echo present` | VERIFIED: present |
| Owner statement: latest 100 deployments of agent-claude and agent-copilot show none approved or run | quote | `echo 'owner statement in the task brief, 2026-11-25; not re-queried'` | NOT RUN: owner statement in the task brief, 2026-11-25; not re-queried |
