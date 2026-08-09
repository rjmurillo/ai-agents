---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-06-session-10003-record-strict-policy-intentional-merge.json
qaCommit: 4f3474ef7760106c7ed56e3c7aeb62f5d9201f0f
---

# Session 10003 strict policy merge QA

## Scope

Validated the session 10003 documentation, memory, and generated instruction
updates after merging current `origin/main`.

## Evidence

- `uv run --frozen python scripts/validation/memory_index.py --path .serena/memories --ci --orphan-policy ratchet` exited 0.
- `uv run --frozen python scripts/ci/memory_index_count_ratchet.py --base-ref origin/main` exited 0.
- `uv run --frozen python scripts/ci/memory_index_token_ratchet.py` exited 0.
- `uv run --frozen python scripts/validation/instruction_budget.py --ci --format table` reported PASS for `.py` at 98,914 bytes against the 99,000 byte ceiling.
- `uv run --frozen pytest tests/validation/test_instruction_budget.py::test_real_repo_python_baseline_is_under_ceiling_and_nonzero tests/validation/test_always_on_corpus_claims.py tests/validation/test_audit_procedure_claims.py -q` reported 58 passed.
- `uv run --frozen python build/scripts/build_all.py` regenerated the instruction mirrors.
- `python3 -c "import re; t=re.findall(r'\]\(([^)]+\.md)\)', open('.serena/memories/memory-index.md').read()); print(len(t), len(set(t)))"` reported `154 154`.

## Result

PASS. The memory index is unique, generated mirrors are current, and the Python
instruction budget is under the ratchet ceiling.
