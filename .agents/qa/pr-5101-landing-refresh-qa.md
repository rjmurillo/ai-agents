---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-5101-landing-refresh.json
qaCommit: dc396bfc9dab0766342a0de4282ab802f3218dd9
---

# PR 5101 QA Report

## Verdict

PASS. The Claude-probe auth-skip behavior and the review renames are verified on commit `dc396bfc9`.

## Scope

- `tests/e2e/test_plugin_load_smoke.py`

## Evidence

- `uv run pytest tests/e2e/test_plugin_load_smoke.py -k "claude_probe or auth" -q`: 5 passed (three parametrized skip cases, the non-auth failure control, and the marker coverage)
- `uv run ruff check tests/e2e/test_plugin_load_smoke.py`: clean
- Review renames applied: the marker tuple is module-private (`_CLAUDE_AUTH_EXPIRED_MARKERS`) matching sibling constants, and the parametrized fixture is `auth_error_text` with a docstring covering the non-expiry auth-failure cases and stdout-or-stderr matching

## Not verified

- The live Copilot/Claude CLI probe path needs a hosted runner with a real CLI; the auth-skip logic is exercised through the mocked `_run_cli` boundary, the same seam the sibling probe tests use.
