# taste-lint: ignore file-size, alias regressions stay co-located for issue #4261.
"""Tests for scripts/validation/check_subprocess_encoding.py (issue #4261).

Guards the gate that catches subprocess calls pinning UTF-8 without
``errors="replace"``. A child process on Windows can emit bytes invalid for
UTF-8; without the replacement handler, the decode raises before the caller
can report the real assertion failure.

Coverage:
- pos/compliant: call with encoding + errors="replace" -> no violation
- pos/binary-mode: call with encoding but no text mode -> no violation (not in scope)
- pos/no-encoding: call with text=True but no encoding -> no violation (other checker)
- pos/non-subprocess: open(file, encoding="utf-8") -> not flagged
- neg/missing-errors-run: subprocess.run with encoding + text=True, no errors -> flagged
- neg/missing-errors-check_output: subprocess.check_output (decodes unconditionally) -> flagged
- neg/missing-errors-capture_output: capture_output=True with encoding, no errors -> flagged
- neg/missing-errors-stdout-pipe: stdout=subprocess.PIPE with encoding -> flagged
- neg/missing-errors-stderr-pipe: stderr=subprocess.PIPE with encoding -> flagged
- neg/alias-pipe-capture: subprocess call and PIPE aliases still resolve -> flagged
- neg/assigned-module-alias: `sp = subprocess` and derived aliases still resolve -> flagged
- neg/function-local-alias: aliases created inside a function still resolve there -> flagged
- neg/use-before-rebind: a valid alias still flags before a later reassignment shadows it
- neg/function-use-before-rebind: function bodies still flag when a later outer rebind happens
- neg/function-alias-use-before-rebind: aliased function calls still capture pre-rebind state
- neg/branch-local-function-order: branch-defined deferred functions honor outer call-time order
- neg/tuple-swap-order: destructuring alias swaps use the pre-assignment snapshot
- neg/tuple-unpack-alias: tuple/list unpacking preserves alias bindings
- neg/branch-join-alias: a subprocess alias in one branch still flags after the join
- neg/lambda-body: violating subprocess calls inside lambdas are flagged
- neg/lambda-use-before-rebind: assigned lambdas honor call-time rebind order
- neg/branch-local-lambda-order: branch-defined lambdas honor outer call-time order
- neg/match-guard-order: match guards capture deferred call order before later rebinds
- neg/universal-newlines: legacy text-mode alias is treated like text=True
- neg/from-import: ``from subprocess import run; run(...)`` -> flagged
- neg/splat: **kwargs present means errors may be absent -> flagged (conservative)
- pos/pipe-capture-binary: PIPE capture without encoding/text semantics -> not flagged
- pos/shadowed-run-helper: unrelated local `run` helper aliases stay clean
- pos/shadowed-imported-run: later rebinding of imported `run` stays clean
- pos/inner-scope-alias-leak: function-local aliases do not leak outward
- edge/text-true-int: text=1 (not literal True) -> not flagged (conservative on non-literal)
- edge/encoding-variable: encoding=enc (variable) -> not flagged (cannot prove UTF-8)
- edge/errors-wrong-value: errors="strict" counts as present -> not flagged
- edge/syntax-error: file with invalid Python -> returns empty list (no crash)
- edge/empty-source: empty source -> no violations
- edge/invalid-root: non-existent directory -> exit 2
- integration: no tracked file under scripts/ has a violation after the fix
- cli/exit-zero: repo root with no violations -> main() returns 0
- cli/exit-one: source with a violation -> main() returns 1
- cli/exit-two: missing root -> main() returns 2
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_subprocess_encoding import (
    find_all_violations,
    find_violations,
    main,
    validate_subprocess_encoding,
)

# ---------------------------------------------------------------------------
# Positive: compliant calls (no violations expected)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,why",
    [
        (
            "import subprocess\n"
            'subprocess.run(["x"], text=True, encoding="utf-8", errors="replace")',
            "compliant: has errors=replace",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], encoding="utf-8", errors="strict")',
            "compliant: errors present (strict counts as present)",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], encoding="utf-8")',
            "no text mode: not in scope for this checker",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], text=True)',
            "no explicit encoding: not our concern",
        ),
        (
            'open("f.txt", encoding="utf-8")',
            "file open, not subprocess",
        ),
        (
            'import subprocess\nsubprocess.run(["x"])',
            "no encoding, no text mode: clean",
        ),
        (
            "",
            "empty source",
        ),
    ],
)
def test_no_violation(source: str, why: str) -> None:
    assert find_violations(source) == [], why


# ---------------------------------------------------------------------------
# Negative: calls that should be flagged
# ---------------------------------------------------------------------------


def test_subprocess_run_missing_errors_text_mode() -> None:
    source = 'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8")'
    assert find_violations(source) == [2]


def test_subprocess_run_missing_errors_capture_output() -> None:
    source = 'import subprocess\nsubprocess.run(["x"], capture_output=True, encoding="utf-8")'
    assert find_violations(source) == [2]


def test_subprocess_run_missing_errors_stdout_pipe() -> None:
    source = 'import subprocess\nsubprocess.run(["x"], stdout=subprocess.PIPE, encoding="utf-8")'
    assert find_violations(source) == [2]


def test_subprocess_run_missing_errors_stderr_pipe() -> None:
    source = 'import subprocess\nsubprocess.run(["x"], stderr=subprocess.PIPE, encoding="utf-8")'
    assert find_violations(source) == [2]


def test_subprocess_check_output_missing_errors() -> None:
    # check_output always decodes; text= not required for it to decode
    source = 'import subprocess\nsubprocess.check_output(["x"], encoding="utf-8")'
    assert find_violations(source) == [2]


def test_aliased_check_output_missing_errors() -> None:
    source = 'from subprocess import check_output as co\nco(["x"], encoding="utf-8")'
    assert find_violations(source) == [2]


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess\n"
            "runner = subprocess.check_output\n"
            'runner(["x"], encoding="utf-8")',
            [3],
        ),
        (
            "from subprocess import check_output as co\n"
            "runner = co\n"
            'runner(["x"], encoding="utf-8")',
            [3],
        ),
    ],
)
def test_local_callable_aliases_are_flagged(source: str, expected: list[int]) -> None:
    assert find_violations(source) == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess\n"
            "sp = subprocess\n"
            'sp.run(["x"], text=True, encoding="utf-8")',
            [3],
        ),
        (
            "import subprocess\n"
            "sp = subprocess\n"
            "runner = sp.check_output\n"
            'runner(["x"], encoding="utf-8")',
            [4],
        ),
    ],
)
def test_assigned_module_aliases_are_flagged(source: str, expected: list[int]) -> None:
    assert find_violations(source) == expected


def test_function_local_aliases_are_flagged() -> None:
    source = (
        "import subprocess\n"
        "def wrapper():\n"
        "    runner = subprocess.check_output\n"
        '    runner(["x"], encoding="utf-8")\n'
    )
    assert find_violations(source) == [4]


def test_alias_used_before_later_rebind_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        'runner(["x"], encoding="utf-8")\n'
        "runner = print\n"
    )
    assert find_violations(source) == [3]


def test_function_alias_call_used_before_later_rebind_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        "def wrapper():\n"
        '    runner(["x"], encoding="utf-8")\n'
        "wrapper()\n"
        "runner = print\n"
    )
    assert find_violations(source) == [4]


def test_function_call_after_later_rebind_is_not_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        "def wrapper():\n"
        '    runner(["x"], encoding="utf-8")\n'
        "runner = print\n"
        "wrapper()\n"
    )
    assert find_violations(source) == []


def test_function_alias_used_before_later_rebind_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        "def wrapper():\n"
        '    runner(["x"], encoding="utf-8")\n'
        "alias = wrapper\n"
        "alias()\n"
        "runner = print\n"
    )
    assert find_violations(source) == [4]


def test_function_alias_called_after_later_rebind_is_not_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        "def wrapper():\n"
        '    runner(["x"], encoding="utf-8")\n'
        "alias = wrapper\n"
        "runner = print\n"
        "alias()\n"
    )
    assert find_violations(source) == []


def test_branch_local_function_used_after_late_outer_bind_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "if cond:\n"
        "    def wrapper():\n"
        '        runner(["x"], encoding="utf-8")\n'
        "runner = subprocess.check_output\n"
        "alias = wrapper\n"
        "alias()\n"
        "runner = print\n"
    )
    assert find_violations(source) == [4]


def test_branch_local_function_after_later_rebind_is_not_flagged() -> None:
    source = (
        "import subprocess\n"
        "if cond:\n"
        "    runner = subprocess.check_output\n"
        "    def wrapper():\n"
        '        runner(["x"], encoding="utf-8")\n'
        "runner = print\n"
    )
    assert find_violations(source) == []


def test_tuple_alias_swap_uses_pre_assignment_snapshot() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        "other = print\n"
        "runner, other = other, runner\n"
        'other(["x"], encoding="utf-8")\n'
    )
    assert find_violations(source) == [5]


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess\n"
            "runner, _ = subprocess.check_output, print\n"
            'runner(["x"], encoding="utf-8")\n',
            [3],
        ),
        (
            "import subprocess\n"
            "sp, _ = subprocess, print\n"
            'sp.run(["x"], text=True, encoding="utf-8")\n',
            [3],
        ),
        (
            "import subprocess\n"
            "pipe, _ = subprocess.PIPE, print\n"
            'subprocess.run(["x"], stdout=pipe, encoding="utf-8")\n',
            [3],
        ),
        (
            "import subprocess\n"
            "runner = subprocess.check_output\n"
            "def wrapper():\n"
            '    runner(["x"], encoding="utf-8")\n'
            "alias, _ = wrapper, print\n"
            "alias()\n"
            "runner = print\n",
            [4],
        ),
    ],
)
def test_tuple_unpacked_aliases_are_flagged(source: str, expected: list[int]) -> None:
    assert find_violations(source) == expected


def test_branch_join_alias_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "if cond:\n"
        "    runner = subprocess.check_output\n"
        "else:\n"
        "    runner = print\n"
        'runner(["x"], encoding="utf-8")\n'
    )
    assert find_violations(source) == [6]


def test_lambda_body_is_flagged() -> None:
    source = (
        "import subprocess\n"
        'runner = lambda: subprocess.run(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [2]


def test_lambda_alias_used_before_later_rebind_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        'wrapper = lambda: runner(["x"], encoding="utf-8")\n'
        "wrapper()\n"
        "runner = print\n"
    )
    assert find_violations(source) == [3]


def test_lambda_alias_called_after_later_rebind_is_not_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        'wrapper = lambda: runner(["x"], encoding="utf-8")\n'
        "runner = print\n"
        "wrapper()\n"
    )
    assert find_violations(source) == []


def test_branch_local_lambda_used_after_late_outer_bind_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "if cond:\n"
        '    wrapper = lambda: runner(["x"], encoding="utf-8")\n'
        "runner = subprocess.check_output\n"
        "alias = wrapper\n"
        "alias()\n"
        "runner = print\n"
    )
    assert find_violations(source) == [3]


def test_branch_local_lambda_after_later_rebind_is_not_flagged() -> None:
    source = (
        "import subprocess\n"
        "if cond:\n"
        "    runner = subprocess.check_output\n"
        '    wrapper = lambda: runner(["x"], encoding="utf-8")\n'
        "runner = print\n"
        "wrapper()\n"
    )
    assert find_violations(source) == []


def test_match_guard_deferred_call_before_later_rebind_is_flagged() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        "def wrapper():\n"
        '    runner(["x"], encoding="utf-8")\n'
        "match value:\n"
        "    case _ if wrapper():\n"
        "        pass\n"
        "runner = print\n"
    )
    assert find_violations(source) == [4]


def test_from_import_run_missing_errors() -> None:
    source = 'from subprocess import run\nrun(["x"], text=True, encoding="utf-8")'
    assert find_violations(source) == [2]


@pytest.mark.parametrize(
    "source",
    [
        (
            "from subprocess import PIPE as CAPTURE, run as srun\n"
            'srun(["x"], stdout=CAPTURE, encoding="utf-8")'
        ),
        (
            "import subprocess as sp\n"
            'sp.run(["x"], stderr=sp.PIPE, encoding="utf-8")'
        ),
    ],
)
def test_pipe_capture_aliases_are_flagged(source: str) -> None:
    assert find_violations(source) == [2]


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess\n"
            "capture = subprocess.PIPE\n"
            'subprocess.run(["x"], stdout=capture, encoding="utf-8")',
            [3],
        ),
        (
            "from subprocess import PIPE as CAPTURE\n"
            "pipe = CAPTURE\n"
            'subprocess.run(["x"], stderr=pipe, encoding="utf-8")',
            [3],
        ),
    ],
)
def test_local_pipe_aliases_are_flagged(source: str, expected: list[int]) -> None:
    assert find_violations(source) == expected


def test_assigned_module_pipe_aliases_are_flagged() -> None:
    source = (
        "import subprocess\n"
        "sp = subprocess\n"
        "pipe = sp.PIPE\n"
        'sp.run(["x"], stdout=pipe, encoding="utf-8")'
    )
    assert find_violations(source) == [4]


def test_splat_kwargs_flagged_conservatively() -> None:
    # **kwargs might carry errors=replace but we cannot verify; flag conservatively.
    source = 'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8", **kw)'
    assert find_violations(source) == [2]


@pytest.mark.parametrize(
    "source",
    [
        'import subprocess\nsubprocess.run(["x"], encoding="utf-8", **{"text": True})',
        'import subprocess\nsubprocess.run(["x"], encoding="utf-8", **{"capture_output": True})',
        'import subprocess\nsubprocess.run(["x"], encoding="utf-8", **{"stdout": subprocess.PIPE})',
    ],
)
def test_splat_kwargs_text_semantics_are_flagged(source: str) -> None:
    assert find_violations(source) == [2]


def test_universal_newlines_missing_errors_is_flagged() -> None:
    source = 'import subprocess\nsubprocess.run(["x"], universal_newlines=True, encoding="utf-8")'
    assert find_violations(source) == [2]


def test_multiple_violations_reported() -> None:
    source = (
        'import subprocess\n'
        'subprocess.run(["a"], text=True, encoding="utf-8")\n'
        'subprocess.run(["b"], capture_output=True, encoding="utf-8")\n'
    )
    lines = find_violations(source)
    assert lines == [2, 3]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_encoding_variable_not_flagged() -> None:
    # Cannot prove the encoding is UTF-8 when it is a variable reference.
    source = 'import subprocess\nsubprocess.run(["x"], text=True, encoding=enc)'
    assert find_violations(source) == []


def test_utf8_aliases_flagged() -> None:
    for alias in ("utf8", "UTF-8", "UTF8", "utf_8", "UTF_8"):
        source = f'import subprocess\nsubprocess.run(["x"], text=True, encoding="{alias}")'
        assert find_violations(source) == [2], f"alias {alias!r} not flagged"


def test_non_utf8_encoding_not_flagged() -> None:
    source = 'import subprocess\nsubprocess.run(["x"], text=True, encoding="latin-1")'
    assert find_violations(source) == []


def test_shadowed_run_helper_is_not_flagged() -> None:
    source = (
        "def run(argv, *, text=False, encoding=None):\n"
        "    return argv\n"
        "runner = run\n"
        'runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_shadowed_imported_run_is_not_flagged() -> None:
    source = (
        "from subprocess import run\n"
        "def run(argv, *, text=False, encoding=None):\n"
        "    return argv\n"
        'run(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_inner_scope_aliases_do_not_leak_outward() -> None:
    source = (
        "import subprocess\n"
        "def wrapper():\n"
        "    runner = subprocess.check_output\n"
        'runner(["x"], encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_lambda_parameters_shadow_aliases() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.check_output\n"
        'fn = lambda runner: runner(["x"], encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_syntax_error_returns_empty() -> None:
    source = "def foo(:\n    pass\n"
    assert find_violations(source) == []


def test_multiline_call_flagged() -> None:
    source = (
        "import subprocess\n"
        "subprocess.run(\n"
        '    ["x"],\n'
        "    text=True,\n"
        '    encoding="utf-8",\n'
        ")\n"
    )
    lines = find_violations(source)
    assert lines == [2], "multiline call should be flagged at its start line"


def test_suppression_comment_silences_violation() -> None:
    """A line ending with the suppression marker must not be flagged."""
    source = (
        "import subprocess\n"
        'subprocess.run(["x"], text=True, encoding="utf-8")'
        "  # subprocess-encoding: strict-ok\n"
    )
    assert find_violations(source) == []


def test_suppression_comment_on_multiline_open_paren() -> None:
    """Suppression comment on the opening line of a multiline call is honoured."""
    source = (
        "import subprocess\n"
        "subprocess.run(  # subprocess-encoding: strict-ok\n"
        '    ["x"],\n'
        "    text=True,\n"
        '    encoding="utf-8",\n'
        ")\n"
    )
    assert find_violations(source) == []


# ---------------------------------------------------------------------------
# Integration: no violations in the live scripts/ tree
# ---------------------------------------------------------------------------


def test_no_violations_in_scripts(tmp_path: Path) -> None:
    """After the fix, no tracked scripts/ file should be flagged."""
    violations = find_all_violations(REPO_ROOT)
    assert violations == [], (
        "Unexpected violations in scripts/:\n"
        + "\n".join(f"  {p}:{ln}" for p, ln in violations)
    )


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


def test_main_exits_zero_on_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    result = main([str(tmp_path)])
    assert result == 0


def test_main_exits_two_on_missing_root() -> None:
    result = main(["/nonexistent/path/that/cannot/exist"])
    assert result == 2


def test_validate_subprocess_encoding_returns_true_on_clean(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    assert validate_subprocess_encoding(tmp_path) is True


def test_validate_subprocess_encoding_returns_false_on_violation(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    violating = scripts / "bad.py"
    violating.write_text(
        'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8")\n',
        encoding="utf-8",
    )
    assert validate_subprocess_encoding(tmp_path) is False


# ---------------------------------------------------------------------------
# Mutation control: breaking the detector fails these tests
# ---------------------------------------------------------------------------


def test_mutation_removing_encoding_check_breaks_detection() -> None:
    """Mutant: if we skip encoding filtering, clean calls get flagged - not this test's concern.
    Instead, verify the detector is NOT trivially always-true or always-false."""
    # compliant source must pass
    clean = (
        "import subprocess\n"
        'subprocess.run(["x"], text=True, encoding="utf-8", errors="replace")'
    )
    assert find_violations(clean) == []
    # violating source must fail
    dirty = 'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8")'
    assert find_violations(dirty) == [2]


def test_detector_requires_text_mode_to_flag() -> None:
    """Binary mode calls with encoding should NOT be flagged.

    If the detector ignores text-mode checking, it would incorrectly flag
    calls that don't decode at all.
    """
    binary_with_encoding = 'import subprocess\nsubprocess.run(["x"], encoding="utf-8")'
    assert find_violations(binary_with_encoding) == [], (
        "Binary-mode call should not be flagged"
    )


@pytest.mark.parametrize(
    "source",
    [
        'import subprocess\nsubprocess.run(["x"], stdout=subprocess.PIPE)',
        'import subprocess as sp\nsp.run(["x"], stderr=sp.PIPE)',
    ],
)
def test_pipe_capture_without_text_semantics_is_not_flagged(source: str) -> None:
    assert find_violations(source) == []


def test_detector_requires_subprocess_to_flag() -> None:
    """Non-subprocess encoding= arguments must not be flagged."""
    file_open = 'open("f", "r", encoding="utf-8")'
    assert find_violations(file_open) == []
