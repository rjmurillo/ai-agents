"""Tests for comprehensive main-binding detection in sole-fallback suppression.

Every Python binding form that creates ``main`` at module scope must suppress
the sole-fallback credit path.  Tests exercise the covered_stems/CLI gate.
"""

from __future__ import annotations

import pytest

from scripts.ci import cli_exit_contract_ratchet as ratchet

# Re-use the synthetic test infrastructure from the main ratchet test module.
from tests.ci.test_cli_exit_contract_ratchet import _arrange, _run

# ---------------------------------------------------------------------------
# Comprehensive binding-shape tests for _has_local_main_definition
# ---------------------------------------------------------------------------


class TestBindingShapeSoleSuppression:
    """Every Python binding form that binds ``main`` at module scope must
    suppress the sole-fallback credit path.

    Each test creates a synthetic script with ``def main`` and a test file
    that (a) introduces a specific binding form for ``main`` and (b) calls
    bare ``main()``.  Because the only credit path for bare ``main()`` in a
    single-stem test is sole, suppressing sole means the ratchet reports
    EXIT_REGRESSION (uncovered).

    Tests that should NOT suppress sole verify EXIT_OK.
    """

    @staticmethod
    def _script():
        return (
            "import sys\n"
            "def main(argv=None):\n"
            "    sys.exit(1)\n"
        )

    @staticmethod
    def _test_with_binding(binding_line):
        return (
            "from scripts.ci import widget\n"
            f"{binding_line}\n"
            "def test_exit():\n"
            "    try:\n"
            "        main([])\n"
            "    except SystemExit as e:\n"
            "        assert e.code != 0\n"
        )

    @pytest.mark.parametrize(
        "label,binding_line",
        [
            ("plain_assign", "main = lambda: None"),
            ("plain_assign_non_lambda", "main = print"),
            ("annotated_assign", "main: object = print"),
            ("augmented_assign", "main = 0\nmain += 1"),
            ("destructuring_tuple", "(_, main) = (1, print)"),
            ("destructuring_list", "[main, _] = [print, 1]"),
            ("starred_unpack", "*main, = [print]"),
            ("import_as", "import os as main"),
            ("from_import_as", "from os import path as main"),
            ("class_def_main", "class main:\n    pass"),
            ("del_after_nothing", "main = print\ndel main"),
            ("for_target", "for main in [1]:\n    pass"),
            ("with_target", "import contextlib\nwith contextlib.nullcontext() as main:\n    pass"),
            ("except_target", "try:\n    pass\nexcept Exception as main:\n    pass"),
            ("walrus", "_ = (main := print)"),
            ("if_guarded_def", "if True:\n    def main():\n        pass"),
            ("if_guarded_assign", "if True:\n    main = print"),
        ],
        ids=lambda x: x if isinstance(x, str) else "",
    )
    def test_binding_suppresses_sole(
        self, tmp_path, monkeypatch, label, binding_line
    ):
        _arrange(tmp_path, monkeypatch, self._script(), self._test_with_binding(binding_line))
        assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION

    @pytest.mark.parametrize(
        "label,binding_line",
        [
            ("class_method_main", "class Helper:\n    def main(self):\n        pass"),
            ("nested_def_main", "def wrapper():\n    def main():\n        pass"),
            ("reexport", "main = widget.main"),
            ("from_import_main", "from scripts.ci.widget import main"),
        ],
        ids=lambda x: x if isinstance(x, str) else "",
    )
    def test_non_binding_preserves_sole(
        self, tmp_path, monkeypatch, label, binding_line
    ):
        _arrange(tmp_path, monkeypatch, self._script(), self._test_with_binding(binding_line))
        assert _run(tmp_path, "0") == ratchet.EXIT_OK


class TestImportThenReassign:
    """Reassignment or deletion of main after a sole-eligible module import
    must suppress the sole credit path.

    Note: ``from X import main`` creates ``bare`` credit which is not affected
    by sole suppression.  These tests use only the module import (sole path).
    """

    @staticmethod
    def _script():
        return (
            "import sys\n"
            "def main(argv=None):\n"
            "    sys.exit(1)\n"
        )

    def test_module_import_then_reassign(self, tmp_path, monkeypatch):
        """Reassigning main after module import suppresses sole."""
        test_src = (
            "from scripts.ci import widget\n"
            "main = lambda: None\n"
            "def test_exit():\n"
            "    try:\n"
            "        main([])\n"
            "    except SystemExit as e:\n"
            "        assert e.code != 0\n"
        )
        _arrange(tmp_path, monkeypatch, self._script(), test_src)
        assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION

    def test_module_import_then_delete(self, tmp_path, monkeypatch):
        """Deleting main after module import suppresses sole."""
        test_src = (
            "from scripts.ci import widget\n"
            "main = print\n"
            "del main\n"
            "def test_exit():\n"
            "    try:\n"
            "        main([])\n"
            "    except SystemExit as e:\n"
            "        assert e.code != 0\n"
        )
        _arrange(tmp_path, monkeypatch, self._script(), test_src)
        assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION
