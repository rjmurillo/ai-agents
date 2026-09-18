"""Safety tests for complete context-output manifest validation."""

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


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


class TestManifestSafety:
    def test_rejects_non_object_manifest(self, tmp_path):
        """AC: manifest JSON must be an object with an entries array."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("[]", encoding="utf-8")

        with pytest.raises(ValueError, match="entries.*array"):
            check_manifest(manifest_path, repo_root=tmp_path)

    def test_rejects_empty_manifest(self, tmp_path):
        """AC: an empty manifest cannot produce a false green check."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"entries": []}', encoding="utf-8")

        with pytest.raises(ValueError, match="must not be empty"):
            check_manifest(manifest_path, repo_root=tmp_path)

    def test_rejects_malformed_manifest(self, tmp_path):
        """AC: malformed manifest configuration fails closed."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("{", encoding="utf-8")

        with pytest.raises(ValueError):
            check_manifest(manifest_path, repo_root=tmp_path)

    def test_rejects_unknown_manifest_fields(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            '{"output_root": ".", "entries": [{"source": "source.md", '
            '"index": "index.md", "detail_dir": "details"}], "extra": true}',
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="only entries and output_root"):
            check_manifest(manifest_path, repo_root=tmp_path)

    def test_rejects_non_object_manifest_entry(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        write_manifest(manifest_path, ["not an object"])

        with pytest.raises(ValueError, match="must be an object"):
            check_manifest(manifest_path, repo_root=tmp_path)

    def test_rejects_incomplete_manifest_entry(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        write_manifest(manifest_path, [{"source": "source.md"}])

        with pytest.raises(ValueError, match="requires only"):
            check_manifest(manifest_path, repo_root=tmp_path)

    def test_rejects_output_paths_outside_output_root(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        write_manifest(
            manifest_path,
            [{"source": "source.md", "index": "index.md", "detail_dir": "details"}],
            output_root="output",
        )

        with pytest.raises(ValueError, match="inside output_root"):
            check_manifest(manifest_path, repo_root=tmp_path)

    def test_rejects_unsafe_manifest_paths(self, tmp_path):
        """AC: manifest path traversal fails closed before any file access."""
        manifest_path = tmp_path / "manifest.json"
        write_manifest(
            manifest_path,
            [
                {
                    "source": "../outside.md",
                    "index": "index.md",
                    "detail_dir": "details",
                }
            ],
        )

        with pytest.raises((PermissionError, ValueError)):
            check_manifest(manifest_path, repo_root=tmp_path)
