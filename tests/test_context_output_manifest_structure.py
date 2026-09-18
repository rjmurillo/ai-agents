"""Tests for manifest path relationships."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
    ),
)

from context_output_manifest_test_support import write_manifest
from extract_and_index import check_manifest


def test_rejects_overlapping_manifest_outputs(tmp_path: Path) -> None:
    """AC: manifest entries cannot inspect overlapping file trees."""
    manifest_path = tmp_path / "manifest.json"
    write_manifest(
        manifest_path,
        [
            {"source": "source.md", "index": "index.md", "detail_dir": "details"},
            {
                "source": "details/nested.md",
                "index": "other-index.md",
                "detail_dir": "other-details",
            },
        ],
    )

    with pytest.raises(ValueError, match="overlap"):
        check_manifest(manifest_path, repo_root=tmp_path)


def test_rejects_manifest_reference_alias(tmp_path: Path) -> None:
    """AC: generated references resolve to the declared detail directory."""
    manifest_path = tmp_path / "manifest.json"
    write_manifest(
        manifest_path,
        [
            {
                "source": "source.md",
                "index": "index.md",
                "detail_dir": "details",
                "detail_ref": "other-details",
            }
        ],
    )

    with pytest.raises(ValueError, match="detail_ref"):
        check_manifest(manifest_path, repo_root=tmp_path)
