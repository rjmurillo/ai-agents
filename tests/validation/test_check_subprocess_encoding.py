# taste-lint: ignore file-size, one suite owns the validator's flow and mutation matrix.
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
- neg/from-import: ``from subprocess import run; run(...)`` -> flagged
- neg/splat: **kwargs present means errors may be absent -> flagged (conservative)
- edge/text-true-int: text=1 (not literal True) -> not flagged (conservative on non-literal)
- edge/encoding-variable: encoding=enc (variable) -> not flagged (cannot prove UTF-8)
- edge/errors-wrong-value: errors="strict" remains a violation
- edge/syntax-error: invalid Python fails closed
- edge/empty-source: empty source -> no violations
- edge/invalid-root: non-existent directory -> exit 2
- edge/empty-scope: zero tracked scripts -> exit 2
- edge/git-failure: unavailable tracked-file inventory -> exit 2
- integration: no tracked file under scripts/ has a violation after the fix
- cli/exit-zero: repo root with no violations -> main() returns 0
- cli/exit-one: source with a violation -> main() returns 1
- cli/exit-two: missing root -> main() returns 2
"""

from __future__ import annotations

import subprocess
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


def make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a repository with the supplied tracked files."""
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


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


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_subprocess_run_missing_errors_explicit_pipe(stream: str) -> None:
    source = f'import subprocess\nsubprocess.run(["x"], {stream}=subprocess.PIPE, encoding="utf-8")'
    assert find_violations(source) == [2]


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_subprocess_run_missing_errors_module_aliased_pipe(stream: str) -> None:
    source = f'import subprocess as sp\nsp.run(["x"], {stream}=sp.PIPE, encoding="utf-8")'
    assert find_violations(source) == [2]


@pytest.mark.parametrize(
    "source,expected_line",
    [
        (
            'from subprocess import PIPE, run\nrun(["x"], stdout=PIPE, encoding="utf-8")',
            2,
        ),
        (
            "from subprocess import PIPE as pipe, run as runner\n"
            'runner(["x"], stderr=pipe, encoding="utf-8")',
            2,
        ),
        (
            "import subprocess as sp\n"
            "pipe = sp.PIPE\n"
            "runner = sp.run\n"
            'runner(["x"], stdout=pipe, encoding="utf-8")',
            4,
        ),
    ],
)
def test_subprocess_pipe_aliases_are_flagged(source: str, expected_line: int) -> None:
    assert find_violations(source) == [expected_line]


@pytest.mark.parametrize(
    "source,expected_line",
    [
        (
            "import subprocess as sp\n"
            "runner, pipe = sp.run, sp.PIPE\n"
            'runner(["x"], stdout=pipe, encoding="utf-8")',
            3,
        ),
        (
            "from subprocess import PIPE, run\n"
            "runner, pipe = run, PIPE\n"
            'runner(["x"], stdout=pipe, encoding="utf-8")',
            3,
        ),
        (
            "import subprocess as sp\n"
            "runner: object = sp.run\n"
            "pipe: object = sp.PIPE\n"
            'runner(["x"], stdout=pipe, encoding="utf-8")',
            4,
        ),
        (
            "import subprocess as sp\n"
            "pipe = other = sp.PIPE\n"
            'sp.run(["x"], stdout=pipe, encoding="utf-8")',
            3,
        ),
    ],
)
def test_non_simple_subprocess_rebindings_are_flagged(source: str, expected_line: int) -> None:
    assert find_violations(source) == [expected_line]


def test_subprocess_check_output_missing_errors() -> None:
    # check_output always decodes; text= not required for it to decode
    source = 'import subprocess\nsubprocess.check_output(["x"], encoding="utf-8")'
    assert find_violations(source) == [2]


def test_subprocess_getstatusoutput_missing_errors() -> None:
    source = 'import subprocess\nsubprocess.getstatusoutput("x", encoding="utf-8")'
    assert find_violations(source) == [2]


def test_subprocess_getstatusoutput_replace_is_allowed() -> None:
    """Mutation control: the new entry point still accepts replacement decoding."""
    source = (
        'import subprocess\nsubprocess.getstatusoutput("x", encoding="utf-8", errors="replace")'
    )
    assert find_violations(source) == []


