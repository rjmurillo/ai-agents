"""Tests for CodeQL CI scripts (issue #3526).

Covers:
  - verify_codeql_artifacts.py
  - verify_codeql_sarif_structure.py
  - codeql_integration_summary.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))

import codeql_integration_summary as cis
import verify_codeql_artifacts as vca
import verify_codeql_sarif_structure as vcss

# ---------------------------------------------------------------------------
# verify_codeql_artifacts
# ---------------------------------------------------------------------------


class TestVerifyCodeqlArtifacts:
    def test_ok_when_db_dir_and_sarif_file_exist(self, tmp_path: Path) -> None:
        lang = "python"
        db_dir = tmp_path / ".codeql/db" / lang
        db_dir.mkdir(parents=True)
        results_dir = tmp_path / ".codeql/results"
        results_dir.mkdir(parents=True)
        sarif = results_dir / f"{lang}.sarif"
        sarif.write_text(
            json.dumps({"version": "2.1.0", "runs": [{"results": []}]}),
            encoding="utf-8",
        )
        rc = vca.main(
            [
                "--language",
                lang,
                "--db-base",
                str(tmp_path / ".codeql/db"),
                "--results-base",
                str(results_dir),
            ]
        )
        assert rc == 0  # EXIT_OK

    def test_missing_db_dir_returns_invalid(self, tmp_path: Path) -> None:
        lang = "python"
        results_dir = tmp_path / ".codeql/results"
        results_dir.mkdir(parents=True)
        sarif = results_dir / f"{lang}.sarif"
        # Valid SARIF so only the missing DB triggers the error
        sarif.write_text(
            json.dumps({"version": "2.1.0", "runs": [{"results": []}]}),
            encoding="utf-8",
        )
        rc = vca.main(
            [
                "--language",
                lang,
                "--db-base",
                str(tmp_path / ".codeql/db"),
                "--results-base",
                str(results_dir),
            ]
        )
        assert rc == 1  # EXIT_MISSING

    def test_missing_sarif_file_returns_invalid(self, tmp_path: Path) -> None:
        lang = "python"
        db_dir = tmp_path / ".codeql/db" / lang
        db_dir.mkdir(parents=True)
        rc = vca.main(
            [
                "--language",
                lang,
                "--db-base",
                str(tmp_path / ".codeql/db"),
                "--results-base",
                str(tmp_path / ".codeql/results"),
            ]
        )
        assert rc == 1  # EXIT_MISSING

    def test_prints_finding_count(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        lang = "javascript"
        db_dir = tmp_path / ".codeql/db" / lang
        db_dir.mkdir(parents=True)
        results_dir = tmp_path / ".codeql/results"
        results_dir.mkdir(parents=True)
        sarif = results_dir / f"{lang}.sarif"
        sarif.write_text(
            json.dumps(
                {
                    "version": "2.1.0",
                    "runs": [{"results": [{"ruleId": "X"}, {"ruleId": "Y"}]}],
                }
            ),
            encoding="utf-8",
        )
        rc = vca.main(
            [
                "--language",
                lang,
                "--db-base",
                str(tmp_path / ".codeql/db"),
                "--results-base",
                str(results_dir),
            ]
        )
        assert rc == 0  # EXIT_OK
        out = capsys.readouterr().out
        assert "2 findings" in out

    def test_missing_language_arg_is_usage_error(self) -> None:
        with pytest.raises(SystemExit) as exc:
            vca.main([])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# verify_codeql_sarif_structure
# ---------------------------------------------------------------------------


def _write_sarif(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class TestVerifyCodeqlSarifStructure:
    def test_ok_with_valid_sarif(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_sarif(
            results_dir / "test.sarif",
            {"version": "2.1.0", "runs": [{"results": []}]},
        )
        all_valid, errors = vcss.validate_sarif_directory(results_dir)
        assert all_valid
        assert errors == []

    def test_missing_version_fails(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_sarif(results_dir / "bad.sarif", {"runs": [{"results": []}]})
        all_valid, errors = vcss.validate_sarif_directory(results_dir)
        assert not all_valid
        assert any("version" in e for e in errors)

    def test_missing_runs_fails(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_sarif(results_dir / "bad.sarif", {"version": "2.1.0"})
        all_valid, errors = vcss.validate_sarif_directory(results_dir)
        assert not all_valid
        assert any("runs" in e for e in errors)

    def test_no_sarif_files_returns_error(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "empty"
        results_dir.mkdir()
        all_valid, errors = vcss.validate_sarif_directory(results_dir)
        assert not all_valid
        assert any("No SARIF files" in e for e in errors)

    def test_invalid_json_returns_error(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "corrupt.sarif").write_text("not json", encoding="utf-8")
        all_valid, errors = vcss.validate_sarif_directory(results_dir)
        assert not all_valid
        assert any("JSON" in e for e in errors)

    def test_multiple_sarif_all_valid(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        for name in ("a.sarif", "b.sarif"):
            _write_sarif(
                results_dir / name,
                {"version": "2.1.0", "runs": [{"results": []}]},
            )
        all_valid, errors = vcss.validate_sarif_directory(results_dir)
        assert all_valid
        assert errors == []

    def test_multiple_sarif_one_invalid(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_sarif(
            results_dir / "good.sarif",
            {"version": "2.1.0", "runs": [{"results": []}]},
        )
        _write_sarif(results_dir / "bad.sarif", {"version": "2.1.0"})
        all_valid, errors = vcss.validate_sarif_directory(results_dir)
        assert not all_valid
        assert len(errors) == 1

    def test_cli_missing_dir_returns_1(self, tmp_path: Path) -> None:
        rc = vcss.main(["--results-dir", str(tmp_path / "nonexistent")])
        assert rc == vcss.EXIT_INVALID

    def test_cli_ok_dir_returns_0(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        _write_sarif(
            results_dir / "x.sarif",
            {"version": "2.1.0", "runs": [{"results": []}]},
        )
        rc = vcss.main(["--results-dir", str(results_dir)])
        assert rc == vcss.EXIT_OK


# ---------------------------------------------------------------------------
# codeql_integration_summary
# ---------------------------------------------------------------------------


class TestCodeqlIntegrationSummary:
    def test_all_success(self) -> None:
        results = {
            "INSTALL_RESULT": "success",
            "LANGUAGE_RESULT": "success",
            "JSON_RESULT": "success",
        }
        text, all_passed = cis.build_summary(results)
        assert all_passed
        assert "TIP" in text
        assert "CAUTION" not in text

    def test_one_failure(self) -> None:
        results = {
            "INSTALL_RESULT": "success",
            "LANGUAGE_RESULT": "failure",
            "JSON_RESULT": "success",
        }
        text, all_passed = cis.build_summary(results)
        assert not all_passed
        assert "CAUTION" in text
        assert "TIP" not in text

    def test_all_skipped(self) -> None:
        results = {
            "INSTALL_RESULT": "skipped",
            "LANGUAGE_RESULT": "skipped",
            "JSON_RESULT": "skipped",
        }
        text, all_passed = cis.build_summary(results)
        assert all_passed
        assert "\u23ed" in text

    def test_missing_env_treated_as_failure(self) -> None:
        results = {}
        text, all_passed = cis.build_summary(results)
        assert not all_passed

    def test_table_has_all_three_rows(self) -> None:
        results = {
            "INSTALL_RESULT": "success",
            "LANGUAGE_RESULT": "success",
            "JSON_RESULT": "success",
        }
        text, _ = cis.build_summary(results)
        assert "Install & Config" in text
        assert "Language Scans" in text
        assert "JSON Output" in text

    def test_main_writes_to_summary_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary_file = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        monkeypatch.setenv("INSTALL_RESULT", "success")
        monkeypatch.setenv("LANGUAGE_RESULT", "success")
        monkeypatch.setenv("JSON_RESULT", "success")
        rc = cis.main()
        assert rc == cis.EXIT_OK
        content = summary_file.read_text(encoding="utf-8")
        assert "CodeQL Integration Test Results" in content

    def test_main_returns_1_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary_file = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        monkeypatch.setenv("INSTALL_RESULT", "failure")
        monkeypatch.setenv("LANGUAGE_RESULT", "success")
        monkeypatch.setenv("JSON_RESULT", "success")
        rc = cis.main()
        assert rc == cis.EXIT_FAILED

    def test_main_returns_2_without_summary_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        rc = cis.main()
        assert rc == cis.EXIT_USAGE

    def test_main_appends_not_overwrites(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary_file = tmp_path / "summary.md"
        summary_file.write_text("existing content\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        monkeypatch.setenv("INSTALL_RESULT", "success")
        monkeypatch.setenv("LANGUAGE_RESULT", "success")
        monkeypatch.setenv("JSON_RESULT", "success")
        cis.main()
        content = summary_file.read_text(encoding="utf-8")
        assert content.startswith("existing content")
        assert "CodeQL Integration Test Results" in content
