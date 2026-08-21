# QA Report: repo-wide ruff cleanup and zero-baseline guard

Session 99927. Branch `claude/ruff-linting-cleanup-hizsp7`. Starting commit `9e1ebd2`.

## Scope under test

Twelve Python files edited to clear 27 ruff violations, plus one baseline integer
lowered from 27 to 0. No behavior change was intended in any file; every edit is
a reflow, an import reorder, a dead-directive removal, an unused-loop-variable
rename, or a condition collapse.

## Evidence

### Lint

```text
$ uv run ruff check .
All checks passed!
```

Before: 27 errors across 10 files. The eight violations quoted in the request
were a subset; the repo-wide run found 19 more.

### Whole-tree ratchet

```text
$ uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py
ruff count ratchet: STALE BASELINE. baseline is 27 but the tree measures 0,
a gap of 27 above the permitted 6. Improvements went unrecorded; write 0 into
the baseline file.
```

The ratchet measured the tree at 0 and demanded the baseline be recorded, which
is the action taken. The ratchet scans git-tracked `*.py`, `*.pyi`, `*.ipynb`,
so its 0 and `ruff check .`'s 0 agree on the same corpus.

### Tests

```text
$ uv run pytest tests/test_req003_migration.py \
    tests/validation/test_validate_python_syntax.py \
    tests/validation/test_validate_skill_shells.py \
    tests/validation/test_validate_sync_registry.py -q
48 passed in 6.45s

$ uv run pytest tests/test_validate_pr_review_config.py -q
57 passed in 0.65s
```

105 tests, 0 failures.

### Behavior-preservation probes for the two sensitive files

`scripts/migrations/req003_inline_plugin_root_bootstrap.py` holds a compiled
regex and a generated-code template. Both were reflowed, so both were probed
directly rather than inferred from the test suite:

```text
regex identical: True
flags MULTILINE: True
emitted compiles: True
marker present: True
sys.exit(2) present: True
```

`regex identical` compares `OLD_PATTERN.pattern` against the pre-change pattern
string character for character. `emitted compiles` runs
`compile(NEW_TEMPLATE.format(exit_code=2), ...)`, confirming the `{{ }}` format
escapes survived the wrap and the emitted source is still valid Python at the
indentation the migration inserts it at. The emitted message text is unchanged:

```text
    print(
        f"Plugin lib directory not found: {_lib_dir} "
        f"(CLAUDE_PLUGIN_ROOT={_plugin_root!r})",
        file=sys.stderr,
    )
```

`.agents/security/benchmarks/vulnerable_samples/cwe22_path_traversal.py` is a
deliberately vulnerable detection benchmark, so its answer key must not move.
Both reflowed lines sit inside the SAFE helpers, `test_safe_file_path`'s
containment `return` and `export_data_secure`'s `ValueError`, not inside any
function marked VULNERABLE. The `I001` fix in that file and in
`cwe77_command_injection.py` removed one blank line after the import block and
reordered nothing that a scanner reads. No new attack surface is introduced, so
`.claude/rules/security.md` MUST-5 requires no benchmark update.

### Syntax

All eight non-test edited files parse under `ast.parse`.

## Gaps

`packages/semantic-hooks/src/semantic_hooks/recorder.py` and
`packages/semantic-hooks/hooks/pre_compact.py` have no direct test module; that
package ships `test_core.py`, `test_embedder.py`, and `test_stuck_detection.py`
only. The `recorder.py` change collapses

```python
if cond:
    return True
return False
```

into `return bool(cond)`, which is equivalent including for a falsy-but-not-False
`tool_name`, where `bool()` normalizes `""` to `False` as the original `return
False` branch did. The `pre_compact.py` change wraps two call arguments. Both
files parse and neither changes a call signature.

Serena MCP is unavailable in this session, so no memory search was run to check
for prior art beyond what the repository files record.

## Verdict

PASS. Lint clean at 0, the ratchet agrees at 0, 105 tests green, and both
sensitive files carry direct behavior-preservation evidence rather than an
inference from coverage.
