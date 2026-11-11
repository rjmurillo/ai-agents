# Local test and push runs have five environment contracts

Five contracts that fail late or silently when missing. Sources: PR #6063
report, PR #6040, the D17 agent report, PR #6062, issues #7172 and #7173, and the
code cited below.

## CLAUDE_PLUGIN_ROOT points at `.claude`

Set `CLAUDE_PLUGIN_ROOT=.claude`, not the repository root. With the root, the
memory scripts fail at import. The skill command paths already fall back to
`.claude` (`${CLAUDE_PLUGIN_ROOT:-.claude}`), so an explicit value must match.

## Stray bytecode is not generated-file drift

The PR #6063 report blamed a leftover `__pycache__` under `.claude` or `src` for
a failed generated-staleness push gate. The code does not support that cause.
`_is_bytecode_artifact` in `build/scripts/build_all.py` excludes any path under
`__pycache__` and any `.pyc` or `.pyo` from the generator-write comparison, and
the `--check` path restores pre-existing caches. Treat a staleness failure as
real drift in a generator-owned file and read the reported paths. Setting
`PYTHONDONTWRITEBYTECODE=1` does not clear or prevent reading an existing cache.
See `decision-warm-pycache-before-push-never-purge.md` for the cache race that
does exist.

## The pre-push python-tests job runs only testmon-selected tests

By default pre-push runs `pytest --testmon` over the suite partitions
(`_testmon_commands` in `scripts/validation/git_hook_policy.py`), so only the
tests pytest-testmon selects run. Selection is best effort and misses code a test
reaches only through a subprocess. With no `.testmondata` the hook first fetches
main's CI seed (`scripts/validation/testmon_seed.py`) and otherwise runs
everything (575 s at 4 workers). Full execution without selection is opt-in
through `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY`, per ADR-104. To match CI locally:

```bash
CLAUDE_PLUGIN_ROOT=.claude GITHUB_EVENT_NAME=merge_group \
  uv run --frozen pytest
```

A green pre-push is not a green suite: CI runs everything.

## A merge of main can demand a D9 review marker

After merging main into a branch, the push carries main's new commits. If they
touched CRITICAL paths such as workflows, the `infrastructure-advisory` job in
`lefthook.yml` (issue #5636, D9) refuses the push unless HEAD is a `/review`
marker commit binding the security axis to its parent. The merge commit is not a
marker, so the push is refused although your own diff is clean. Run `/review`
on the merged head, then push.

## Local temp roots sit outside `$HOME`

Measured 2026-11-11 on a machine with `~/.claude/CLAUDE.md`, main at
`6283ad0ec`. A temp root under `$HOME` makes eval tests fail with a refusal that
reads like a regression. It is a guard doing its job.

```bash
# Fails: temp root under $HOME
PYTEST_NON_TMP_ROOT=$HOME/.cache/harness-check \
  uv run python scripts/ci/run_pytest_non_tmp.py tests/eval -q -n 8
# Passes: temp root outside $HOME (a scratch path under /tmp works)
PYTEST_NON_TMP_ROOT=/tmp/harness-check \
  uv run python scripts/ci/run_pytest_non_tmp.py tests/eval -q -n 8
```

- `scripts/ci/run_pytest_non_tmp.py` points pytest's temp roots and `TMPDIR` at
  `PYTEST_NON_TMP_ROOT`. CI uses `${{ runner.temp }}/ai-agents-pytest`
  (`.github/workflows/pytest.yml`), and its runner has no `~/.claude/CLAUDE.md`.
- `ambient_instruction_paths` in `scripts/eval/_claude_skill_harness.py` walks
  from `tempfile.gettempdir()` up through every ancestor. It looks for
  `CLAUDE.md`, `CLAUDE.local.md`, and a `.claude` entry. It skips `~/.claude`
  itself and still finds `~/.claude/CLAUDE.md`, because an ancestor's
  `.claude/CLAUDE.md` can load as project memory.
- `require_isolated_workspace_root` in `scripts/eval/_runtime_harness.py` is a
  second guard. It walks up from the workspace root, not the temp dir, and
  checks a wider list (`ANCESTOR_INSTRUCTION_FILES`, which adds `AGENTS.md`,
  `.claude/rules`, and the `.github` Copilot instruction files) with no
  `~/.claude` skip. Its message reads `inherits instruction files a CLI loads
  from ancestor directories`.
- Before PR #7260 (issue #7173), 14 tests in
  `tests/eval/test_claude_skill_harness.py` failed with `sits under instruction
  files`. They now stub the guard through the `claude_env` fixture and pass
  under either root. The guard itself still refuses a real run with a temp root
  under `$HOME`.
- After that fix, `tests/eval` with the root under `$HOME` still gave 1 failed,
  6420 passed, 7 skipped. The failure is
  `tests/eval/test_control_ablation_isolated_login.py::test_a_missing_login_is_not_needed_for_a_dry_run`,
  and the same file passes 10 of 10 with the root under `/tmp`. Issue #7289 tracks
  it. Only `tests/eval` was measured, so other trees are unmeasured.
- A temp root with an ancestor that holds `CLAUDE.md`, `CLAUDE.local.md`, or a
  `.claude` entry trips the harness guard, not only a root under `$HOME`. The
  workspace-root guard also refuses `AGENTS.md`, `.claude/rules`, and the
  `.github` Copilot instruction files in any ancestor.
- Issue #7172 records that PR #7092 called the original 14 failures a local
  runner artifact. With a root outside `$HOME`, all 32 tests in the file pass,
  so that diagnosis was wrong.
