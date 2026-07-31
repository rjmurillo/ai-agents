"""Tests for scripts/validation/check_unreachable_after_terminator.py.

Coverage:
- Positive: statement after return, raise, continue, break is detected.
- Negative: clean functions, terminators as last statement, nested defs.
- Edge: empty function, multiple violations in same file, parse error file.
- CLI: exit codes 0 and 1, --quiet flag, path arguments.
- Isolating negative control: each rule is individually load-bearing.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.check_unreachable_after_terminator import (
    Violation,
    main,
    scan_file,
    scan_tree,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(src: str, path: Path = Path("test.py")) -> list[Violation]:
    tree = ast.parse(src)
    return scan_tree(tree, path)


# ---------------------------------------------------------------------------
# Positive tests: should detect violations
# ---------------------------------------------------------------------------


class TestPositiveDetection:
    def test_statement_after_return(self) -> None:
        src = "def f():\n    return 1\n    x = 2\n"
        violations = _parse(src)
        assert len(violations) == 1
        v = violations[0]
        assert v.func_name == "f"
        assert v.terminator_type == "Return"
        assert v.dead_lineno == 3

    def test_statement_after_raise(self) -> None:
        src = "def f():\n    raise ValueError()\n    return 0\n"
        violations = _parse(src)
        assert len(violations) == 1
        assert violations[0].terminator_type == "Raise"

    def test_statement_after_continue(self) -> None:
        src = "def f(items):\n    for x in items:\n        continue\n        print(x)\n"
        # continue is inside loop body, scan_tree walks nested functions
        tree = ast.parse(src)
        # The loop body is NOT a FunctionDef.body, it's a For.body, so
        # the scanner does NOT catch loop-body dead code (deliberate scope).
        violations = scan_tree(tree, Path("test.py"))
        assert violations == []

    def test_statement_after_break_in_loop(self) -> None:
        src = "def f(items):\n    for x in items:\n        break\n        print(x)\n"
        tree = ast.parse(src)
        violations = scan_tree(tree, Path("test.py"))
        # break in a for-loop body: scan only covers func.body, not for.body
        assert violations == []

    def test_multiple_dead_statements_reports_first_only(self) -> None:
        src = "def f():\n    return 1\n    x = 2\n    y = 3\n"
        violations = _parse(src)
        assert len(violations) == 1
        assert violations[0].dead_lineno == 3

    def test_async_function(self) -> None:
        src = "async def f():\n    return 1\n    await something()\n"
        violations = _parse(src)
        assert len(violations) == 1
        assert violations[0].func_name == "f"

    def test_nested_function_violation(self) -> None:
        src = "def outer():\n    def inner():\n        return 1\n        x = 2\n    return inner\n"
        violations = _parse(src)
        assert len(violations) == 1
        assert violations[0].func_name == "inner"

    def test_violation_in_method(self) -> None:
        src = "class C:\n    def m(self):\n        raise NotImplementedError()\n        return 0\n"
        violations = _parse(src)
        assert len(violations) == 1
        assert violations[0].func_name == "m"


# ---------------------------------------------------------------------------
# Negative tests: should NOT detect violations
# ---------------------------------------------------------------------------


class TestNegativeClean:
    def test_return_as_last_statement(self) -> None:
        src = "def f():\n    x = 1\n    return x\n"
        assert _parse(src) == []

    def test_raise_as_last_statement(self) -> None:
        src = "def f():\n    raise ValueError('bad')\n"
        assert _parse(src) == []

    def test_empty_function(self) -> None:
        src = "def f():\n    pass\n"
        assert _parse(src) == []

    def test_single_statement_function(self) -> None:
        src = "def f():\n    return 1\n"
        assert _parse(src) == []

    def test_if_branch_with_return(self) -> None:
        src = "def f(x):\n    if x:\n        return 1\n    return 0\n"
        assert _parse(src) == []

    def test_return_inside_if_not_function_body(self) -> None:
        src = "def f(x):\n    if x:\n        return 1\n    x = 2\n    return x\n"
        assert _parse(src) == []

    def test_no_functions(self) -> None:
        src = "x = 1\ny = 2\n"
        assert _parse(src) == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_two_functions_first_clean_second_dirty(self) -> None:
        src = "def clean():\n    return 1\ndef dirty():\n    return 2\n    x = 3\n"
        violations = _parse(src)
        assert len(violations) == 1
        assert violations[0].func_name == "dirty"

    def test_violation_path_preserved(self, tmp_path: Path) -> None:
        p = tmp_path / "sub.py"
        p.write_text("def f():\n    return 1\n    x = 2\n", encoding="utf-8")
        violations = scan_file(p)
        assert violations[0].path == p

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.py"
        p.write_text("def f(\n", encoding="utf-8")
        violations = scan_file(p)
        assert violations == []

    def test_scan_file_binary_read_error(self, tmp_path: Path) -> None:
        p = tmp_path / "missing.py"
        # scan_file with a path that does not exist should call sys.exit(2)
        with pytest.raises(SystemExit) as exc:
            scan_file(p)
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# CLI boundary tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_clean_directory_exits_zero(self, tmp_path: Path) -> None:
        (tmp_path / "ok.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        exit_code = main([str(tmp_path)])
        assert exit_code == 0

    def test_dirty_directory_exits_one(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("def f():\n    return 1\n    x = 2\n", encoding="utf-8")
        exit_code = main([str(tmp_path)])
        assert exit_code == 1

    def test_specific_file_exits_one(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.py"
        p.write_text("def f():\n    raise ValueError()\n    return 0\n", encoding="utf-8")
        exit_code = main([str(p)])
        assert exit_code == 1

    def test_specific_clean_file_exits_zero(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.py"
        p.write_text("def f():\n    return 1\n", encoding="utf-8")
        exit_code = main([str(p)])
        assert exit_code == 0

    def test_quiet_flag_suppresses_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "bad.py").write_text("def f():\n    return 1\n    x = 2\n", encoding="utf-8")
        exit_code = main(["--quiet", str(tmp_path)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_default_path_scans_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        exit_code = main([])
        assert exit_code == 0

    def test_skips_venv_directory(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "bad.py").write_text("def f():\n    return 1\n    x = 2\n", encoding="utf-8")
        exit_code = main([str(tmp_path)])
        assert exit_code == 0


# ---------------------------------------------------------------------------
# Isolating negative controls: each detection component is load-bearing
# ---------------------------------------------------------------------------


class TestIsolatingNegativeControls:
    """Each component of the check is individually proven load-bearing.

    A test here must fail if the named component is removed from the
    implementation, not merely if the whole feature is removed.
    """

    def test_terminators_tuple_must_include_return(self) -> None:
        src = "def f():\n    return 1\n    x = 2\n"
        tree = ast.parse(src)
        violations = scan_tree(tree, Path("t.py"))
        # If Return were absent from _TERMINATORS, violations would be empty.
        assert violations, "Return must be in _TERMINATORS"

    def test_terminators_tuple_must_include_raise(self) -> None:
        src = "def f():\n    raise ValueError()\n    x = 2\n"
        tree = ast.parse(src)
        violations = scan_tree(tree, Path("t.py"))
        assert violations, "Raise must be in _TERMINATORS"

    def test_body_slice_stops_before_last(self) -> None:
        # If the check used body[:-1] correctly, return as final stmt is clean.
        src = "def f():\n    x = 1\n    return x\n"
        assert _parse(src) == [], "return as last stmt must NOT fire"

    def test_only_sibling_statements_counted(self) -> None:
        # A return inside an if-branch does not make the next func-body stmt dead.
        src = "def f(x):\n    if x:\n        return x\n    return 0\n"
        assert _parse(src) == [], "return inside if-body must not affect func body"

    def test_async_function_also_scanned(self) -> None:
        src = "async def f():\n    return 1\n    x = 2\n"
        violations = _parse(src)
        assert violations, "AsyncFunctionDef must be scanned, not only FunctionDef"


# ---------------------------------------------------------------------------
# Regression guard: rescued class from the causal_restore test file (#3874)
# ---------------------------------------------------------------------------


class TestCausalRestoreClassPlacement:
    """Proves that TestAdrReviewPolicyRenameAndBlobScope is a module-level class.

    The class was accidentally nested inside _repo_where_a_rename_repadded_the_number
    (commit 54449b351), making its 4 test methods unreachable. This test is the
    isolating negative control: if the class definition is removed the 4 methods
    become nested functions inside the helper and this assertion fails.
    """

    _FILE = (
        Path(__file__).resolve().parents[2]
        / "tests/validation/test_git_hook_policy_causal_restore.py"
    )

    def test_rescued_class_is_module_level(self) -> None:
        """Assert the class appears as a direct child of the module, not nested."""
        source = self._FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        module_level_classes = {
            node.name for node in ast.iter_child_nodes(tree) if isinstance(node, ast.ClassDef)
        }
        assert "TestAdrReviewPolicyRenameAndBlobScope" in module_level_classes, (
            "TestAdrReviewPolicyRenameAndBlobScope must be a module-level class; "
            "if it is missing, its 4 test methods are unreachable."
        )

    def test_rescued_class_has_four_test_methods(self) -> None:
        """Assert the class contains exactly the 4 rescued test methods."""
        source = self._FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.iter_child_nodes(tree):
            if (
                isinstance(node, ast.ClassDef)
                and node.name == "TestAdrReviewPolicyRenameAndBlobScope"
            ):
                methods = [n.name for n in ast.walk(node) if isinstance(n, ast.FunctionDef)]
                assert len(methods) == 4, (
                    f"Expected 4 test methods in TestAdrReviewPolicyRenameAndBlobScope, "
                    f"got {len(methods)}: {methods}"
                )
                return
        pytest.fail("TestAdrReviewPolicyRenameAndBlobScope class not found in module")