def test_from_import_run_missing_errors() -> None:
    source = 'from subprocess import run\nrun(["x"], text=True, encoding="utf-8")'
    assert find_violations(source) == [2]


def test_strict_errors_remains_a_violation() -> None:
    source = (
        'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8", errors="strict")'
    )
    assert find_violations(source) == [2]


@pytest.mark.parametrize(
    "source,expected_line",
    [
        (
            'import subprocess as sp\nsp.run(["x"], text=True, encoding="utf-8")',
            2,
        ),
        (
            'from subprocess import run as runner\nrunner(["x"], text=True, encoding="utf-8")',
            2,
        ),
        (
            "import subprocess\n"
            "runner = subprocess.run\n"
            'runner(["x"], text=True, encoding="utf-8")',
            3,
        ),
    ],
)
def test_subprocess_aliases_are_flagged(source: str, expected_line: int) -> None:
    assert find_violations(source) == [expected_line]


def test_splat_kwargs_flagged_conservatively() -> None:
    # **kwargs might carry errors=replace but we cannot verify; flag conservatively.
    source = 'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8", **kw)'
    assert find_violations(source) == [2]


def test_multiple_violations_reported() -> None:
    source = (
        "import subprocess\n"
        'subprocess.run(["a"], text=True, encoding="utf-8")\n'
        'subprocess.run(["b"], capture_output=True, encoding="utf-8")\n'
    )
    lines = find_violations(source)
    assert lines == [2, 3]


def test_conditional_rebinding_preserves_possible_subprocess_alias() -> None:
    source = (
        "import subprocess as sp\n"
        "runner = sp.run\n"
        "if use_fake:\n"
        "    runner = fake\n"
        'runner(["x"], capture_output=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [5]


@pytest.mark.parametrize(
    "source,expected_line",
    [
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "for value in maybe_empty:\n"
            "    runner = fake\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n',
            5,
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "while condition:\n"
            "    runner = fake\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n',
            5,
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "try:\n"
            "    runner = fake\n"
            "except NameError:\n"
            "    pass\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n',
            7,
        ),
    ],
)
def test_control_flow_rebinding_preserves_possible_subprocess_alias(
    source: str, expected_line: int
) -> None:
    assert find_violations(source) == [expected_line]


