"""The main() entry-point integration tests for the Claude-Mem importer.

Split out of tests/claude_mem/test_importer_resolution.py at the 500-line
taste-lint ceiling. The seam is real: everything here drives `main()`
end-to-end (argv, exit codes, subprocess wiring, memories-dir creation),
distinct from resolve_importer()'s own precedence/blank/tilde contract
tested in that module.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
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


# Pinned independently of the implementation. Deriving this by calling
# claude_default_importer() would make the fixture and the assertions share one
# derivation, so a default that moved to the wrong location would move both
# together and every test below would stay green.
_CLAUDE_DEFAULT_SUFFIX = Path(".claude/plugins/marketplaces/thedotmack/scripts/import-memories.ts")


def _make_claude_default(home: Path) -> Path:
    """Create the Claude Code plugin importer under a fake home."""
    importer = home / _CLAUDE_DEFAULT_SUFFIX
    importer.parent.mkdir(parents=True, exist_ok=True)
    importer.write_text("// stub importer", encoding="utf-8")
    return importer


class TestImportMemoriesMain:
    def test_exits_0_and_skips_when_optional_plugin_absent(self, tmp_path: Path, capsys) -> None:
        result = _import_mem.main([], env={}, home=tmp_path / "empty-home")

        assert result == 0
        assert "SKIP" in capsys.readouterr().out

    def test_defaults_the_environment_to_the_real_process_environment(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        # env is omitted here, unlike every other case in this file, so this
        # only passes if main() actually reads os.environ rather than a test
        # double every other test supplies explicitly.
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        monkeypatch.setenv(_import_mem.IMPORTER_ENV_VAR, str(importer))
        memories = tmp_path / "memories"
        memories.mkdir()
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        result = _import_mem.main([], home=tmp_path)

        assert result == 0
        # Reaching the empty-memories-dir message (rather than SKIP) proves
        # the real environment variable was actually read and resolved.
        assert "No memory files to import from" in capsys.readouterr().out

    def test_defaults_home_to_the_real_process_home(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        # home is omitted here, unlike every other case in this file, so this
        # only passes if main() actually reads Path.home() rather than a test
        # double every other test supplies explicitly.
        monkeypatch.delenv(_import_mem.IMPORTER_ENV_VAR, raising=False)
        process_home = tmp_path / "process-home"
        process_home.mkdir()
        _make_claude_default(process_home)
        monkeypatch.setenv("HOME", str(process_home))
        monkeypatch.setenv("USERPROFILE", str(process_home))
        memories = tmp_path / "memories"
        memories.mkdir()
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        result = _import_mem.main([], env={})

        assert result == 0
        # Reaching the empty-memories-dir message (rather than SKIP) proves
        # the real process home was actually read and the default found.
        assert "No memory files to import from" in capsys.readouterr().out

    def test_exits_1_when_explicit_importer_does_not_exist(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing-importer.ts"

        result = _import_mem.main(["--importer", str(missing)], env={}, home=tmp_path)

        assert result == 1

    def test_exits_1_when_configured_environment_importer_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        env = {_import_mem.IMPORTER_ENV_VAR: str(tmp_path / "missing-importer.ts")}

        result = _import_mem.main([], env=env, home=tmp_path)

        assert result == 1

    def test_exits_1_when_configured_importer_is_a_directory(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # exists() is true for a directory too. A misconfigured --importer (or
        # an upstream marketplace layout change) that names a directory must
        # be rejected by the guard, never handed to tsx as an argument.
        importer_dir = tmp_path / "importer.ts"
        importer_dir.mkdir()
        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        calls = []

        def _record_call(*args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr(_import_mem.subprocess, "run", _record_call)

        result = _import_mem.main(["--importer", str(importer_dir)], env={}, home=tmp_path)

        assert result == 1
        assert calls == []

    def test_exits_1_when_configured_importer_fails(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        monkeypatch.setattr(
            _import_mem.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 3, "", "boom"),
        )

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 1

    def test_exits_0_when_configured_importer_succeeds(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        monkeypatch.setattr(
            _import_mem.subprocess,
            "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, "", ""),
        )

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0

    def test_exits_0_when_no_memory_files_present(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0

    def test_creates_the_memories_dir_when_it_is_absent(self, tmp_path: Path, monkeypatch) -> None:
        """The absent-directory branch, which the empty-directory case never reaches."""
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)
        assert not memories.exists()

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0
        assert memories.is_dir()

    def test_creates_nested_memories_dir_when_parents_are_absent(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """parents=True is load-bearing: the parent may not exist either."""
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "absent-parent" / "memories"
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 0
        assert memories.is_dir()

    @pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
    def test_exits_1_when_explicit_argument_is_blank(self, blank: str, tmp_path: Path) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)
        env = {_import_mem.IMPORTER_ENV_VAR: str(_make_claude_default(tmp_path / "other"))}

        result = _import_mem.main(["--importer", blank], env=env, home=home)

        # A usable env value and a usable default both exist; the blank argument
        # must still fail rather than fall through to either of them.
        assert result == 1

    def test_exits_1_when_importer_binary_is_unavailable(self, tmp_path: Path, monkeypatch) -> None:
        importer = tmp_path / "importer.ts"
        importer.write_text("// stub importer", encoding="utf-8")
        memories = tmp_path / "memories"
        memories.mkdir()
        (memories / "shared.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(_import_mem, "_MEMORIES_DIR", memories)

        def _raise(*_args, **_kwargs):
            raise FileNotFoundError("npx not on PATH")

        monkeypatch.setattr(_import_mem.subprocess, "run", _raise)

        result = _import_mem.main(["--importer", str(importer)], env={}, home=tmp_path)

        assert result == 1
