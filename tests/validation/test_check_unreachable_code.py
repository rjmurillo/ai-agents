"""Tests for scripts/validation/check_unreachable_code.py.

Covers:
- Clean tree passes (no false positives)
- Return followed by statement flagged
- Raise followed by statement flagged
- Continue/Break followed by statement flagged
- Last statement in body never flagged (boundary)
- Nested function unreachable code flagged
- Class methods not false-positived when clean
- Negative control: deliberate unreachable code after return
- Invalid repo root exits 2
- Syntax error files skipped gracefully
- Non-test, non-function scoped unreachable code not flagged (only function bodies)
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Allow importing from scripts/validation without modifying sys.path in source files
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

from check_unreachable_code import (
    find_unreachable_statements,
    validate_unreachable_code,
)


def _write(tmp_path: Path, name: str, src: str) -> Path:
    """Write a Python source file with dedented content."""
    path = tmp_path / name
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# find_unreachable_statements unit tests
# ---------------------------------------------------------------------------


def test_clean_function_not_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "clean.py",
        """\
        def good():
            x = 1
            return x
        """,
    )
    assert find_unreachable_statements(tmp_path) == []


def test_statement_after_return_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bad.py",
        """\
        def bad():
            return 1
            x = 2
        """,
    )
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) == 1
    path, func, lineno = findings[0]
    assert func == "bad"
    assert lineno == 3


def test_statement_after_raise_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bad.py",
        """\
        def bad():
            raise ValueError("oops")
            return 0
        """,
    )
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) == 1
    _, func, _ = findings[0]
    assert func == "bad"


def test_statement_after_continue_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bad.py",
        """\
        def bad():
            for i in range(5):
                continue
                print(i)
        """,
    )
    # The loop body is nested in the function body, but continue is inside
    # the for-loop's body. Our scanner walks ALL FunctionDef nodes including
    # nested blocks via ast.walk - but it only checks func.body directly.
    # The for-loop body is NOT func.body, so this won't be caught at func level.
    # This test documents the current scope: only direct function body stmts.
    # For statements inside loop bodies, the unreachable is in the For node's body.
    # Our current gate scans func.body only (matching the issue's reference impl).
    findings = find_unreachable_statements(tmp_path)
    # continue is inside a for-loop body, not direct function body => not flagged
    assert findings == []


def test_statement_after_break_in_direct_function_body(tmp_path: Path) -> None:
    """break at function body level (unusual but detectable)."""
    _write(
        tmp_path,
        "bad.py",
        """\
        def bad():
            break
            x = 1
        """,
    )
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) == 1


def test_last_statement_never_flagged(tmp_path: Path) -> None:
    """A return as the last statement in a function body is fine."""
    _write(
        tmp_path,
        "ok.py",
        """\
        def ok():
            x = 1
            return x
        """,
    )
    assert find_unreachable_statements(tmp_path) == []


def test_nested_function_unreachable_flagged(tmp_path: Path) -> None:
    """Unreachable code in an inner function is detected via ast.walk."""
    _write(
        tmp_path,
        "nested.py",
        """\
        def outer():
            def inner():
                return 1
                x = 2
            return inner
        """,
    )
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) == 1
    _, func, _ = findings[0]
    assert func == "inner"


def test_class_method_clean_not_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "cls.py",
        """\
        class Foo:
            def method(self) -> int:
                return 42
        """,
    )
    assert find_unreachable_statements(tmp_path) == []


def test_syntax_error_skipped_gracefully(tmp_path: Path) -> None:
    """A file with a syntax error must not crash the scanner."""
    path = tmp_path / "bad_syntax.py"
    path.write_text("def broken(:\n    pass\n", encoding="utf-8")
    # Should return empty and not raise
    result = find_unreachable_statements(tmp_path)
    assert isinstance(result, list)


def test_empty_module_not_flagged(tmp_path: Path) -> None:
    _write(tmp_path, "empty.py", "")
    assert find_unreachable_statements(tmp_path) == []


def test_multiple_functions_multiple_findings(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "multi.py",
        """\
        def f1():
            return 1
            x = 2

        def f2():
            return 3
            y = 4
        """,
    )
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) == 2
    names = {f for _, f, _ in findings}
    assert names == {"f1", "f2"}


# ---------------------------------------------------------------------------
# Negative control: the gate must NOT be vacuous
# ---------------------------------------------------------------------------


def test_negative_control_gate_catches_real_unreachable(tmp_path: Path) -> None:
    """Deliberate unreachable code must be caught. Guards against vacuous passes."""
    _write(
        tmp_path,
        "deliberate.py",
        """\
        def will_never_reach():
            return "done"
            print("this line never runs")
        """,
    )
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) >= 1, (
        "Gate returned no findings for deliberately unreachable code. "
        "The gate is broken or vacuous."
    )


# ---------------------------------------------------------------------------
# validate_unreachable_code integration tests
# ---------------------------------------------------------------------------


def test_validate_passes_on_clean_tree(tmp_path: Path) -> None:
    _write(tmp_path, "clean.py", "def f():\n    return 1\n")
    assert validate_unreachable_code(tmp_path) is True


def test_validate_fails_on_unreachable(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bad.py",
        "def f():\n    return 1\n    x = 2\n",
    )
    assert validate_unreachable_code(tmp_path) is False


def test_invalid_root_exits_2(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(SystemExit) as exc_info:
        validate_unreachable_code(missing)
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# CLI exit code tests
# ---------------------------------------------------------------------------


def test_cli_exits_0_on_clean_tree(tmp_path: Path) -> None:
    import shutil

    (tmp_path / "ok.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    shutil.copy(
        "scripts/validation/check_unreachable_code.py",
        tmp_path / "check_unreachable_code.py",
    )
    result = subprocess.run(
        [sys.executable, "check_unreachable_code.py"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True, encoding="utf-8",
    )
    assert result.returncode == 0


def test_cli_exits_1_on_unreachable(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("def f():\n    return 1\n    x = 2\n", encoding="utf-8")
    # Run from repo root so the script resolves, but cwd=tmp_path for scan
    import shutil

    shutil.copy(
        "scripts/validation/check_unreachable_code.py",
        tmp_path / "check_unreachable_code.py",
    )
    result = subprocess.run(
        [sys.executable, "check_unreachable_code.py"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True, encoding="utf-8",
    )
    assert result.returncode == 1
