---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10006-fleet-pr-4651.json
qaCommit: 146d5aca1838673f5f4d37cb9ab9e8d924bd5e7b
---
# PR 4651 Fail Closed Agent Machinery QA Report

## Scope

PR 4651 changes hook enforcement, generated Copilot hook mirrors, build generation, `lefthook.yml`, the CLI exit contract baseline, token ratchet scripts, and validation tooling.

## Evidence

### Changed module tests

Command:

```bash
uv run --frozen pytest tests/build_scripts/test_build_all.py tests/build_scripts/test_generate_hooks.py tests/ci/test_cli_exit_contract_ratchet.py tests/ci/test_ruff_ratchet.py tests/hooks/test_markdownlint_guard.py tests/hooks/test_markdownlint_verifier_security.py tests/hooks/test_push_guard_base.py tests/test_lefthook_gate_config.py tests/test_update_memory_index_tokens.py tests/validation_pre_pr/test_markdown_checks.py -q
```

Real output:

```text
collected 486 items
485 passed, 1 skipped in 14.74s
```

### CLI exit contract baseline direction

Command:

```bash
printf '09b58c12b^ baseline: '; git show 09b58c12b^:scripts/ci/cli_exit_contract_baseline.txt
printf '09b58c12b baseline: '; git show 09b58c12b:scripts/ci/cli_exit_contract_baseline.txt
printf 'HEAD baseline: '; cat scripts/ci/cli_exit_contract_baseline.txt
```

Real output:

```text
09b58c12b^ baseline: 29
09b58c12b baseline: 28
HEAD baseline: 27
```

### Generated Copilot hook mirrors

Command:

```bash
uv run --frozen python build/scripts/build_all.py
git diff --exit-code -- src/copilot-cli/hooks .claude/hooks build/scripts/generate_hooks_events.py
```

Real output excerpt:

```text
=== Hooks -> Copilot ===
Found 2 Claude event(s) in .claude/hooks/hooks.json
Written: 2
```

`git diff --exit-code -- src/copilot-cli/hooks .claude/hooks build/scripts/generate_hooks_events.py` produced no output and exited 0.

### Ruff on changed Python files

Command:

```bash
uv run --frozen ruff check $(git diff --name-only origin/main...HEAD -- '*.py')
```

Real output:

```text
All checks passed!
```

### Fail closed behavior for unchecked agent machinery

Command:

```bash
uv run --frozen pytest tests/hooks/test_push_guard_base.py -q -k 'diff_failure_blocks or validator_exception_blocks or malformed_hook_input_blocks or empty_stdin_blocks or ambiguous_push_scope_blocks or shell_expansion_blocks or unsafe_bare_push_configuration_blocks or configured_explicit_push_target'
```

Real output:

```text
collected 80 items / 59 deselected / 21 selected
21 passed, 59 deselected in 0.17s
```

## Verdict

PASS. The CI failure was a missing `qaSessionLog` file. The report now points to a committed session log.
