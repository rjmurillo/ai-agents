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
from types import SimpleNamespace

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


class TestDashPrefixedImporterCannotBecomeAFlag:
    """A relative importer whose name starts with a dash must not reach tsx as one.

    `tsx` parses a leading dash as a flag, and both configured tiers accept a
    relative path the caller chose. A file named `--experimental-foo` is a legal
    POSIX filename and passes the existence check, so passing the name through
    unchanged would hand tsx a flag instead of a script: the configured importer
    silently never runs and the exit code still reports success.

    The fix is to make the argv entry absolute, which no dash can lead. These
    assert on recorded argv, because every other subprocess stub ignores it.
    """

    @staticmethod
    def _record(monkeypatch) -> list[list[str]]:
        calls: list[list[str]] = []

        def _fake_run(argv, **_kwargs):
            calls.append(list(argv))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(_import_mem.subprocess, "run", _fake_run)
        return calls

    @staticmethod
    def _stage(tmp_path: Path, monkeypatch, name: str) -> Path:
        importer = tmp_path / name
        importer.write_text("// stub importer", encoding="utf-8")

        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        # The defect only exists for a RELATIVE path, so run from tmp_path and
        # configure the bare name.
        monkeypatch.chdir(tmp_path)
        return importer

    @pytest.mark.parametrize(
        "name",
        ["--experimental-foo", "--help", "-r"],
        ids=["long-flag-lookalike", "help-lookalike", "short-flag-lookalike"],
    )
    def test_dash_named_importer_reaches_argv_as_an_absolute_path(
        self, name: str, tmp_path: Path, monkeypatch
    ) -> None:
        importer = self._stage(tmp_path, monkeypatch, name)
        calls = self._record(monkeypatch)

        assert _import_mem.main([f"--importer={name}"], env={}, home=tmp_path) == 0

        argv = calls[0]
        assert argv[2] == os.path.abspath(importer), "tsx must receive the absolute path"
        assert not argv[2].startswith("-"), "an argv entry starting with a dash is a flag"

    def test_the_same_holds_for_the_environment_tier(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        importer = self._stage(tmp_path, monkeypatch, "--experimental-foo")
        calls = self._record(monkeypatch)
        env = {_import_mem.IMPORTER_ENV_VAR: "--experimental-foo"}

        assert _import_mem.main([], env=env, home=tmp_path) == 0

        assert calls[0][2] == os.path.abspath(importer)
        assert not calls[0][2].startswith("-")

    def test_a_symlinked_importer_keeps_the_directory_the_caller_named(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Absolute, not resolved. The importer may locate its imports relative to itself.

        `Path.resolve()` would also defeat the dash but would report the symlink
        target's directory, changing the script's own base directory. Package
        managers install plugin trees behind symlinks, so this is a live case.
        """
        real = tmp_path / "real"
        real.mkdir()
        (real / "importer.ts").write_text("// stub importer", encoding="utf-8")
        (tmp_path / "linked").symlink_to(real, target_is_directory=True)

        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        calls = self._record(monkeypatch)

        linked = tmp_path / "linked" / "importer.ts"
        assert _import_mem.main(["--importer", str(linked)], env={}, home=tmp_path) == 0

        assert calls[0][2] == str(linked), "the caller's own path, made absolute"
        assert calls[0][2] != str(linked.resolve()), "resolve() would have collapsed it"
