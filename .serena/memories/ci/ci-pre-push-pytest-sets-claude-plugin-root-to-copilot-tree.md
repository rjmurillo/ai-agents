# Pre-push pytest runs with CLAUDE_PLUGIN_ROOT=src/copilot-cli, so env-default tests diverge

## What happens

`run_pytest` in `scripts/validation/git_hook_policy.py` (line 7775) strips `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT`, and `COPILOT_PLUGIN_ROOT` from the child environment (lines 7777 to 7781). It then sets `CLAUDE_PLUGIN_ROOT` to `<repo>/src/copilot-cli` (line 7797).

## Effect on tests

A test that expands a skill command such as `${CLAUDE_PLUGIN_ROOT:-.claude}/skills/...` gets the default `.claude` in a plain local pytest run. Under the pre-push hook it gets `src/copilot-cli`. The test passes locally and fails at push (seen on PR #6303).

## Fix in the test

Clear `CLAUDE_PLUGIN_ROOT` and its sibling `COPILOT_PLUGIN_ROOT` (monkeypatch.delenv) before expanding, or set both explicitly to the tree under test. Agent prompts use the nested form `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}`, so the sibling matters too.

## Related

`ci/ci-local-push-and-test-environment-contracts` covers setting `CLAUDE_PLUGIN_ROOT=.claude` to reproduce CI locally.

## Sources

- `scripts/validation/git_hook_policy.py` lines 7775 to 7797.
- PR #6303, as relayed by the coordinator (not re-read).
