---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-10-session-14653-bddf96dac-github-issue-4853-end-end.json
qaCommit: 5f6872e64e42984a30696d53356c8ad66fd08284
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

- Scoped Ruff checks on the seven changed Python files: pass.
- `uv run pytest tests/eval/test_eval_runtime_parity.py tests/eval/test_eval_runtime_parity_review_fixes.py tests/eval/test_eval_runtime_parity_report_contract.py -q`: 48 passed.
- `uv run pytest tests/eval -q`: 1975 passed, 4 skipped.
- Pre-push Python tests passed after the latest base merge.
- Full-tree Ruff remains red on unrelated files under `.agents/analysis`.
  Scoped Ruff on every changed Python file passes.
- Malformed JSONL text and non-object JSON now exit 3 and record an external
  runtime failure.
- Claude receives only Anthropic credentials. Copilot receives only GitHub
  credentials.
- The consequential-choice fixture exposes `AskUserQuestion` to Claude and
  `ask_user` to Copilot. Copilot no longer receives `--no-ask-user` for that
  fixture, so the report can record either a structured event or the text
  fallback.
- Live CLI probe of the shipped `build_argv`: Copilot exits 0 in 10.8s and answers in prose with `--no-ask-user`, with the flag removed, and with `--available-tools=ask_user --allow-tool=ask_user`. No question tool call in any run. Claude reaches the auth check instead of failing agent resolution, which is the evidence the agent rename works.
- `uv run ruff check scripts/eval tests/eval`: All checks passed.
- Coverage: 89 percent across `_runtime_parity.py` and
  `eval_runtime_parity.py`.
- `eval_runtime_parity.py --dry-run`: four fixtures and both controls loaded.
- Runtime failures use one report shape. Agent digests use agent names, and
  agent installation preserves source line endings.
- Reports hash the transformed agent bytes loaded by each CLI.
- Runtime stderr is retained. Nonzero exits include the diagnostic in `error`.
- Structured question assertions score the tool payload without requiring
  fallback prose.
- Authored Python file-size errors were cleared by extracting output parsing
  and splitting report contract tests. Advisory warnings remain.

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
