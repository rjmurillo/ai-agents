"""CLI tests for complete context-output manifest validation."""

import json
import shutil
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

from extract_and_index import extract_and_index
from test_extract_and_index import REPO_ROOT, SAMPLE_DOC, run_cli


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


class TestManifestCLI:
    def test_check_manifest_reports_counts_and_drift(self, tmp_path):
        """AC: check-only CLI validates a manifest without rewriting outputs."""
        work_dir = REPO_ROOT / ".pytest_tmp" / f"manifest_{tmp_path.name}"
        output_root = work_dir / "output"
        work_dir.mkdir(parents=True, exist_ok=True)
        source = work_dir / "source.md"
        detail_dir = output_root / "details"
        index_path = output_root / "index.md"
        manifest_path = work_dir / "manifest.json"
        try:
            source.write_text(SAMPLE_DOC, encoding="utf-8")
            detail_ref = detail_dir.relative_to(REPO_ROOT).as_posix()
            result = extract_and_index(
                SAMPLE_DOC,
                detail_dir,
                detail_ref,
                repo_root=REPO_ROOT,
            )
            index_path.write_text(result.index_content, encoding="utf-8")
            manifest_path.write_text(
                json.dumps(
                    {
                        "output_root": output_root.relative_to(REPO_ROOT).as_posix(),
                        "entries": [
                            {
                                "source": source.relative_to(REPO_ROOT).as_posix(),
                                "index": index_path.relative_to(REPO_ROOT).as_posix(),
                                "detail_dir": detail_ref,
                                "detail_ref": detail_ref,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            before = {path: path.read_bytes() for path in [index_path, *detail_dir.iterdir()]}

            result = run_cli(["--check", "--manifest", str(manifest_path)])

            assert result.returncode == 0
            assert "Checked 1 source, 1 index" in result.stderr
            after = {path: path.read_bytes() for path in [index_path, *detail_dir.iterdir()]}
            assert after == before
            next(detail_dir.iterdir()).write_text("drift\n", encoding="utf-8")

            result = run_cli(["--check", "--manifest", str(manifest_path)])

            assert result.returncode == 1
            assert "Context output drift detected" in result.stderr
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
