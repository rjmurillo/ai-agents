"""Tests for get_codeql_diagnostics.py CodeQL diagnostics script."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_spec = importlib.util.spec_from_file_location(
    "get_codeql_diagnostics",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".codeql",
        "scripts",
        "get_codeql_diagnostics.py",
    ),
)
assert _spec is not None, "Failed to find get_codeql_diagnostics.py"
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None, "Module spec has no loader"
_spec.loader.exec_module(_mod)

build_parser = _mod.build_parser
check_cli = _mod.check_cli
check_config = _mod.check_config
check_database = _mod.check_database
check_database_cache = _mod.check_database_cache
check_results = _mod.check_results
main = _mod.main


class TestBuildParser:
    def test_default_values(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.repo_path == "."
        assert args.output_format == "console"

    def test_json_format(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--output-format", "json"])
        assert args.output_format == "json"

    def test_markdown_format(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--output-format", "markdown"])
        assert args.output_format == "markdown"


class TestCheckCli:
    def test_cli_not_found(self) -> None:
        with (
            patch("shutil.which", return_value=None),
            patch.object(Path, "exists", return_value=False),
        ):
            result = check_cli()
            assert result["installed"] is False
            assert len(result["recommendations"]) > 0

    def test_cli_found_in_path(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/codeql"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(
                returncode=0, stdout="CodeQL command-line toolchain release 2.23.9\n",
            )
            result = check_cli()
            assert result["installed"] is True
            assert result["path"] == "/usr/bin/codeql"
            assert "2.23.9" in result["version"]


class TestCheckConfig:
    def test_config_not_found(self) -> None:
        result = check_config("/nonexistent/config.yml", None)
        assert result["exists"] is False
        assert len(result["recommendations"]) > 0

    def test_valid_config(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("name: test\npacks:\n  - codeql/python-queries\n")
        result = check_config(str(config), None)
        assert result["exists"] is True
        assert result["valid_yaml"] is True

    def test_empty_config(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("")
        result = check_config(str(config), None)
        assert result["exists"] is True
        assert result["valid_yaml"] is False

    def test_config_with_tabs(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("name: test\n\tbad: indent\n")
        result = check_config(str(config), None)
        assert result["exists"] is True
        assert result["valid_yaml"] is False


class TestCheckDatabase:
    def test_no_database(self, tmp_path: Path) -> None:
        result = check_database(
            str(tmp_path / "nonexistent"), "config.yml", str(tmp_path),
        )
        assert result["exists"] is False

    def test_database_exists(self, tmp_path: Path) -> None:
        db = tmp_path / "db"
        db.mkdir()
        lang_dir = db / "python"
        lang_dir.mkdir()
        (lang_dir / "test.txt").write_bytes(b"x" * (1024 * 1024))

        result = check_database(str(db), "config.yml", str(tmp_path))
        assert result["exists"] is True
        assert "python" in result["languages"]
        assert result["size_mb"] > 0

    def test_database_with_metadata(self, tmp_path: Path) -> None:
        db = tmp_path / "db"
        db.mkdir()
        metadata = {"git_head": "abc", "config_hash": "", "scripts_hash": "", "config_dir_hash": ""}
        (db / ".cache-metadata.json").write_text(json.dumps(metadata))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="abc\n")
            result = check_database(str(db), "config.yml", str(tmp_path))
            assert result["exists"] is True


class TestCheckResults:
    def test_no_results_dir(self) -> None:
        result = check_results("/nonexistent")
        assert result["exists"] is False

    def test_empty_results_dir(self, tmp_path: Path) -> None:
        results = tmp_path / "results"
        results.mkdir()
        result = check_results(str(results))
        assert result["exists"] is True
        assert result["sarif_files"] == []
        assert len(result["recommendations"]) > 0

    def test_results_with_sarif(self, tmp_path: Path) -> None:
        results = tmp_path / "results"
        results.mkdir()
        sarif_data = {
            "version": "2.1.0",
            "runs": [{"results": [{"ruleId": "test", "level": "warning"}]}],
        }
        (results / "python.sarif").write_text(json.dumps(sarif_data))

        result = check_results(str(results))
        assert result["exists"] is True
        assert "python.sarif" in result["sarif_files"]
        assert result["total_findings"] == 1
        assert result["findings_by_language"]["python"] == 1


class TestMain:
    def test_console_output(self, tmp_path: Path) -> None:
        with patch("shutil.which", return_value=None):
            result = main(["--repo-path", str(tmp_path)])
            assert result == 1

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        with patch("shutil.which", return_value=None):
            main(["--repo-path", str(tmp_path), "--output-format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "cli" in data
        assert "config" in data
        assert "overall_status" in data

    def test_markdown_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        with patch("shutil.which", return_value=None):
            main(["--repo-path", str(tmp_path), "--output-format", "markdown"])
        captured = capsys.readouterr()
        assert "# CodeQL Diagnostics Report" in captured.out

    def test_type_error_propagates(self, tmp_path: Path) -> None:
        with patch.object(_mod, "check_cli", side_effect=TypeError("bad type")):
            with pytest.raises(TypeError, match="bad type"):
                main(["--repo-path", str(tmp_path)])

    def test_attribute_error_propagates(self, tmp_path: Path) -> None:
        with patch.object(_mod, "check_cli", side_effect=AttributeError("no attr")):
            with pytest.raises(AttributeError, match="no attr"):
                main(["--repo-path", str(tmp_path)])


class TestCheckDatabaseCache:
    def test_corrupt_json_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        db = tmp_path / "db"
        db.mkdir()
        (db / ".cache-metadata.json").write_text("{corrupt json!!!")
        with caplog.at_level(logging.WARNING, logger=_mod.__name__):
            result = check_database_cache(str(db), "config.yml", str(tmp_path))
        assert result is False
        assert any("invalid json" in r.message.lower() for r in caplog.records)

    def test_unreadable_metadata_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        db = tmp_path / "db"
        db.mkdir()
        meta = db / ".cache-metadata.json"
        meta.write_text("{}")
        meta.chmod(0o000)
        try:
            with caplog.at_level(logging.WARNING, logger=_mod.__name__):
                result = check_database_cache(str(db), "config.yml", str(tmp_path))
            assert result is False
            assert any("unreadable" in r.message.lower() for r in caplog.records)
        finally:
            meta.chmod(0o644)
