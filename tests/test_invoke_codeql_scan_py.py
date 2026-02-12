"""Tests for invoke_codeql_scan.py CodeQL scan orchestration script."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_spec = importlib.util.spec_from_file_location(
    "invoke_codeql_scan",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".codeql",
        "scripts",
        "invoke_codeql_scan.py",
    ),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

build_parser = _mod.build_parser
detect_languages = _mod.detect_languages
compute_file_hash = _mod.compute_file_hash
compute_directory_hash = _mod.compute_directory_hash
check_database_cache = _mod.check_database_cache
format_results = _mod.format_results


class TestBuildParser:
    def test_default_values(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.repo_path == "."
        assert args.output_format == "console"
        assert args.ci is False
        assert args.use_cache is False
        assert args.quick_scan is False
        assert args.languages is None

    def test_custom_languages(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--languages", "python", "actions"])
        assert args.languages == ["python", "actions"]

    def test_ci_mode(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--ci", "--format", "json"])
        assert args.ci is True
        assert args.output_format == "json"


class TestDetectLanguages:
    def test_detects_python(self, tmp_path: Path) -> None:
        (tmp_path / "script.py").write_text("print('hello')")
        langs = detect_languages(str(tmp_path))
        assert "python" in langs

    def test_detects_actions(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI")
        langs = detect_languages(str(tmp_path))
        assert "actions" in langs

    def test_no_languages(self, tmp_path: Path) -> None:
        langs = detect_languages(str(tmp_path))
        assert langs == []

    def test_detects_both(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text("pass")
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI")
        langs = detect_languages(str(tmp_path))
        assert "python" in langs
        assert "actions" in langs


class TestComputeFileHash:
    def test_produces_sha256(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello world")
        result = compute_file_hash(str(f))
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")
        assert compute_file_hash(str(f1)) != compute_file_hash(str(f2))


class TestComputeDirectoryHash:
    def test_empty_directory(self, tmp_path: Path) -> None:
        sub = tmp_path / "empty"
        sub.mkdir()
        result = compute_directory_hash(str(sub))
        assert isinstance(result, str)
        assert len(result) == 64

    def test_nonexistent_directory(self) -> None:
        result = compute_directory_hash("/nonexistent/path")
        assert result == ""

    def test_deterministic(self, tmp_path: Path) -> None:
        sub = tmp_path / "dir"
        sub.mkdir()
        (sub / "a.txt").write_text("aaa")
        (sub / "b.txt").write_text("bbb")
        h1 = compute_directory_hash(str(sub))
        h2 = compute_directory_hash(str(sub))
        assert h1 == h2


class TestCheckDatabaseCache:
    def test_no_database_dir(self, tmp_path: Path) -> None:
        assert check_database_cache(
            str(tmp_path / "nonexistent"), "config.yml", str(tmp_path),
        ) is False

    def test_no_metadata_file(self, tmp_path: Path) -> None:
        db = tmp_path / "db"
        db.mkdir()
        assert check_database_cache(str(db), "config.yml", str(tmp_path)) is False

    def test_valid_cache(self, tmp_path: Path) -> None:
        db = tmp_path / "db"
        db.mkdir()

        config = tmp_path / "config.yml"
        config.write_text("name: test")
        config_hash = compute_file_hash(str(config))

        metadata = {
            "git_head": "abc123",
            "config_hash": config_hash,
            "scripts_hash": "",
            "config_dir_hash": "",
        }
        (db / ".cache-metadata.json").write_text(json.dumps(metadata))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="abc123\n",
            )
            result = check_database_cache(str(db), str(config), str(tmp_path))
            assert result is True

    def test_stale_cache_git_changed(self, tmp_path: Path) -> None:
        db = tmp_path / "db"
        db.mkdir()

        metadata = {
            "git_head": "old_head",
            "config_hash": "",
            "scripts_hash": "",
            "config_dir_hash": "",
        }
        (db / ".cache-metadata.json").write_text(json.dumps(metadata))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="new_head\n",
            )
            result = check_database_cache(str(db), "config.yml", str(tmp_path))
            assert result is False


class TestFormatResults:
    def test_console_format(self, capsys: pytest.CaptureFixture) -> None:
        results = [
            {
                "language": "python",
                "findings_count": 0,
                "findings": [],
                "sarif_path": "/tmp/python.sarif",
                "timed_out": False,
            },
        ]
        format_results(results, "console")
        captured = capsys.readouterr()
        assert "python" in captured.err
        assert "0 findings" in captured.err

    def test_json_format(self, capsys: pytest.CaptureFixture) -> None:
        results = [
            {
                "language": "python",
                "findings_count": 2,
                "findings": [{}, {}],
                "sarif_path": "/tmp/python.sarif",
                "timed_out": False,
            },
        ]
        format_results(results, "json")
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["TotalFindings"] == 2

    def test_timed_out_excluded_from_total(self, capsys: pytest.CaptureFixture) -> None:
        results = [
            {
                "language": "python",
                "findings_count": 0,
                "findings": [],
                "sarif_path": None,
                "timed_out": True,
            },
        ]
        format_results(results, "json")
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["TotalFindings"] == 0
