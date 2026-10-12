"""Conformance of the live binplace manifest to the loader's Row schema (#5399).

The module docstring in binplace_manifest.py no longer copies the manifest
schema. These tests load the real manifest so a schema change fails here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import binplace_manifest  # noqa: E402
import yaml  # noqa: E402

_MANIFEST = _REPO_ROOT / "templates" / "platforms" / "binplace.yaml"
_ROW_KEYS = {"class", "source", "plugin_tree", "install_tree", "compile"}


def _raw_rows() -> list[dict]:
    return yaml.safe_load(_MANIFEST.read_text(encoding="utf-8"))["rows"]


def test_live_manifest_conformance_to_row_schema() -> None:
    raw = _raw_rows()
    rows = binplace_manifest.load(_REPO_ROOT)

    assert [row.class_name for row in rows] == [entry["class"] for entry in raw]
    for entry in raw:
        assert set(entry) <= _ROW_KEYS, f"row {entry['class']} has a key Row does not model"
        assert {"plugin_tree", "install_tree"} <= set(entry)


def test_row_model_covers_every_manifest_key() -> None:
    fields = set(binplace_manifest.Row.__dataclass_fields__)

    assert fields == {"class_name", "source", "plugin_tree", "install_tree", "compile"}


@pytest.mark.parametrize("missing", ["plugin_tree", "install_tree"])
def test_row_missing_a_required_key_is_rejected(tmp_path: Path, missing: str) -> None:
    (tmp_path / "templates" / "platforms").mkdir(parents=True)
    (tmp_path / "templates" / "x").mkdir()
    keys = {"plugin_tree": "null", "install_tree": ".claude/x"}
    del keys[missing]
    body = "".join(f"    {k}: {v}\n" for k, v in keys.items())
    (tmp_path / "templates" / "platforms" / "binplace.yaml").write_text(
        'schemaVersion: "1.0"\nrows:\n  - class: x\n    source: templates/x\n' + body,
        encoding="utf-8",
    )

    with pytest.raises(binplace_manifest.BinplaceConfigError, match=missing):
        binplace_manifest.load(tmp_path)
