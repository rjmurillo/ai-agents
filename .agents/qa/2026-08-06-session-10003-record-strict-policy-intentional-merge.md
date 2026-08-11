---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-06-session-10003-record-strict-policy-intentional-merge.json
qaCommit: 7f79b060ca7342f68dbd1cb65b15f840b7777463
---

# Session 10003 strict policy merge QA

## Scope

Validated the session 10003 CI repair for instruction-budget claims, memory,
and generated instruction mirrors.

## Evidence

- `uv run --frozen python scripts/validation/memory_index.py --path .serena/memories --ci --orphan-policy ratchet` exited 0.
- `uv run --frozen python scripts/ci/memory_index_count_ratchet.py --base-ref 650344b6a7bfbac38d145836322835f6a61dbc6c` exited 0.
- `uv run --frozen python scripts/ci/memory_index_token_ratchet.py` exited 0 with plugin roots bound to this worktree.
- `uv run --frozen python scripts/validation/instruction_budget.py --ci --format table` reported PASS for `.py` at 98,999 bytes against the 99,000 byte ceiling.
- `uv run python scripts/ci/ruff_count_ratchet.py --base-ref origin/main` reported the measured count equals baseline 27.
- `uv run pytest tests/validation/test_instruction_budget.py tests/validation/test_always_on_corpus_claims.py tests/validation/test_instruction_ceiling_ratchet.py -q` reported 140 passed.
- `uv run python build/scripts/build_all.py --platform copilot-cli --check` exited 0.

## Result

PASS. Memory ratchets pass, generated mirrors are current, corpus claims match
their measured trees, and the Python instruction budget is under its ceiling.
