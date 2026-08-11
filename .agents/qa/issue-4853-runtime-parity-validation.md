---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-14653-bddf96dac-github-issue-4853-end-end.json
qaCommit: b7b74d561727e0b32aa5c8592ccb827e4adc9b94
---

# Issue 4853 Runtime Parity Validation

## Verdict

PASS for the implementation and deterministic controls. Issue completion stays
BLOCKED because Claude Code 2.1.179 has no active authentication on this
machine.

## Issue triage

- Validity: valid on refreshed `origin/main`.
- Priority: P1. Issues 4850 and 4851 depend on this measurement.
- Fix merit: yes. Existing evals measure prompt injection, not two real CLI
  loading paths.

## Deterministic evidence

- `uv run ruff check` on both modules and the test file: pass.
- `uv run pytest tests/eval/test_eval_runtime_parity.py -q`: 16 passed.
- Coverage: 89 percent across `_runtime_parity.py` and
  `eval_runtime_parity.py`.
- `eval_runtime_parity.py --dry-run`: four fixtures and both controls loaded.
- Taste lints: zero errors across three Python files.

## Real CLI evidence

Versions:

- Claude Code 2.1.179.
- GitHub Copilot CLI 1.0.79.

Copilot runtime probes used an isolated `COPILOT_HOME`, nested git repository,
disabled custom instructions, disabled built-in MCP servers, and restricted
tools.

- Resume fixture returned `CONTINUE_PHASE_3`.
- Tool fixture edited `parity-result.txt` to `parity-ok` and emitted one
  successful edit event.
- Sentinel instruction did not appear in either response.
- Both Copilot runs resolved `claude-opus-4.6` despite requesting
  `claude-opus-5`. The evaluator now fails closed when either resolved model
  differs from the requested model or its peer.

Claude reached the real binary and reported resolved model
`claude-opus-5`, then returned `Not logged in`. The evaluator wrote an error
report and exited 4, the repository authentication exit code.

## Remaining gate

Run the four-fixture live command after Claude authentication exists:

```text
uv run python scripts/eval/eval_runtime_parity.py
```

Do not label the issue complete until both CLIs execute every fixture with the
same resolved model.
