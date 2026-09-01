"""Tests for .claude-mem/scripts/ memory export/import scripts."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Import modules under test by file path since they live outside scripts/

_base = os.path.join(os.path.dirname(__file__), "..", ".claude-mem", "scripts")


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


_export_direct = _load("export_claude_mem_direct", "export_claude_mem_direct.py")
_export_memories = _load("export_claude_mem_memories", "export_claude_mem_memories.py")
_export_backup = _load("export_claude_mem_full_backup", "export_claude_mem_full_backup.py")
_import_mem = _load("import_claude_mem_memories", "import_claude_mem_memories.py")


class TestExportDirectValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / "export.json"
        assert _export_direct.validate_output_path(output, mem_dir) is True

    def test_rejects_traversal(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = tmp_path / "escape.json"
        assert _export_direct.validate_output_path(output, mem_dir) is False


class TestExportDirectGetCount:
    @pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 binary not installed")
    def test_returns_negative_on_error(self, tmp_path: Path) -> None:
        # A directory is unopenable as a database, so the CLI fails at open in
        # every sqlite3 version. A nonexistent file path does not error here:
        # the shell creates the database lazily and "SELECT 1;" touches no
        # table, so sqlite3 exits 0 and get_count returns 1.
        result = _export_direct.get_count(str(tmp_path), "SELECT 1;")
        assert result == -1

    @pytest.mark.skipif(shutil.which("sqlite3") is None, reason="sqlite3 binary not installed")
    def test_returns_negative_on_non_numeric_output(self, tmp_path: Path) -> None:
        db = tmp_path / "real.db"
        result = _export_direct.get_count(str(db), "SELECT 'not-a-number';")
        assert result == -1


class TestExportMemoriesValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / "export.json"
        assert _export_memories.validate_output_path(output, mem_dir) is True

    def test_rejects_traversal(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = tmp_path / "escape.json"
        assert _export_memories.validate_output_path(output, mem_dir) is False


class TestExportBackupValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / "backup.json"
        assert _export_backup.validate_output_path(output, mem_dir) is True

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        mem_dir = tmp_path / "memories"
        mem_dir.mkdir()
        output = mem_dir / ".." / "escape.json"
        assert _export_backup.validate_output_path(output, mem_dir) is False


class TestSecurityReviewBoundary:
    @pytest.mark.parametrize(
        ("module", "runner_name"),
        [
            (_export_direct, "_run_security_review_direct"),
            (_export_memories, "_run_security_review_memories"),
            (_export_backup, "_run_security_review"),
        ],
        ids=["direct", "memories", "full-backup"],
    )
    def test_passes_export_path_positionally(
        self,
        module: object,
        runner_name: str,
        tmp_path: Path,
    ) -> None:
        export_file = tmp_path / "memory export.json"
        export_file.write_text('{"data": "safe content"}', encoding="utf-8")

        runner = getattr(module, runner_name)

        assert runner(export_file) == 0


class TestExportDirectMain:
    def test_exits_1_when_sqlite3_missing(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda x: None)
        result = _export_direct.main(["--project", "test"])
        assert result == 1


class TestExportMemoriesMain:
    def test_exits_1_with_invalid_query(self) -> None:
        result = _export_memories.main(["query with $pecial; chars"])
        assert result == 1


def _make_claude_default(home: Path) -> Path:
    """Create the Claude Code plugin importer under a fake home."""
    importer = _import_mem.claude_default_importer(home)
    importer.parent.mkdir(parents=True, exist_ok=True)
    importer.write_text("// stub importer", encoding="utf-8")
    return importer


class TestResolveImporter:
    def test_uses_claude_plugin_default_when_nothing_configured(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        expected = _make_claude_default(home)

        resolution = _import_mem.resolve_importer(None, {}, home)

        assert resolution.path == expected
        assert resolution.is_configured is False

    def test_explicit_argument_outranks_environment_and_default(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)
        explicit = tmp_path / "explicit.ts"
        env = {_import_mem.IMPORTER_ENV_VAR: str(tmp_path / "from-env.ts")}

        resolution = _import_mem.resolve_importer(str(explicit), env, home)

        assert resolution.path == explicit
        assert resolution.is_configured is True

    def test_environment_outranks_default(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        _make_claude_default(home)
        from_env = tmp_path / "from-env.ts"
        env = {_import_mem.IMPORTER_ENV_VAR: str(from_env)}

        resolution = _import_mem.resolve_importer(None, env, home)

        assert resolution.path == from_env
        assert resolution.is_configured is True

    @pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "whitespace"])
    def test_blank_environment_value_falls_through_to_default(
        self, blank: str, tmp_path: Path
    ) -> None:
        home = tmp_path / "home"
        expected = _make_claude_default(home)
        env = {_import_mem.IMPORTER_ENV_VAR: blank}

        resolution = _import_mem.resolve_importer(None, env, home)

        assert resolution.path == expected
        assert resolution.is_configured is False

    def test_expands_tilde_in_explicit_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        resolution = _import_mem.resolve_importer("~/importer.ts", {}, tmp_path)

        assert resolution.path == Path(tmp_path / "importer.ts")

    def test_reports_unset_when_plugin_absent(self, tmp_path: Path) -> None:
        resolution = _import_mem.resolve_importer(None, {}, tmp_path / "empty-home")

        assert resolution.path is None
        assert resolution.is_configured is False


class TestImportMemoriesMain:
    def test_exits_0_and_skips_when_optional_plugin_absent(self, tmp_path: Path, capsys) -> None:
        result = _import_mem.main([], env={}, home=tmp_path / "empty-home")

        assert result == 0
        assert "SKIP" in capsys.readouterr().out

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
