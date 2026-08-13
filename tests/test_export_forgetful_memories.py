"""Tests for scripts.forgetful.export_forgetful_memories module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.forgetful.export_forgetful_memories import (
    TABLE_MAPPING,
    _run_security_review_forgetful,
    export_table,
    run_sqlite3,
    validate_output_path,
)


class TestValidateOutputPath:
    def test_accepts_valid_path(self, tmp_path: Path) -> None:
        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()
        output = exports_dir / "backup.json"
        assert validate_output_path(output, exports_dir) is True

    def test_rejects_traversal(self, tmp_path: Path) -> None:
        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()
        output = tmp_path / "outside.json"
        assert validate_output_path(output, exports_dir) is False

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        exports_dir = tmp_path / "exports"
        exports_dir.mkdir()
        output = exports_dir / ".." / "escape.json"
        assert validate_output_path(output, exports_dir) is False


class TestTableMapping:
    def test_all_groups_have_tables(self) -> None:
        for group, tables in TABLE_MAPPING.items():
            assert len(tables) > 0, f"Group {group} has no tables"

    def test_memories_group_includes_memory_links(self) -> None:
        assert "memory_links" in TABLE_MAPPING["memories"]

    def test_associations_group(self) -> None:
        assoc = TABLE_MAPPING["associations"]
        assert all("association" in t for t in assoc)


class TestRunSqlite3:
    def _make_result(
        self, returncode: int = 0, stdout: str = "", stderr: str = "",
    ) -> object:
        return type(
            "R", (), {"returncode": returncode, "stderr": stderr, "stdout": stdout},
        )()

    def test_raises_on_failure_with_stderr(self) -> None:
        mock = self._make_result(1, stderr="database is locked\n")
        with patch("subprocess.run", return_value=mock):
            with pytest.raises(RuntimeError, match="database is locked"):
                run_sqlite3("/fake/db", "SELECT 1")

    def test_raises_on_failure_with_empty_stderr(self) -> None:
        with patch("subprocess.run", return_value=self._make_result(1)):
            with pytest.raises(RuntimeError, match="sqlite3 failed"):
                run_sqlite3("/fake/db", "SELECT 1")

    def test_returns_stdout_on_success(self) -> None:
        with patch("subprocess.run", return_value=self._make_result(0, stdout="hello")):
            result = run_sqlite3("/fake/db", "SELECT 1")
        assert result == "hello"


class TestRunSecurityReviewForgetful:
    def test_missing_scanner_fails_closed(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        export_file = tmp_path / "clean.json"
        with patch(
            "scripts.forgetful.export_forgetful_memories._SCRIPT_DIR",
            tmp_path / "forgetful",
        ):
            assert _run_security_review_forgetful(export_file) == 1
        assert "Security review script not found" in capsys.readouterr().err

    @pytest.mark.parametrize("filename", ["clean.json", "memory export.json"])
    def test_clean_export_passes_real_cli_boundary(
        self,
        tmp_path: Path,
        filename: str,
    ) -> None:
        export_file = tmp_path / filename
        export_file.write_text('{"data": "safe content"}', encoding="utf-8")

        assert _run_security_review_forgetful(export_file) == 0

    def test_dash_leading_relative_path_passes_real_cli_boundary(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        export_file = Path("-dash-leading.json")
        export_file.write_text('{"data": "safe content"}', encoding="utf-8")

        assert _run_security_review_forgetful(export_file) == 0

    def test_sensitive_export_fails_real_cli_boundary(
        self,
        tmp_path: Path,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        export_file = tmp_path / "sensitive.json"
        export_file.write_text('{"api_key": "placeholder"}', encoding="utf-8")

        assert _run_security_review_forgetful(export_file) == 1
        assert "WARNING - Sensitive data patterns detected!" in capfd.readouterr().out


class TestExportTable:
    def test_raises_on_json_parse_error(self) -> None:
        """export_table raises RuntimeError on JSONDecodeError."""
        with (
            patch(
                "scripts.forgetful.export_forgetful_memories.get_table_columns",
                return_value=["id", "name"],
            ),
            patch(
                "scripts.forgetful.export_forgetful_memories.run_sqlite3",
                return_value="not valid json{{{",
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to parse JSON"):
                export_table("/fake/db", "memories")
