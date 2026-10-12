"""Conformance of the zero-collection guard's config reader to pytest (#5399)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation.check_zero_collection_tests import read_pytest_config

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_read_pytest_config_conformance_to_pytest(pytestconfig: pytest.Config) -> None:
    testpaths, python_files = read_pytest_config(REPO_ROOT)

    assert testpaths == list(pytestconfig.getini("testpaths"))
    assert python_files == list(pytestconfig.getini("python_files"))


def test_reader_rejects_a_pyproject_without_the_pytest_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="table"):
        read_pytest_config(tmp_path)