def test_exhaustive_non_subprocess_branches_clear_subprocess_alias() -> None:
    """Mutation control: joining branches must not retain impossible aliases."""
    source = (
        "import subprocess as sp\n"
        "runner = sp.run\n"
        "if use_first_fake:\n"
        "    runner = first_fake\n"
        "else:\n"
        "    runner = second_fake\n"
        'runner(["x"], capture_output=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_loop_target_clears_outer_subprocess_alias_inside_body() -> None:
    """Mutation control: an unknown loop value must not inherit the outer alias."""
    source = (
        "import subprocess as sp\n"
        "runner = sp.run\n"
        "for runner in factories:\n"
        '    runner(["x"], capture_output=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


@pytest.mark.parametrize(
    "source,expected_line",
    [
        (
            "import subprocess as sp\n"
            "runner = fake\n"
            "for runner in [sp.run]:\n"
            '    runner(["x"], capture_output=True, encoding="utf-8")\n',
            4,
        ),
        (
            "import subprocess as sp\n"
            "runner = fake\n"
            "for runner in [sp.run]:\n"
            "    pass\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n',
            5,
        ),
        (
            "import subprocess as sp\n"
            "runner = fake\n"
            '[runner(["x"], capture_output=True, encoding="utf-8") for runner in [sp.run]]\n',
            3,
        ),
    ],
)
def test_static_iteration_subprocess_bindings_are_flagged(source: str, expected_line: int) -> None:
    assert find_violations(source) == [expected_line]


@pytest.mark.parametrize(
    "source",
    [
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "for runner in [fake]:\n"
            "    pass\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n'
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            '[runner(["x"], capture_output=True, encoding="utf-8") for runner in [fake]]\n'
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            'invoke = lambda runner: runner(["x"], capture_output=True, encoding="utf-8")\n'
        ),
    ],
)
def test_iteration_and_lambda_shadowing_do_not_leak_outer_alias(source: str) -> None:
    """Mutation control: lexical targets replace the outer binding."""
    assert find_violations(source) == []


def test_nested_comprehension_propagates_static_subprocess_binding() -> None:
    source = (
        "import subprocess as sp\n"
        '[fn(["x"], text=True, encoding="utf-8") for row in [[sp.run]] for fn in row]\n'
    )
    assert find_violations(source) == [2]


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess as sp\n"
            "from contextlib import nullcontext\n"
            "with nullcontext(sp.run) as runner:\n"
            '    runner(["x"], text=True, encoding="utf-8")\n',
            [4],
        ),
        (
            "import subprocess as sp\n"
            "from contextlib import nullcontext\n"
            "runner = sp.run\n"
            "with nullcontext(fake) as runner:\n"
            '    runner(["x"], text=True, encoding="utf-8")\n',
            [],
        ),
    ],
)
def test_with_target_updates_subprocess_binding(source: str, expected: list[int]) -> None:
    assert find_violations(source) == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess as sp\n"
            "match (sp.run,):\n"
            "    case (runner,):\n"
            '        runner(["x"], text=True, encoding="utf-8")\n',
            [4],
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "match (fake,):\n"
            "    case (runner,):\n"
            '        runner(["x"], text=True, encoding="utf-8")\n',
            [],
        ),
    ],
)
def test_match_capture_updates_subprocess_binding(source: str, expected: list[int]) -> None:
    assert find_violations(source) == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess as sp\n"
            "def outer():\n"
            "    import fake_subprocess as sp\n"
            "    def inner():\n"
            "        global sp\n"
            '        sp.run(["x"], text=True, encoding="utf-8")\n',
            [6],
        ),
        (
            "import fake_subprocess as sp\n"
            "def outer():\n"
            "    import subprocess as sp\n"
            "    def inner():\n"
            "        global sp\n"
            '        sp.run(["x"], text=True, encoding="utf-8")\n',
            [],
        ),
        (
            "import fake_subprocess as runner\n"
            "import subprocess as sp\n"
            "def outer():\n"
            "    def inner():\n"
            "        nonlocal runner\n"
            '        runner(["x"], text=True, encoding="utf-8")\n'
            "    runner = sp.run\n",
            [6],
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "def outer():\n"
            "    def inner():\n"
            "        nonlocal runner\n"
            '        runner(["x"], text=True, encoding="utf-8")\n'
            "    runner = fake\n",
            [],
        ),
    ],
)
def test_global_and_nonlocal_use_declared_scope_bindings(source: str, expected: list[int]) -> None:
    assert find_violations(source) == expected


