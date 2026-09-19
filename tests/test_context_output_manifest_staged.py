"""Tests for staged context output validation."""

import json
import subprocess
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


def _generate_manifest(tmp_path: Path) -> tuple[Path, Path, Path]:
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


def test_staged_check_catches_outputs_left_unstaged(tmp_path: Path) -> None:
    """AC: pre-commit compares staged sources with staged outputs."""
    manifest_path, index_path, detail_dir = _generate_manifest(tmp_path)
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)

    source = tmp_path / "source.md"
    changed_content = SAMPLE_DOC.replace("layered architecture", "changed architecture")
    source.write_text(changed_content, encoding="utf-8")
    result = extract_and_index(changed_content, detail_dir, "output/details", repo_root=tmp_path)
    index_path.write_text(result.index_content, encoding="utf-8")
    subprocess.run(
        ["git", "add", "source.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert check_manifest(manifest_path, repo_root=tmp_path).issues == []
    report = check_manifest(manifest_path, repo_root=tmp_path, staged=True)

    assert any("index drift" in issue.lower() for issue in report.issues)
    assert any("detail drift" in issue.lower() for issue in report.issues)
