"""Platform-specific path handling in expand_home.

Split out of tests/claude_mem/test_importer_resolution.py, which grew past the
500-line taste-lint ceiling. The seam is real: everything here is about what a
given platform counts as a path separator and as a drive, which is the one
behavior in this module that differs by OS.

Two things mean different things per platform. A backslash separates path
segments on Windows and is an ordinary filename character on POSIX. A leading
`D:` anchors to a drive on Windows and is an ordinary directory name on POSIX.
Both sides are asserted from either platform by injecting the standard-library
path module, because a skip-marked Windows test never runs on the Linux CI
shards and would leave that branch effectively uncovered. Several
windows_path-marked tests additionally pin the real, uninjected derivation on a
Windows runner.

The injected knob is the whole path module rather than a separator string
because separators and drives must be answered about the same platform. One knob
cannot pin a combination no platform has.
"""

from __future__ import annotations

import importlib.util
import ntpath
import os
import posixpath
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
    """A backslash separates segments on Windows and names a file on POSIX."""

    @pytest.mark.parametrize(
        "raw",
        ["~\\importer.ts", "~\\\\importer.ts"],
        ids=["single-backslash", "double-backslash"],
    )
    def test_posix_keeps_a_backslash_name_literal(self, raw: str, tmp_path: Path) -> None:
        """On POSIX this is one relative filename, not a tilde path.

        Expanding it would rewrite a legal filename into a different path.
        """
        result = _import_mem.expand_home(raw, tmp_path, pathmod=posixpath)

        assert result == Path(raw)
        assert not result.is_absolute()
        assert tmp_path not in result.parents

    @pytest.mark.parametrize(
        "raw",
        ["~\\importer.ts", "~\\\\importer.ts", "~/\\importer.ts"],
        ids=["single-backslash", "double-backslash", "mixed"],
    )
    def test_windows_treats_backslash_as_a_separator(self, raw: str, tmp_path: Path) -> None:
        result = _import_mem.expand_home(raw, tmp_path, pathmod=ntpath)

        assert result == tmp_path / "importer.ts"

    def test_posix_mixed_separator_keeps_the_backslash_segment(self, tmp_path: Path) -> None:
        """`~/\\importer.ts` is a tilde path whose filename starts with a backslash."""
        result = _import_mem.expand_home("~/\\importer.ts", tmp_path, pathmod=posixpath)

        assert result == tmp_path / "\\importer.ts"

    def test_forward_slash_is_a_separator_on_both(self, tmp_path: Path) -> None:
        for mod in (posixpath, ntpath):
            assert (
                _import_mem.expand_home("~/importer.ts", tmp_path, pathmod=mod)
                == tmp_path / "importer.ts"
            )

    def test_path_separators_matches_the_stdlib(self) -> None:
        """The default set is derived from the platform's path module, not os.name."""
        assert _import_mem.path_separators() == os.sep + (os.altsep or "")

    @pytest.mark.parametrize(
        ("mod", "expected"),
        [(posixpath, "/"), (ntpath, "\\/")],
        ids=["posix", "windows"],
    )
    def test_path_separators_answers_for_the_module_it_is_given(self, mod, expected: str) -> None:
        """Both platform answers, so neither is pinned only by the local runner."""
        assert _import_mem.path_separators(mod) == expected

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
        """The altsep half of the derivation, which only Windows can observe.

        On POSIX, `sep` alone equals `sep + (altsep or "")`, so dropping the
        altsep term is undetectable there. Windows is where that term does work:
        without it a forward-slash tilde path would stop expanding.
        """
        assert _import_mem.expand_home("~/importer.ts", tmp_path) == tmp_path / "importer.ts"


class TestDriveAnchoredSuffixIsNotExpanded:
    """A suffix carrying a drive is anchored elsewhere, so it is left literal.

    Stripping leading separators does not make a suffix relative on Windows. A
    drive is a second anchoring mechanism, and joining a drive-anchored suffix
    onto `home` discards `home` exactly as a rooted suffix does. On POSIX the
    same text carries no drive, so `D:` stays an ordinary directory name and the
    path expands normally. That asymmetry is the point of this class.
    """

    @pytest.mark.parametrize(
        "raw",
        ["~/D:/importer.ts", "~\\D:\\importer.ts", "~/D:importer.ts"],
        ids=["absolute-other-drive", "backslash-other-drive", "drive-relative"],
    )
    def test_windows_leaves_a_drive_anchored_suffix_literal(
        self, raw: str, tmp_path: Path
    ) -> None:
        result = _import_mem.expand_home(raw, tmp_path, pathmod=ntpath)

        assert result == Path(raw)
        assert ntpath.splitdrive(str(result))[0] == "", "expansion must not anchor to a drive"

    def test_posix_treats_a_drive_letter_as_an_ordinary_directory(self, tmp_path: Path) -> None:
        """No drives on POSIX, so `D:` is just a directory name under home."""
        result = _import_mem.expand_home("~/D:/importer.ts", tmp_path, pathmod=posixpath)

        assert result == tmp_path / "D:" / "importer.ts"

    def test_windows_inherits_splitdrive_permissiveness(self, tmp_path: Path) -> None:
        """`ntpath` calls any single character before a colon a drive, and so does this.

        No drive `1:` can exist, so this is over-rejection. It is the safe
        direction: a wrongly-anchored suffix returned literally fails the
        caller's existence check, while a wrongly expanded one would resolve
        somewhere the caller never named.
        """
        assert ntpath.splitdrive("1:x")[0] == "1:", "premise: ntpath calls this a drive"

        assert _import_mem.expand_home("~/1:x", tmp_path, pathmod=ntpath) == Path("~/1:x")

    def test_windows_still_expands_a_suffix_with_no_drive(self, tmp_path: Path) -> None:
        """The guard rejects drive anchoring only, not every Windows suffix."""
        result = _import_mem.expand_home("~/sub/importer.ts", tmp_path, pathmod=ntpath)

        assert result == tmp_path / "sub" / "importer.ts"

    @pytest.mark.windows_path
    @pytest.mark.skipif(sys.platform != "win32", reason="Asserts Windows drive semantics")
    def test_drive_anchored_suffix_stays_literal_on_a_windows_runner(
        self, tmp_path: Path
    ) -> None:
        """Pin the real derivation: home must survive a drive-anchored suffix."""
        result = _import_mem.expand_home("~/D:/importer.ts", tmp_path)

        assert result == Path("~/D:/importer.ts")
        assert result.drive == "", "expansion must not anchor to a drive"
