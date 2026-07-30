"""Tests for npm publish CI scripts (issue #3533).

Covers:
  - verify_npm_package_metadata.py
  - measure_npm_pack_size.py
  - verify_npm_published.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))

import measure_npm_pack_size as mnps
import verify_npm_package_metadata as vnpm
import verify_npm_published as vp

# ---------------------------------------------------------------------------
# verify_npm_package_metadata
# ---------------------------------------------------------------------------

_VALID_PKG = {
    "name": "@rjmurillo/ai-agents",
    "version": "1.0.0",
    "publishConfig": {"access": "public", "provenance": True},
    "bin": {"ai-agents": "dist/index.js"},
    "files": ["dist/"],
}


def _write_pkg(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


class TestVerifyNpmPackageMetadata:
    def test_valid_package_passes(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path / "package.json", _VALID_PKG)
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_OK

    def test_wrong_name_fails(self, tmp_path: Path) -> None:
        pkg = {**_VALID_PKG, "name": "@other/pkg"}
        _write_pkg(tmp_path / "package.json", pkg)
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_INVALID

    def test_missing_publish_config_access_fails(self, tmp_path: Path) -> None:
        pkg = {**_VALID_PKG, "publishConfig": {"provenance": True}}
        _write_pkg(tmp_path / "package.json", pkg)
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_INVALID

    def test_private_access_fails(self, tmp_path: Path) -> None:
        pkg = {**_VALID_PKG, "publishConfig": {"access": "restricted", "provenance": True}}
        _write_pkg(tmp_path / "package.json", pkg)
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_INVALID

    def test_missing_provenance_fails(self, tmp_path: Path) -> None:
        pkg = {**_VALID_PKG, "publishConfig": {"access": "public"}}
        _write_pkg(tmp_path / "package.json", pkg)
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_INVALID

    def test_missing_bin_fails(self, tmp_path: Path) -> None:
        pkg = {k: v for k, v in _VALID_PKG.items() if k != "bin"}
        _write_pkg(tmp_path / "package.json", pkg)
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_INVALID

    def test_missing_files_fails(self, tmp_path: Path) -> None:
        pkg = {k: v for k, v in _VALID_PKG.items() if k != "files"}
        _write_pkg(tmp_path / "package.json", pkg)
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_INVALID

    def test_missing_package_json_returns_invalid(self, tmp_path: Path) -> None:
        rc = vnpm.main(["--package-dir", str(tmp_path)])
        assert rc == vnpm.EXIT_INVALID

    def test_multiple_errors_reported(self, tmp_path: Path) -> None:
        pkg = {"name": "wrong", "version": "1.0.0"}
        _write_pkg(tmp_path / "package.json", pkg)
        errors = vnpm.check_package_metadata(pkg)
        assert len(errors) >= 4

    def test_check_returns_empty_for_valid(self) -> None:
        errors = vnpm.check_package_metadata(_VALID_PKG)
        assert errors == []


# ---------------------------------------------------------------------------
# measure_npm_pack_size
# ---------------------------------------------------------------------------


class TestMeasureNpmPackSize:
    def test_ok_when_under_limit(self, tmp_path: Path) -> None:
        mock_result_json = MagicMock(returncode=0, stdout=json.dumps([{"size": 1000}]), stderr="")
        mock_result_human = MagicMock(
            returncode=0, stdout="npm notice Total files: 5\n1 kB\n", stderr=""
        )
        with patch("subprocess.run", side_effect=[mock_result_json, mock_result_human]):
            size, detail = mnps.measure_pack_size(tmp_path)
        assert size == 1000
        assert "kB" in detail

    def test_warning_when_over_limit(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        big = mnps._SIZE_LIMIT_BYTES + 1
        mock_result_json = MagicMock(returncode=0, stdout=json.dumps([{"size": big}]), stderr="")
        mock_result_human = MagicMock(returncode=0, stdout="100 MB\n", stderr="")
        with patch("subprocess.run", side_effect=[mock_result_json, mock_result_human]):
            rc = mnps.main(["--package-dir", str(tmp_path)])
        assert rc == mnps.EXIT_OK
        out = capsys.readouterr().out
        assert "::warning::" in out

    def test_no_warning_when_under_limit(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        mock_result_json = MagicMock(returncode=0, stdout=json.dumps([{"size": 100}]), stderr="")
        mock_result_human = MagicMock(returncode=0, stdout="100 B\n", stderr="")
        with patch("subprocess.run", side_effect=[mock_result_json, mock_result_human]):
            rc = mnps.main(["--package-dir", str(tmp_path)])
        assert rc == mnps.EXIT_OK
        out = capsys.readouterr().out
        assert "::warning::" not in out

    def test_npm_failure_returns_none(self, tmp_path: Path) -> None:
        mock_result = MagicMock(returncode=1, stdout="", stderr="npm error")
        mock_result2 = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", side_effect=[mock_result, mock_result2]):
            size, msg = mnps.measure_pack_size(tmp_path)
        assert size is None
        assert "npm pack failed" in msg

    def test_bad_json_returns_none_size(self, tmp_path: Path) -> None:
        mock_result_json = MagicMock(returncode=0, stdout="not json", stderr="")
        mock_result_human = MagicMock(returncode=0, stdout="unknown\n", stderr="")
        with patch("subprocess.run", side_effect=[mock_result_json, mock_result_human]):
            size, _ = mnps.measure_pack_size(tmp_path)
        assert size is None


# ---------------------------------------------------------------------------
# verify_npm_published
# ---------------------------------------------------------------------------


class TestVerifyNpmPublished:
    def test_immediate_success(self) -> None:
        with patch.object(vp, "get_published_version", return_value="1.2.3"):
            found = vp.wait_for_publish(
                "@rjmurillo/ai-agents", "1.2.3", max_retries=2, delay_seconds=0
            )
        assert found

    def test_success_on_second_attempt(self) -> None:
        calls = {"n": 0}

        def side_effect(pkg: str, ver: str) -> str:
            calls["n"] += 1
            return ver if calls["n"] >= 2 else ""

        with patch.object(vp, "get_published_version", side_effect=side_effect):
            found = vp.wait_for_publish("@x/y", "3.0.0", max_retries=3, delay_seconds=0)
        assert found
        assert calls["n"] == 2

    def test_all_retries_fail_returns_false(self) -> None:
        with patch.object(vp, "get_published_version", return_value=""):
            found = vp.wait_for_publish("@x/y", "1.0.0", max_retries=3, delay_seconds=0)
        assert not found

    def test_main_succeeds_when_published(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path / "package.json", {"version": "2.0.0"})
        with (
            patch.object(vp, "get_published_version", return_value="2.0.0"),
            patch.object(vp.time, "sleep"),
        ):
            rc = vp.main(["--package-dir", str(tmp_path)])
        assert rc == vp.EXIT_OK

    def test_main_fails_when_not_published(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path / "package.json", {"version": "9.9.9"})
        with (
            patch.object(vp, "get_published_version", return_value=""),
            patch.object(vp.time, "sleep"),
        ):
            rc = vp.main(["--package-dir", str(tmp_path)])
        assert rc == vp.EXIT_NOT_PUBLISHED

    def test_main_fails_on_missing_package_json(self, tmp_path: Path) -> None:
        rc = vp.main(["--package-dir", str(tmp_path)])
        assert rc == vp.EXIT_NOT_PUBLISHED

    def test_main_fails_on_missing_version_field(self, tmp_path: Path) -> None:
        _write_pkg(tmp_path / "package.json", {"name": "@x/y"})
        rc = vp.main(["--package-dir", str(tmp_path)])
        assert rc == vp.EXIT_NOT_PUBLISHED

    def test_get_published_version_returns_empty_on_error(self) -> None:
        mock_result = MagicMock(returncode=1, stdout="  \n  ", stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            v = vp.get_published_version("@x/y", "1.0.0")
        assert v == ""
