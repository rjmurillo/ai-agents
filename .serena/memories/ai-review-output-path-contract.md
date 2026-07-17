# AI Review Output Path Contract

The infrastructure gate owns the AI review verdict file path.

- Resolution order is `AI_REVIEW_OUTPUT_FILE`, `RUNNER_TEMP`, then `tempfile.gettempdir()`.
- The gate publishes `output_file` and `skip` on every run.
- On context infrastructure failure, the gate publishes
  `infrastructure_failure=true` and `retry_count=0`.
- `.github/actions/ai-review/action.yml` passes `output_file` to the invoke and
  parse steps. Never restore a literal `/tmp/ai-review-output.txt` path.
- `tests/test_check_ai_review_infra_gate.py` verifies Python and Bash use the
  same physical file.
- `.github/workflows/pytest.yml` runs the contract on Linux and Windows. Its
  path filter includes action-only changes so the test cannot be skipped.

Evidence:

- PR #3103 and issue #2967.
- `scripts/ci/check_ai_review_infra_gate.py`.
- `.github/actions/ai-review/action.yml`.
- `tests/test_check_ai_review_infra_gate.py`.
- `.github/workflows/pytest.yml`.
