---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14705.json
qaCommit: 7cabac1dca91690af708637ded7d9dc574a5e747
---

# Issue 4921 QA Report: codeql-scan wrapper delegates

**Verdict**: PASS
**Session**: 14705
**Branch**: fix/4921-codeql-skill-python-wrappers

## Reproduction, before and after

The command from the issue, run in a linked worktree:

| Command | Before | After |
|---------|--------|-------|
| `invoke_codeql_scan.py --operation validate` | exit 3, "Configuration script not found: .codeql/scripts/Test-CodeQLConfig.ps1" | exit 0, "Configuration is valid" |
| `invoke_codeql_scan_skill.py --operation validate` | exit 3, same message | exit 0 |
| `invoke_codeql_scan.py --operation full` | exit 3, install hint named `pwsh Install-CodeQL.ps1 -AddToPath` | exit 3, install hint names `install_codeql.py --add-to-path` |
| `step_verify_claude_skill()` | "[WARNING] Claude Code skill missing" while installed | "[PASS] Claude Code skill installed" |

Exit 3 for `--operation full` is correct: the CodeQL CLI is not installed in
this environment, which is the documented meaning of that code.

## Test evidence

| Command | Result |
|---------|--------|
| `uv run pytest tests/skills/ tests/test_install_codeql_integration.py .claude/skills/codeql-scan/tests/ -q` | 2363 passed |
| `uv run pytest tests/skills/codeql-scan/test_codeql_delegate_paths.py -q` | 29 passed |
| `uv run pytest tests/test_stdout_flush_before_spawn.py -q` | 30 passed |
| `uv run ruff check` (changed files) | All checks passed |
| `npx markdownlint-cli2` (changed markdown) | 0 issues |
| `uv run python scripts/validation/pre_pr.py` | RESULT: All validations passed |
| `uv run python build/scripts/build_all.py --check` | exit 0, no drift |

## Mutation testing of the new suite

A regression suite that cannot fail is not evidence. Each mutation reverted one
part of the fix and was then reverted:

| Mutation | Tests that failed |
|----------|-------------------|
| `CONFIG_SCRIPT_NAME` back to `Test-CodeQLConfig.ps1` | 10 |
| `--use-cache` misspelled `--useCache` | 3 |
| `cwd=repo_root` dropped from the delegate call | 2 |

## Coverage of the new tests

- Positive: delegate names resolve in the real repository; both wrappers agree;
  emitted flags parse under the delegate's own `build_parser()`; the wrapper
  runs green as a subprocess from the repo root and from a subdirectory.
- Negative: missing config delegate (3), missing scan delegate (3), outside a
  git repository (3), delegate exit 1 mapped to 2, delegate exit 2 mapped to 2,
  findings passed through as 1.
- Edge: empty `sys.executable` falls back to `python3`, `OSError` on launch
  returns 3, unexpected exit code 42 passes through, `cwd` anchoring asserted,
  consumer repo without `.codeql/` skips with 0.

## Security review

No CWE surface introduced. Delegate commands are built from `sys.executable`
plus a repo-root-anchored path plus argparse-constrained flags; `--languages`
is restricted to `python` and `actions` by `choices`. No `shell=True`, no
user-controlled path segments, no new network or filesystem writes. Semgrep ran
126 rules over the 10 changed files: 0 findings.

## Known limitations

Two pre-existing defects were found and deliberately left out of scope. Both are
recorded in the session log and the Serena memory:

1. `invoke_codeql_scan_skill.py` duplicates `invoke_codeql_scan.py` and is
   undocumented in SKILL.md.
2. `test_codeql_config.py` derives repo root as
   `Path(config_path).parent.parent`, yielding `.github` and emitting spurious
   "Path does not exist" warnings.

## Review comment fixes (daf3d09)

Docstring-only and metadata changes addressing 5 copilot-pull-request-reviewer
threads. No behavioral code changes:

1. Replaced cross-root `.claude/rules/canonical-source-mirror.md` references
   with tree-neutral wording in all 4 wrapper docstrings.
2. Replaced summarized `parser.add_argument(...)` with path+line-range
   references per canonical-source-mirror contract rules.
3. Added codeql memory entry to `.serena/memories/memory-index.md`.

All existing tests still pass (29/29 delegate path tests, build_all.py --check
reports no drift).
