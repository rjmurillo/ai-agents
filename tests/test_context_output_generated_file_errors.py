"""Tests for generated context output drift and path errors."""

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

from extract_and_index import check_generated_files, extract_and_index
from test_extract_and_index import SAMPLE_DOC


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


def _generate_output(tmp_path: Path, content: str = SAMPLE_DOC) -> tuple[Path, Path]:
    detail_dir = tmp_path / "details"
    index_path = tmp_path / "index.md"
    result = extract_and_index(content, detail_dir, ".details", repo_root=tmp_path)
    index_path.write_text(result.index_content, encoding="utf-8")
    return detail_dir, index_path


def test_reports_index_drift(tmp_path: Path) -> None:
    detail_dir, index_path = _generate_output(tmp_path)
    index_path.write_text("stale index\n", encoding="utf-8")

    issues = check_generated_files(
        SAMPLE_DOC,
        detail_dir,
        index_path,
        ".details",
        repo_root=tmp_path,
    )

    assert any("index drift" in issue.lower() for issue in issues)


def test_reports_missing_and_extra_detail_files(tmp_path: Path) -> None:
    detail_dir, index_path = _generate_output(tmp_path)
    (detail_dir / "architecture.md").unlink()
    (detail_dir / "extra.md").write_text("# Extra\n", encoding="utf-8")

    issues = check_generated_files(
        SAMPLE_DOC,
        detail_dir,
        index_path,
        ".details",
        repo_root=tmp_path,
    )

    assert any("missing detail file" in issue.lower() for issue in issues)
    assert any("extra detail file" in issue.lower() for issue in issues)


def test_rejects_paths_outside_repository(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    outside = tmp_path / "outside"

    with pytest.raises(PermissionError):
        check_generated_files(
            SAMPLE_DOC,
            outside / "details",
            outside / "index.md",
            ".details",
            repo_root=repo_root,
        )
