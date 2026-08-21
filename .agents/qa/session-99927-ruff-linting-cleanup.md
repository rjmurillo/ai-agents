---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99927-ruff-linting-cleanup.json
qaCommit: 8e88e13ba66770cf0a05f317c88226960723f424
---

# QA Report: repo-wide ruff cleanup and zero-baseline guard

Session 99927. Branch `claude/ruff-linting-cleanup-hizsp7`. Starting commit `9e1ebd2`.

## Scope under test

Eleven Python files edited to clear 27 ruff violations, plus two config changes:
`scripts/ci/ruff_count_baseline.txt` lowered from 27 to 0, and one
`per-file-ignores` entry widened for the security benchmark corpus. No behavior
change was intended in any file; every edit is a reflow, an import reorder, a
dead-directive removal, an unused-loop-variable rename, a condition collapse, or
a type annotation.

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
is the action taken. Both commands reported 0 in this run, but that is not a
general guarantee: `ruff_count_ratchet.py`'s own docstring documents that its
scope is git-tracked files only, while a bare `ruff check .` also walks
untracked scratch, nested worktrees, and vendored caches, which the docstring
notes inflated a local run to 767 against a real tracked count of 361
elsewhere. The two counts agreeing here reflects a clean working tree, not
identical corpora by design.

### The guard is enforcement, not documentation

After lowering the baseline to 0, the gate was proved by injecting a violation
rather than by inspection:

```text
$ printf '# %s\n' "$(python3 -c "print('x'*120)")" >> scripts/validate_pr_review_config.py
$ uv run ruff check scripts/validate_pr_review_config.py --output-format=concise
scripts/validate_pr_review_config.py:418:101: E501 Line too long (122 > 100)

$ uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py
ruff count ratchet: REGRESSION. 1 violations > baseline 0 (+1). New ruff
violations cannot merge; fix them or, if they are unavoidable, coordinate a
baseline change (issue #2993).
RATCHET_EXIT=1

$ git checkout -- scripts/validate_pr_review_config.py
$ uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py
ruff count ratchet: OK (count == baseline 0).
RATCHET_EXIT=0
```

The control run after restoring the file is what makes the exit 1 attributable
to the injected line rather than to anything else in the tree.

The first attempt at this probe was non-discriminating and is recorded because
it is the trap worth naming: the violation was injected into
`docs/eval/scripts/analyze.py`, and `pyproject.toml` waives E501 for
`docs/eval/scripts/**/*.py`, so ruff emitted nothing and the ratchet reported OK
with the line present. A probe whose target rule is waived on the target path
measures nothing while looking exactly like a passing probe
(`.claude/rules/testing.md` SHOULD-17). Choose an injection site where the rule
is actually enabled.

### Tests

```text
$ uv run pytest tests/test_req003_migration.py \
    tests/validation/test_validate_python_syntax.py \
    tests/validation/test_validate_skill_shells.py \
    tests/validation/test_validate_sync_registry.py -q
48 passed in 6.45s

$ uv run pytest tests/test_validate_pr_review_config.py -q
57 passed in 0.65s

$ uv run pytest <the four files above> tests/test_validate_pr_review_config.py \
    tests/ci/test_validate_vendor_provenance.py -q
155 passed in 11.19s
```

155 tests, 0 failures. Re-run after merging origin/main, which is the commit the qaCommit above names.

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

The security benchmark corpus is not edited at all. The branch initially
reformatted `cwe22_path_traversal.py` and `cwe77_command_injection.py`, and the
pre-push `security-scan` job then blocked on three CWE-78 `shell=True` findings
in the latter. That job feeds changed files to semgrep, so touching the file at
all put its intentional payloads in scope. Those payloads are the benchmark's
reason to exist.

Both files were reverted to their `origin/main` content, and the existing
`per-file-ignores` entry for `.agents/security/benchmarks/**/*.py`, which
already waived `RUF100` with an answer-key rationale, was widened to `I001` and
`E501`. Verified: `git diff --name-only origin/main...HEAD` lists neither file,
so the corpus is byte-identical to main and `.claude/rules/security.md` MUST-5
needs no benchmark update.

This is the one place the zero count rests on a waiver rather than a code fix,
and it covers three files in a corpus that is graded by external scanners rather
than executed as product code. Every other violation was fixed in the source.

### Syntax

All non-test edited files parse under `ast.parse`. `mypy` reports Success on the
changed set, and the changed-line mypy ratchet gate returns True.

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

PASS. Lint clean at 0, the ratchet agrees at 0, 155 tests green, and both
sensitive files carry direct behavior-preservation evidence rather than an
inference from coverage.
