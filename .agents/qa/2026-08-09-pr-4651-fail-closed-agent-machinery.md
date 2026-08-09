---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-08-session-10006-fleet-pr-4651.json
qaCommit: a331de32787d194abf0c4edc9e79103c22366e53
---

# QA Report: PR 4651 Fail Closed Agent Machinery

## Verdict

PASS. I ran the verification on commit `a331de32787d194abf0c4edc9e79103c22366e53` after merging `origin/main` into `fix/adversarial-review-agent-machinery` in worktree `../ai-agents-qa-4651`.

## Scope

PR 4651 changes hook enforcement, generated Copilot hook mirrors, build generation, `lefthook.yml`, the CLI exit contract baseline, token ratchet scripts, and validation tooling.

## Evidence

### 1. Changed module tests

Command:

```bash
uv run --frozen pytest tests/build_scripts/test_build_all.py tests/build_scripts/test_generate_hooks.py tests/ci/test_cli_exit_contract_ratchet.py tests/ci/test_ruff_ratchet.py tests/hooks/test_markdownlint_guard.py tests/hooks/test_markdownlint_verifier_security.py tests/hooks/test_push_guard_base.py tests/test_lefthook_gate_config.py tests/test_update_memory_index_tokens.py tests/validation_pre_pr/test_markdown_checks.py -q
```

Real output:

```text
collected 490 items

======================= 489 passed, 1 skipped in 14.77s =======================
```

### 2. CLI exit contract baseline direction

Command:

```bash
printf '09b58c12b^ baseline: '; git show 09b58c12b^:scripts/ci/cli_exit_contract_baseline.txt && printf '09b58c12b baseline: '; git show 09b58c12b:scripts/ci/cli_exit_contract_baseline.txt && printf 'HEAD baseline: '; cat scripts/ci/cli_exit_contract_baseline.txt
```

Real output:

```text
09b58c12b^ baseline: 29
09b58c12b baseline: 28
HEAD baseline: 27
```

Result: tightening direction. The PR commit `09b58c12b` reduced the baseline from 29 to 28. The current QA commit tightens it again to 27 after pre-push measured the tracked count at 27.

### 3. Generated Copilot hook mirrors

Command:

```bash
uv run --frozen python build/scripts/build_all.py && git diff --exit-code -- src/copilot-cli/hooks .claude/hooks build/scripts/generate_hooks_events.py
```

Real output excerpt:

```text
=== Hooks -> Copilot ===
Config: /home/richard/src/GitHub/rjmurillo/ai-agents-qa-4651/templates/platforms/copilot-cli.yaml
Repo root: /home/richard/src/GitHub/rjmurillo/ai-agents-qa-4651
Mode: Generate

Found 2 Claude event(s) in /home/richard/src/GitHub/rjmurillo/ai-agents-qa-4651/.claude/hooks/hooks.json

=== Summary ===
Duration: 0.01s
Written: 2
```

`git diff --exit-code -- src/copilot-cli/hooks .claude/hooks build/scripts/generate_hooks_events.py` produced no output and exited 0. The committed mirrors match generator output.

### 4. Ruff on changed Python files

Command:

```bash
uv run --frozen ruff check $(git diff --name-only origin/main...HEAD -- '*.py')
```

Real output:

```text
All checks passed!
```

### 5. Fail closed behavior for unchecked agent machinery

Command:

```bash
uv run --frozen pytest tests/hooks/test_push_guard_base.py -q -k 'diff_failure_blocks or validator_exception_blocks or malformed_hook_input_blocks or empty_stdin_blocks or ambiguous_push_scope_blocks or shell_expansion_blocks or unsafe_bare_push_configuration_blocks'
```

Real output:

```text
collected 78 items / 60 deselected / 18 selected

tests/hooks/test_push_guard_base.py ..................                   [100%]

====================== 18 passed, 60 deselected in 0.19s ======================
```

Named coverage: `test_diff_failure_blocks`, `test_validator_exception_blocks`, `test_malformed_hook_input_blocks`, `test_empty_stdin_blocks`, `test_ambiguous_push_scope_blocks`, `test_shell_expansion_blocks_before_subprocess`, and `test_unsafe_bare_push_configuration_blocks_before_diff` prove the guard blocks on unchecked or unsafe push machinery paths.

## Uncompleted verifications

None. All five requested checks completed and passed.
