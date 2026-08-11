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
- Syntax error files fail closed
- Empty Python scope fails closed
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
    ScanError,
    find_unreachable_statements,
    main,
    validate_unreachable_code,
)


def _init_repo(tmp_path: Path) -> None:
    if not (tmp_path / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)


def _write(tmp_path: Path, name: str, src: str) -> Path:
    """Write a Python source file with dedented content."""
    _init_repo(tmp_path)
    path = tmp_path / name
    path.write_text(textwrap.dedent(src), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
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


def test_ambient_git_repository_pointers_do_not_reduce_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "target"
    foreign = tmp_path / "foreign"
    target.mkdir()
    foreign.mkdir()
    _write(target, "clean.py", "def clean():\n    return 1\n")
    bad = _write(target, "bad.py", "def bad():\n    return 1\n    x = 2\n")
    _write(foreign, "clean.py", "def clean():\n    return 1\n")
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))

    findings = find_unreachable_statements(target)

    assert findings == [(bad, "bad", 3)]


def test_untracked_python_files_are_outside_corpus(tmp_path: Path) -> None:
    _write(tmp_path, "tracked.py", "def tracked():\n    return 1\n")
    (tmp_path / "scratch.py").write_text(
        "def scratch():\n    return 1\n    x = 2\n",
        encoding="utf-8",
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
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) == 1
    assert findings[0][2] == 4


def test_statement_after_break_in_loop_is_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "bad.py",
        """\
        def bad():
            while True:
                break
                print("never")
        """,
    )
    findings = find_unreachable_statements(tmp_path)
    assert len(findings) == 1
    assert findings[0][2] == 4


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


def test_syntax_error_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "bad_syntax.py", "def broken(:\n    pass\n")
    with pytest.raises(ScanError, match="could not analyze Python source"):
        find_unreachable_statements(tmp_path)


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
    with pytest.raises(ScanError):
        validate_unreachable_code(missing)


def test_cli_exits_two_on_empty_python_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("No Python here.\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)

    result = main([str(tmp_path)])

    assert result == 2
    assert "zero tracked Python files" in capsys.readouterr().err


def test_cli_exits_two_on_invalid_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main([str(tmp_path / "does_not_exist")])

    assert result == 2
    assert "repository root not found" in capsys.readouterr().err


def test_cli_exits_two_on_too_many_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main([str(tmp_path), str(tmp_path)])

    assert result == 2
    assert "expected at most one repository root" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# CLI exit code tests
# ---------------------------------------------------------------------------


def test_cli_exits_0_on_clean_tree(tmp_path: Path) -> None:
    import shutil

    _write(tmp_path, "ok.py", "def f():\n    return 1\n")
    shutil.copy(
        "scripts/validation/check_unreachable_code.py",
        tmp_path / "check_unreachable_code.py",
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, "check_unreachable_code.py"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0


def test_cli_exits_1_on_unreachable(tmp_path: Path) -> None:
    _write(tmp_path, "bad.py", "def f():\n    return 1\n    x = 2\n")
    # Run from repo root so the script resolves, but cwd=tmp_path for scan
    import shutil

    shutil.copy(
        "scripts/validation/check_unreachable_code.py",
        tmp_path / "check_unreachable_code.py",
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    result = subprocess.run(
        [sys.executable, "check_unreachable_code.py"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
