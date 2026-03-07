"""Tests for review_memory_export_security.py sensitive data scanning."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.review_memory_export_security import main, scan_file


@pytest.fixture
def clean_file(tmp_path: Path) -> Path:
    p = tmp_path / "clean.json"
    p.write_text('{"data": "safe content, no secrets here"}', encoding="utf-8")
    return p


@pytest.fixture
def file_with_api_key(tmp_path: Path) -> Path:
    p = tmp_path / "secrets.json"
    p.write_text('{"key": "ghp_abcdefghijklmnopqrstuvwxyz1234567890"}', encoding="utf-8")
    return p


@pytest.fixture
def file_with_private_key(tmp_path: Path) -> Path:
    p = tmp_path / "private.json"
    p.write_text('{"data": "-----BEGIN RSA KEY-----"}', encoding="utf-8")
    return p


@pytest.fixture
def file_with_home_path(tmp_path: Path) -> Path:
    p = tmp_path / "paths.json"
    p.write_text('{"path": "/home/testuser/secrets/config"}', encoding="utf-8")
    return p


class TestScanFile:
    def test_clean_file_returns_0(self, clean_file: Path) -> None:
        assert scan_file(clean_file, quiet=True) == 0

    def test_file_with_api_key_returns_1(self, file_with_api_key: Path) -> None:
        assert scan_file(file_with_api_key, quiet=True) == 1

    def test_file_with_private_key_returns_1(self, file_with_private_key: Path) -> None:
        assert scan_file(file_with_private_key, quiet=True) == 1

    def test_file_with_home_path_returns_1(self, file_with_home_path: Path) -> None:
        assert scan_file(file_with_home_path, quiet=True) == 1


class TestMain:
    def test_missing_file_returns_1(self) -> None:
        assert main(["nonexistent.json"]) == 1

    def test_clean_file_returns_0(self, clean_file: Path) -> None:
        assert main([str(clean_file)]) == 0

    def test_quiet_flag_accepted(self, clean_file: Path) -> None:
        assert main([str(clean_file), "--quiet"]) == 0
