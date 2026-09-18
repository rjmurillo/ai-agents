"""Contract tests for complete context-output manifest validation."""

import json
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

from extract_and_index import check_manifest, extract_and_index
from test_extract_and_index import SAMPLE_DOC


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


class TestManifestContract:
    def _generate_manifest(self, tmp_path):
        source = tmp_path / "source.md"
        output_root = tmp_path / "output"
        detail_dir = output_root / "details"
        index_path = output_root / "index.md"
        manifest_path = tmp_path / "manifest.json"
        source.write_text(SAMPLE_DOC, encoding="utf-8")

        detail_ref = detail_dir.relative_to(tmp_path).as_posix()
        result = extract_and_index(SAMPLE_DOC, detail_dir, detail_ref, repo_root=tmp_path)
        index_path.write_text(result.index_content, encoding="utf-8")
        manifest_path.write_text(
            json.dumps(
                {
                    "output_root": output_root.relative_to(tmp_path).as_posix(),
                    "entries": [
                        {
                            "source": "source.md",
                            "index": index_path.relative_to(tmp_path).as_posix(),
                            "detail_dir": detail_ref,
                            "detail_ref": detail_ref,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return manifest_path, index_path, detail_dir

    def test_validates_all_manifest_outputs_and_reports_counts(self, tmp_path):
        """AC: the manifest checks every source and reports generated counts."""
        manifest_path, _, detail_dir = self._generate_manifest(tmp_path)

        report = check_manifest(manifest_path, repo_root=tmp_path)

        assert report.issues == []
        assert report.sources_checked == 1
        assert report.indexes_checked == 1
        expected_details = len(list(detail_dir.iterdir()))
        assert report.details_checked == expected_details
        assert report.details_found == expected_details

    def test_reports_manifest_drift(self, tmp_path):
        """AC: missing and stale outputs fail the complete manifest check."""
        manifest_path, index_path, detail_dir = self._generate_manifest(tmp_path)
        index_path.write_text("stale index\n", encoding="utf-8")
        next(detail_dir.iterdir()).unlink()

        report = check_manifest(manifest_path, repo_root=tmp_path)

        assert any("index drift" in issue.lower() for issue in report.issues)
        assert any("missing detail file" in issue.lower() for issue in report.issues)

    def test_reports_extra_sibling_output_file(self, tmp_path):
        """AC: an unlisted index in the output root fails closed."""
        manifest_path, index_path, _ = self._generate_manifest(tmp_path)
        extra_index = index_path.parent / "stale-index.md"
        extra_index.write_text("stale\n", encoding="utf-8")

        report = check_manifest(manifest_path, repo_root=tmp_path)

        assert any(
            "extra context output" in issue.lower() and "stale-index.md" in issue
            for issue in report.issues
        )

    def test_reports_missing_source_and_found_output_count(self, tmp_path):
        """AC: missing sources fail while existing generated files remain counted."""
        manifest_path, _, detail_dir = self._generate_manifest(tmp_path)
        (tmp_path / "source.md").unlink()

        report = check_manifest(manifest_path, repo_root=tmp_path)

        assert any("missing source file" in issue.lower() for issue in report.issues)
        assert report.details_checked == 0
        assert report.details_found == len(list(detail_dir.iterdir()))