def test_loop_else_without_break_replaces_subprocess_alias() -> None:
    """Mutation control: an unavoidable else removes the stale loop-body state."""
    source = (
        "import subprocess as sp\n"
        "runner = sp.run\n"
        "for _ in [1]:\n"
        "    pass\n"
        "else:\n"
        "    runner = fake\n"
        'runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_loop_else_with_break_preserves_possible_subprocess_alias() -> None:
    source = (
        "import subprocess as sp\n"
        "runner = sp.run\n"
        "for stop in [True, False]:\n"
        "    if stop:\n"
        "        break\n"
        "else:\n"
        "    runner = fake\n"
        'runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


def test_comprehension_walrus_updates_enclosing_subprocess_alias() -> None:
    source = (
        "import subprocess as sp\n"
        "runner = fake\n"
        "[(runner := sp.run) for _ in [1]]\n"
        'runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [4]


def test_empty_comprehension_preserves_preexisting_alias() -> None:
    """Mutation control: a walrus in an empty comprehension never executes."""
    source = (
        "import subprocess as sp\n"
        "runner = sp.run\n"
        "[(runner := fake) for _ in []]\n"
        'runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [4]


def test_irrefutable_match_drops_impossible_incoming_alias() -> None:
    """Mutation control: a wildcard case always replaces the prior binding."""
    source = (
        "import subprocess as sp\n"
        "runner = sp.run\n"
        "match value:\n"
        "    case _:\n"
        "        runner = fake\n"
        'runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_terminating_match_case_does_not_hide_reachable_sibling_case() -> None:
    source = (
        "import subprocess\n"
        "def invoke(values):\n"
        "    for value in values:\n"
        "        match value:\n"
        "            case 1:\n"
        "                break\n"
        "            case _:\n"
        "                runner = subprocess.run\n"
        '        runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [9]


def test_exhaustive_terminating_match_keeps_following_call_unreachable() -> None:
    """Mutation control: no match case reaches the call after the match."""
    source = (
        "import subprocess\n"
        "for value in values:\n"
        "    match value:\n"
        "        case 1:\n"
        "            break\n"
        "        case _:\n"
        "            continue\n"
        '    subprocess.run(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_module_alias_defined_after_function_is_visible_at_runtime() -> None:
    source = (
        "def invoke():\n"
        '    sp.run(["x"], text=True, encoding="utf-8")\n'
        "import subprocess as sp\n"
        "invoke()\n"
    )
    assert find_violations(source) == [2]


def test_module_constant_defined_after_function_is_visible_at_runtime() -> None:
    source = (
        "import subprocess\n"
        "def invoke():\n"
        "    if ENABLED:\n"
        '        subprocess.run(["x"], text=True, encoding="utf-8")\n'
        "ENABLED = False\n"
        "invoke()\n"
    )
    assert find_violations(source) == []


def test_late_true_module_constant_does_not_hide_violation() -> None:
    """Mutation control: a true late-bound constant keeps the call reachable."""
    source = (
        "import subprocess\n"
        "def invoke():\n"
        "    if ENABLED:\n"
        '        subprocess.run(["x"], text=True, encoding="utf-8")\n'
        "ENABLED = True\n"
        "invoke()\n"
    )
    assert find_violations(source) == [4]


def test_mutated_module_constant_does_not_hide_earlier_violation() -> None:
    source = (
        "import subprocess\n"
        "ENABLED = True\n"
        "def invoke():\n"
        "    if ENABLED:\n"
        '        subprocess.run(["x"], text=True, encoding="utf-8")\n'
        "try:\n"
        "    invoke()\n"
        "finally:\n"
        "    ENABLED = False\n"
    )
    assert find_violations(source) == [5]


def test_single_assignment_module_constant_still_prunes_dead_branch() -> None:
    """Mutation control: one late assignment remains a stable module constant."""
    source = (
        "import subprocess\n"
        "def invoke():\n"
        "    if ENABLED:\n"
        '        subprocess.run(["x"], text=True, encoding="utf-8")\n'
        "ENABLED = False\n"
        "invoke()\n"
    )
    assert find_violations(source) == []


def test_module_walrus_mutation_prevents_constant_pruning() -> None:
    source = (
        "import subprocess\n"
        "FLAG = True\n"
        "def invoke():\n"
        "    if FLAG:\n"
        '        subprocess.run(["x"], text=True, encoding="utf-8")\n'
        "invoke()\n"
        "(FLAG := False)\n"
    )
    assert find_violations(source) == [5]


def test_module_constant_with_nested_global_writer_is_not_stable() -> None:
    source = (
        "import subprocess\n"
        "FLAG = False\n"
        "def enable():\n"
        "    global FLAG\n"
        "    FLAG = True\n"
        "def invoke():\n"
        "    if FLAG:\n"
        '        subprocess.run(["x"], text=True, encoding="utf-8")\n'
        "enable()\n"
        "invoke()\n"
    )
    assert find_violations(source) == [8]


def test_nested_function_resolves_late_enclosing_alias() -> None:
    source = (
        "def outer():\n"
        "    def inner():\n"
        '        runner(["x"], text=True, encoding="utf-8")\n'
        "    import subprocess\n"
        "    runner = subprocess.run\n"
        "    inner()\n"
        "outer()\n"
    )
    assert find_violations(source) == [3]


def test_nested_function_resolves_late_walrus_alias() -> None:
    source = (
        "import subprocess\n"
        "def outer():\n"
        "    def inner():\n"
        '        runner(["x"], text=True, encoding="utf-8")\n'
        "    (runner := subprocess.run)\n"
        "    inner()\n"
        "outer()\n"
    )
    assert find_violations(source) == [4]


def test_nested_function_local_binding_shadows_enclosing_alias() -> None:
    """Mutation control: a local declaration prevents closure resolution."""
    source = (
        "def outer():\n"
        "    import subprocess\n"
        "    runner = subprocess.run\n"
        "    def inner():\n"
        "        runner = len\n"
        '        runner(["x"], text=True, encoding="utf-8")\n'
        "    inner()\n"
        "outer()\n"
    )
    assert find_violations(source) == []


def test_finally_sees_binding_active_when_try_statement_raises() -> None:
    source = (
        "import subprocess\n"
        "def invoke():\n"
        "    runner = len\n"
        "    try:\n"
        "        runner = subprocess.run\n"
        "        explode()\n"
        "        runner = len\n"
        "    finally:\n"
        '        runner(["x"], text=True, encoding="utf-8")\n'
        "invoke()\n"
    )
    assert find_violations(source) == [9]


def test_finally_sees_exception_state_inside_compound_statement() -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "try:\n"
        "    if condition():\n"
        "        runner = subprocess.run\n"
        "        explode()\n"
        "    runner = len\n"
        "finally:\n"
        '    runner(["x"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [9]


def test_outer_finally_sees_exception_state_inside_nested_try() -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "try:\n"
        "    try:\n"
        "        runner = subprocess.run\n"
        "        explode()\n"
        "    finally:\n"
        "        pass\n"
        "    runner = len\n"
        "finally:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [11]


def test_nested_try_normal_path_can_clear_subprocess_binding() -> None:
    """Mutation control: a nonraising nested try reaches the clearing assignment."""
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "try:\n"
        "    try:\n"
        "        runner = len\n"
        "    finally:\n"
        "        pass\n"
        "finally:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_with_body_exception_state_reaches_handler() -> None:
    source = (
        "import subprocess\n"
        "from contextlib import nullcontext\n"
        "runner = len\n"
        "try:\n"
        "    with nullcontext():\n"
        "        runner = subprocess.run\n"
        "        explode()\n"
        "        runner = len\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [10]


def test_later_with_item_failure_retains_earlier_item_binding() -> None:
    source = (
        "import subprocess\n"
        "from contextlib import nullcontext\n"
        "runner = len\n"
        "try:\n"
        "    with nullcontext(subprocess.run) as runner, explode():\n"
        "        runner = len\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


def test_with_context_walrus_binding_reaches_handler() -> None:
    source = (
        "import subprocess\n"
        "from contextlib import nullcontext\n"
        "runner = len\n"
        "try:\n"
        "    with nullcontext() as _, explode(runner := subprocess.run):\n"
        "        runner = len\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


def test_nonraising_with_context_walrus_clears_stale_binding() -> None:
    source = (
        "import subprocess\n"
        "from contextlib import nullcontext\n"
        "runner = subprocess.run\n"
        "try:\n"
        "    with nullcontext(runner := len):\n"
        "        raise ValueError()\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_raising_nullcontext_argument_retains_prior_binding() -> None:
    source = (
        "import subprocess\n"
        "from contextlib import nullcontext\n"
        "runner = subprocess.run\n"
        "try:\n"
        "    with nullcontext(resolve_value()) as runner:\n"
        "        runner = len\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


def test_nullcontext_descriptor_failure_retains_prior_binding() -> None:
    source = (
        "import subprocess\n"
        "from contextlib import nullcontext\n"
        "runner = subprocess.run\n"
        "try:\n"
        "    with nullcontext(holder.value) as runner:\n"
        "        runner = len\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


@pytest.mark.parametrize("loop", ("for _ in flaky_iter():", "while condition():"))
def test_repeated_loop_test_exception_retains_body_binding(loop: str) -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "try:\n"
        f"    {loop}\n"
        "        runner = subprocess.run\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [7]


def test_match_guard_exception_retains_pattern_binding() -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "try:\n"
        "    match (subprocess.run,):\n"
        "        case (runner,) if explode():\n"
        "            pass\n"
        "except Exception:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


def test_caught_nested_exception_does_not_reach_outer_finally() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "try:\n"
        "    try:\n"
        "        raise ValueError()\n"
        "    except ValueError:\n"
        "        runner = len\n"
        "finally:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_exception_handler_catches_explicit_exception_subclass() -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "try:\n"
        "    try:\n"
        "        runner = subprocess.run\n"
        "        raise ValueError()\n"
        "    except Exception:\n"
        "        runner = len\n"
        "finally:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_exception_handler_catches_explicit_error_after_delete() -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "payload = object()\n"
        "try:\n"
        "    try:\n"
        "        runner = subprocess.run\n"
        "        del payload\n"
        "        raise ValueError()\n"
        "    except Exception:\n"
        "        runner = len\n"
        "finally:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


@pytest.mark.parametrize("exception", ("KeyboardInterrupt", "SystemExit"))
def test_exception_handler_does_not_catch_base_exception_subclasses(
    exception: str,
) -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "try:\n"
        "    try:\n"
        "        runner = subprocess.run\n"
        f"        raise {exception}()\n"
        "    except Exception:\n"
        "        runner = len\n"
        "finally:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [10]


def test_return_and_raise_terminate_unreachable_flow() -> None:
    source = (
        "import subprocess\n"
        "def invoke(value):\n"
        "    match value:\n"
        "        case 1:\n"
        "            return\n"
        "        case _:\n"
        "            raise ValueError()\n"
        '    subprocess.run([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


@pytest.mark.parametrize(
    "abrupt",
    (
        "return (runner := subprocess.run)",
        "raise RuntimeError(runner := subprocess.run)",
    ),
)
def test_abrupt_expression_binding_reaches_finally(abrupt: str) -> None:
    source = (
        "import subprocess\n"
        "def invoke():\n"
        "    runner = len\n"
        "    try:\n"
        f"        {abrupt}\n"
        "    finally:\n"
        '        runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [7]


@pytest.mark.parametrize(
    "binding,expected",
    (("subprocess.run", [9]), ("len", [])),
)
def test_nested_finally_transforms_escaping_exception_state(
    binding: str,
    expected: list[int],
) -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "try:\n"
        "    try:\n"
        "        raise ValueError()\n"
        "    finally:\n"
        f"        runner = {binding}\n"
        "finally:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == expected


def test_nested_finally_return_clears_binding_before_outer_finally() -> None:
    source = (
        "import subprocess\n"
        "def invoke(fallback=len):\n"
        "    runner = subprocess.run\n"
        "    try:\n"
        "        try:\n"
        "            raise ValueError()\n"
        "        finally:\n"
        "            return (runner := fallback)\n"
        "    finally:\n"
        '        runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_finally_ignores_subprocess_binding_after_nonraising_try() -> None:
    """Mutation control: the normal path clears the alias before finally."""
    source = (
        "import subprocess\n"
        "def invoke():\n"
        "    runner = subprocess.run\n"
        "    try:\n"
        "        runner = len\n"
        "    finally:\n"
        '        runner(["x"], text=True, encoding="utf-8")\n'
        "invoke()\n"
    )
    assert find_violations(source) == []


def test_generator_walrus_does_not_execute_at_creation() -> None:
    """Mutation control: a lazy generator cannot clear the live alias yet."""
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "values = ((runner := len) for _ in [1])\n"
        'runner(["cmd"], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [4]


def test_deterministic_for_retains_last_binding() -> None:
    source = (
        "import subprocess\n"
        "for runner in [subprocess.run, len]:\n"
        "    pass\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_deterministic_for_checks_each_body_binding() -> None:
    """Mutation control: exact exit state must not hide earlier iterations."""
    source = (
        "import subprocess\n"
        "for runner in [subprocess.run, len]:\n"
        '    runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [3]


def test_while_false_body_does_not_change_bindings() -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "while False:\n"
        "    runner = subprocess.run\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_while_true_does_not_retain_impossible_pre_loop_binding() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "while True:\n"
        "    runner = len\n"
        "    break\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_while_true_only_retains_reachable_conditional_break_binding() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "while True:\n"
        "    runner = len\n"
        "    if ready():\n"
        "        break\n"
        "    runner = subprocess.run\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_while_true_break_after_later_iteration_retains_subprocess_binding() -> None:
    """Mutation control: a later iteration can break before clearing the alias."""
    source = (
        "import subprocess\n"
        "runner = len\n"
        "while True:\n"
        "    if ready():\n"
        "        break\n"
        "    runner = subprocess.run\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [7]


@pytest.mark.parametrize("terminator", ("break", "continue"))
def test_loop_terminator_state_includes_finally_rebinding(terminator: str) -> None:
    source = (
        "import subprocess\n"
        "runner = len\n"
        "while condition():\n"
        "    try:\n"
        "        runner = subprocess.run\n"
        f"        {terminator}\n"
        "    finally:\n"
        "        runner = len\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_finally_can_create_subprocess_break_binding() -> None:
    """Mutation control: the break exit must include assignments from finally."""
    source = (
        "import subprocess\n"
        "runner = len\n"
        "while True:\n"
        "    try:\n"
        "        break\n"
        "    finally:\n"
        "        runner = subprocess.run\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


def test_unreachable_break_does_not_bypass_loop_else() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "for _ in [1]:\n"
        "    if False:\n"
        "        break\n"
        "else:\n"
        "    runner = len\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


@pytest.mark.parametrize("terminator", ["break", "continue"])
def test_conditional_loop_exit_preserves_subprocess_binding(terminator: str) -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "for stop in [True]:\n"
        "    if stop:\n"
        f"        {terminator}\n"
        "    runner = len\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [7]


def test_non_exiting_loop_path_can_clear_subprocess_binding() -> None:
    """Mutation control: the false condition reaches the later assignment."""
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "for stop in [False]:\n"
        "    if stop:\n"
        "        continue\n"
        "    runner = len\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_join_drops_constant_cleared_on_one_branch() -> None:
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "flag = True\n"
        "if condition():\n"
        "    flag = dynamic()\n"
        "if flag:\n"
        "    runner = len\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == [8]


def test_join_retains_constant_known_on_every_branch() -> None:
    """Mutation control: equivalent known values still allow branch pruning."""
    source = (
        "import subprocess\n"
        "runner = subprocess.run\n"
        "flag = True\n"
        "if condition():\n"
        "    flag = 1\n"
        "if flag:\n"
        "    runner = len\n"
        'runner([], text=True, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


@pytest.mark.parametrize(
    "source,expected",
    [
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "runner, *rest = [fake]\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n',
            [],
        ),
        (
            "import subprocess as sp\n"
            "runner = fake\n"
            "runner, *rest = [sp.run]\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n',
            [4],
        ),
        (
            "import subprocess as sp\n"
            "runner = sp.run\n"
            "*rest, runner = [fake]\n"
            'runner(["x"], capture_output=True, encoding="utf-8")\n',
            [],
        ),
    ],
)
def test_starred_assignment_updates_subprocess_bindings(source: str, expected: list[int]) -> None:
    """Regression and mutation controls for extended iterable unpacking."""
    assert find_violations(source) == expected


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_encoding_variable_not_flagged() -> None:
    # Cannot prove the encoding is UTF-8 when it is a variable reference.
    source = 'import subprocess\nsubprocess.run(["x"], text=True, encoding=enc)'
    assert find_violations(source) == []


@pytest.mark.parametrize(
    "alias",
    ("utf8", "UTF-8", "UTF8", "utf_8", "UTF_8", "Utf-8", "uTf_8", "cp65001", "CP65001"),
)
def test_utf8_aliases_flagged(alias: str) -> None:
    source = f'import subprocess\nsubprocess.run(["x"], text=True, encoding="{alias}")'
    assert find_violations(source) == [2]


@pytest.mark.parametrize("alias", ("cp65001", "CP65001", "Utf-8", "uTf_8"))
def test_utf8_aliases_accept_replacement_errors(alias: str) -> None:
    """Mutation control: every accepted UTF-8 alias passes with replacement decoding."""
    source = (
        f'import subprocess\nsubprocess.run(["x"], text=True, encoding="{alias}", errors="replace")'
    )
    assert find_violations(source) == []


def test_non_utf8_encoding_not_flagged() -> None:
    source = 'import subprocess\nsubprocess.run(["x"], text=True, encoding="latin-1")'
    assert find_violations(source) == []


def test_syntax_error_fails_closed() -> None:
    source = "def foo(:\n    pass\n"
    with pytest.raises(SyntaxError):
        find_violations(source)


def test_ambient_git_repository_pointers_do_not_reduce_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = make_repo(
        tmp_path / "target",
        {
            "scripts/clean.py": "x = 1\n",
            "scripts/bad.py": (
                'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8")\n'
            ),
        },
    )
    foreign = make_repo(
        tmp_path / "foreign",
        {"scripts/clean.py": "x = 1\n"},
    )
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))

    findings = find_all_violations(target)

    assert findings == [(target / "scripts/bad.py", 2)]


def test_multiline_call_flagged() -> None:
    source = (
        'import subprocess\nsubprocess.run(\n    ["x"],\n    text=True,\n    encoding="utf-8",\n)\n'
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
    assert violations == [], "Unexpected violations in scripts/:\n" + "\n".join(
        f"  {p}:{ln}" for p, ln in violations
    )


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------


def test_main_exits_zero_on_clean_tree(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "scripts/clean.py": (
                "import subprocess\n"
                'subprocess.run(["x"], text=True, encoding="utf-8", errors="replace")\n'
            )
        },
    )
    result = main([str(repo)])
    assert result == 0


def test_main_exits_two_on_missing_root() -> None:
    result = main(["/nonexistent/path/that/cannot/exist"])
    assert result == 2


def test_validate_subprocess_encoding_returns_true_on_clean(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"scripts/clean.py": "value = 1\n"})
    assert validate_subprocess_encoding(repo) is True


def test_validate_subprocess_encoding_returns_false_on_violation(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {
            "scripts/bad.py": (
                'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8")\n'
            )
        },
    )
    assert validate_subprocess_encoding(repo) is False


def test_main_exits_two_when_git_reports_zero_tracked_scripts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"README.md": "No scripts here.\n"})

    result = main([str(repo)])

    assert result == 2
    assert "zero tracked Python files" in capsys.readouterr().err


def test_main_exits_two_when_git_cannot_list_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "clean.py").write_text("value = 1\n", encoding="utf-8")

    result = main([str(tmp_path)])

    assert result == 2
    assert "git could not list tracked scripts" in capsys.readouterr().err


def test_main_exits_two_on_tracked_syntax_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"scripts/bad.py": "def broken(:\n"})

    result = main([str(repo)])

    assert result == 2
    assert "could not analyze tracked source" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Mutation control: breaking the detector fails these tests
# ---------------------------------------------------------------------------


def test_mutation_removing_encoding_check_breaks_detection() -> None:
    """Mutant: if we skip encoding filtering, clean calls get flagged - not this test's concern.
    Instead, verify the detector is NOT trivially always-true or always-false."""
    # compliant source must pass
    clean = (
        'import subprocess\nsubprocess.run(["x"], text=True, encoding="utf-8", errors="replace")'
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
    assert find_violations(binary_with_encoding) == [], "Binary-mode call should not be flagged"


def test_detector_requires_subprocess_to_flag() -> None:
    """Non-subprocess encoding= arguments must not be flagged."""
    file_open = 'open("f", "r", encoding="utf-8")'
    assert find_violations(file_open) == []


def test_detector_requires_real_pipe_capture_to_flag() -> None:
    """Mutation control: an unrelated PIPE-like value does not enable decoding."""
    source = (
        "class Local:\n"
        "    PIPE = object()\n"
        "local = Local()\n"
        "import subprocess\n"
        'subprocess.run(["x"], stdout=local.PIPE, encoding="utf-8")\n'
    )
    assert find_violations(source) == []


def test_tuple_rebinding_preserves_target_value_pairing() -> None:
    """Mutation control: tuple analysis must not assign PIPE to another target."""
    source = (
        "import subprocess as sp\n"
        "pipe, ordinary = sp.PIPE, object()\n"
        'sp.run(["x"], stdout=ordinary, encoding="utf-8")\n'
    )
    assert find_violations(source) == []
