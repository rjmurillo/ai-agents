"""Shared fixtures for the api-doc-authoring tests."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "api-doc-authoring"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from api_fixtures import QTY_FIELD_V1, QTY_FIELD_V2, serve


@pytest.fixture(autouse=True)
def _run_from_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--evidence`` is confined to the working directory, so each test runs from its tmp_path."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def order_api() -> Iterator[str]:
    """The API as the worked example documents it (field `qty`)."""
    with serve(QTY_FIELD_V1) as base_url:
        yield base_url


@pytest.fixture
def changed_order_api() -> Iterator[str]:
    """The same API after a breaking rename of `qty` to `quantity`."""
    with serve(QTY_FIELD_V2) as base_url:
        yield base_url


@pytest.fixture
def write_doc(tmp_path: Path) -> Callable[[str, str], Path]:
    """Write a markdown document under tmp_path and return its path."""

    def _write(name: str, text: str) -> Path:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    return _write
