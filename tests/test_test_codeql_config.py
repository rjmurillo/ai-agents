"""Tests for test_codeql_config.py configuration validation script."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

_spec = importlib.util.spec_from_file_location(
    "test_codeql_config",
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".codeql",
        "scripts",
        "test_codeql_config.py",
    ),
)
assert _spec is not None, "Failed to find test_codeql_config.py"
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None, "Module spec has no loader"
_spec.loader.exec_module(_mod)

build_parser = _mod.build_parser
validate_yaml_syntax = _mod.validate_yaml_syntax
validate_config_schema = _mod.validate_config_schema
validate_paths_exist = _mod.validate_paths_exist
main = _mod.main


class TestBuildParser:
    def test_default_values(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.config_path == ".github/codeql/codeql-config.yml"
        assert args.ci is False
        assert args.output_format == "console"

    def test_custom_config_path(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--config-path", "/tmp/config.yml"])
        assert args.config_path == "/tmp/config.yml"

    def test_json_format(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--format", "json"])
        assert args.output_format == "json"


class TestValidateYamlSyntax:
    def test_valid_yaml(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("name: test\npacks:\n  - codeql/python-queries\n")
        result = validate_yaml_syntax(str(config))
        assert result["valid"] is True
        assert result["content"] is not None

    def test_empty_file(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("")
        result = validate_yaml_syntax(str(config))
        assert result["valid"] is False
        assert "empty" in result["error"].lower()

    def test_tabs_rejected(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("name: test\n\tinvalid: yes\n")
        result = validate_yaml_syntax(str(config))
        assert result["valid"] is False
        assert "tab" in result["error"].lower() or "\\t" in result["error"]

    def test_nonexistent_file(self) -> None:
        result = validate_yaml_syntax("/nonexistent/config.yml")
        assert result["valid"] is False


class TestValidateConfigSchema:
    def test_valid_config(self) -> None:
        content = "name: test-config\npacks:\n  - codeql/python-queries\n"
        result = validate_config_schema(content)
        assert result["errors"] == []
        assert len(result["packs"]) == 1

    def test_missing_name(self) -> None:
        content = "packs:\n  - codeql/python-queries\n"
        result = validate_config_schema(content)
        assert any("name" in e.lower() for e in result["errors"])

    def test_missing_packs_and_queries(self) -> None:
        content = "name: test-config\n"
        result = validate_config_schema(content)
        assert any("packs" in e.lower() or "queries" in e.lower() for e in result["errors"])

    def test_invalid_severity(self) -> None:
        content = "name: test-config\npacks:\n  - q\nseverity: banana\n"
        result = validate_config_schema(content)
        assert any("severity" in e.lower() for e in result["errors"])

    def test_valid_severity(self) -> None:
        content = "name: test-config\npacks:\n  - q\nseverity: high\n"
        result = validate_config_schema(content)
        assert not any("severity" in e.lower() for e in result["errors"])

    def test_extracts_paths(self) -> None:
        content = "name: test\nqueries:\n  - q\npaths:\n  - src/\n  - lib/\n"
        result = validate_config_schema(content)
        assert len(result["paths"]) == 2


class TestValidatePathsExist:
    def test_existing_paths(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        result = validate_paths_exist(["src"], str(tmp_path))
        assert result == []

    def test_missing_paths(self, tmp_path: Path) -> None:
        result = validate_paths_exist(["nonexistent"], str(tmp_path))
        assert len(result) == 1
        assert result[0]["path"] == "nonexistent"


class TestMain:
    def test_config_not_found(self, tmp_path: Path) -> None:
        result = main(["--config-path", str(tmp_path / "missing.yml"), "--ci"])
        assert result == 2

    def test_valid_config(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("name: test-config\npacks:\n  - codeql/python-queries\n")
        with patch.object(_mod, "find_codeql_executable", return_value=None):
            result = main(["--config-path", str(config)])
            assert result == 0

    def test_invalid_config_returns_error(self, tmp_path: Path) -> None:
        config = tmp_path / "config.yml"
        config.write_text("")
        result = main(["--config-path", str(config), "--ci"])
        assert result == 1

    def test_json_output(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        config = tmp_path / "config.yml"
        config.write_text("name: test-config\nqueries:\n  - q\n")
        with patch.object(_mod, "find_codeql_executable", return_value=None):
            main(["--config-path", str(config), "--format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["valid"] is True
