"""Platform-specific separator handling in expand_home.

Split out of tests/claude_mem/test_importer_resolution.py, which grew past the
500-line taste-lint ceiling. The seam is real: everything here is about what a
given platform counts as a path separator, which is the one behavior in this
module that differs by OS.

A backslash separates path segments on Windows and is an ordinary filename
character on POSIX, so the same argument means two different things. Both sides
are asserted from either platform by injecting the separator set, because a
skip-marked Windows test never runs on the Linux CI shards and would leave that
branch effectively uncovered. Two windows_path-marked tests additionally pin the
real, uninjected derivation on a Windows runner.
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


class TestSeparatorsArePlatformSpecific:
    """A backslash separates segments on Windows and names a file on POSIX.

    Both behaviors are asserted from either platform by injecting the separator
    set, because a skip-marked Windows test never runs on the Linux CI shards
    and would leave that branch effectively uncovered. The marked test below
    additionally pins the real derivation on a Windows runner.
    """

    POSIX = "/"
    WINDOWS = "\\/"

    @pytest.mark.parametrize(
        "raw",
        ["~\\importer.ts", "~\\\\importer.ts"],
        ids=["single-backslash", "double-backslash"],
    )
    def test_posix_keeps_a_backslash_name_literal(self, raw: str, tmp_path: Path) -> None:
        """On POSIX this is one relative filename, not a tilde path.

        Expanding it would rewrite a legal filename into a different path.
        """
        result = _import_mem.expand_home(raw, tmp_path, separators=self.POSIX)

        assert result == Path(raw)
        assert not result.is_absolute()
        assert tmp_path not in result.parents

    @pytest.mark.parametrize(
        "raw",
        ["~\\importer.ts", "~\\\\importer.ts", "~/\\importer.ts"],
        ids=["single-backslash", "double-backslash", "mixed"],
    )
    def test_windows_treats_backslash_as_a_separator(self, raw: str, tmp_path: Path) -> None:
        result = _import_mem.expand_home(raw, tmp_path, separators=self.WINDOWS)

        assert result == tmp_path / "importer.ts"

    def test_posix_mixed_separator_keeps_the_backslash_segment(self, tmp_path: Path) -> None:
        """`~/\\importer.ts` is a tilde path whose filename starts with a backslash."""
        result = _import_mem.expand_home("~/\\importer.ts", tmp_path, separators=self.POSIX)

        assert result == tmp_path / "\\importer.ts"

    def test_forward_slash_is_a_separator_on_both(self, tmp_path: Path) -> None:
        for seps in (self.POSIX, self.WINDOWS):
            assert (
                _import_mem.expand_home("~/importer.ts", tmp_path, separators=seps)
                == tmp_path / "importer.ts"
            )

    def test_path_separators_matches_the_stdlib(self) -> None:
        """The default set is derived from os.sep and os.altsep, not from os.name."""
        assert _import_mem.path_separators() == os.sep + (os.altsep or "")

    @pytest.mark.skipif(sys.platform == "win32", reason="Asserts POSIX separator semantics")
    def test_backslash_is_not_a_separator_on_a_posix_runner(self, tmp_path: Path) -> None:
        """Pin the real derivation on the shards that carry the bulk of CI."""
        assert _import_mem.expand_home("~\\importer.ts", tmp_path) == Path("~\\importer.ts")

    @pytest.mark.windows_path
    @pytest.mark.skipif(sys.platform != "win32", reason="Asserts Windows separator semantics")
    def test_backslash_is_a_separator_on_a_windows_runner(self, tmp_path: Path) -> None:
        """Pin the real derivation on the Windows runner, without injection."""
        assert _import_mem.expand_home("~\\importer.ts", tmp_path) == tmp_path / "importer.ts"

    @pytest.mark.windows_path
    @pytest.mark.skipif(sys.platform != "win32", reason="Asserts Windows separator semantics")
    def test_forward_slash_is_also_a_separator_on_a_windows_runner(self, tmp_path: Path) -> None:
        """The os.altsep half of the derivation, which only Windows can observe.

        On POSIX, `os.sep` alone equals `os.sep + (os.altsep or "")`, so dropping
        the altsep term is undetectable there. Windows is where that term does
        work: without it a forward-slash tilde path would stop expanding.
        """
        assert _import_mem.expand_home("~/importer.ts", tmp_path) == tmp_path / "importer.ts"

