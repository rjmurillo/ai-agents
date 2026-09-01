"""The CLI boundary of .claude-mem/scripts/import_claude_mem_memories.py.

Split out of tests/claude_mem/test_importer_resolution.py at the 500-line
taste-lint ceiling. The seam is real: everything here is about what argparse
does with a command line before `main` reaches its own resolution contract,
which is a different owner and a different exit code from everything in that
module.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Import the module under test by file path since it lives outside scripts/.

_base = os.path.join(os.path.dirname(__file__), "..", "..", ".claude-mem", "scripts")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_base, filename))
    assert spec is not None, f"Failed to find {filename}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, f"Module spec for {filename} has no loader"
    # dataclasses resolves a class's module through sys.modules, so a module
    # executed without registration raises AttributeError at class creation.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_import_mem = _load("import_claude_mem_memories", "import_claude_mem_memories.py")


class TestMalformedCommandLineExits2:
    """argparse owns the usage-error code, and it is 2, not 1.

    `parse_args` raises SystemExit(2) before `main` reaches its own contract, and
    the entrypoint's `sys.exit(main())` propagates it, so exit 2 is a real third
    state of this CLI. The module docstring documents it; these tests pin it so
    the prose cannot drift from the behavior again.

    This is not the import contract. Exit 2 is reachable only when the caller's
    command line is wrong, never as an outcome of an import.
    """

    @pytest.mark.parametrize(
        "argv",
        [["--importer"], ["--bogus"], ["unexpected-positional"]],
        ids=["flag-without-value", "unknown-flag", "unexpected-positional"],
    )
    def test_malformed_argv_exits_2(self, argv: list[str], tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as caught:
            _import_mem.main(argv, env={}, home=tmp_path)

        assert caught.value.code == 2

    def test_help_exits_0(self, tmp_path: Path) -> None:
        """`--help` is a successful invocation, not a usage error."""
        with pytest.raises(SystemExit) as caught:
            _import_mem.main(["--help"], env={}, home=tmp_path)

        assert caught.value.code == 0

    def test_a_blank_importer_value_is_not_a_usage_error(self, tmp_path: Path) -> None:
        """`--importer ""` parses fine, so it reaches the exit-1 resolution contract.

        The distinction this pins: argparse rejects a MISSING value with 2, while
        a value that is present and blank is a resolution failure and stays 1.
        """
        result = _import_mem.main(["--importer", ""], env={}, home=tmp_path)

        assert result == 1
