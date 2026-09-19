"""CLI and reduction tests for the context extractor."""

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

from test_extract_and_index import (
    REPO_ROOT,
    SAMPLE_DOC,
    SCRIPT_PATH,
    run_cli,
)


@pytest.fixture
def cli_workspace(tmp_path: Path):
    """Provide an isolated repository-local workspace for subprocess output."""
    workspace = REPO_ROOT / ".pytest_tmp" / f"cli_{tmp_path.name}"
    workspace.mkdir(parents=True, exist_ok=True)
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


def _has_tiktoken_encoding() -> bool:
    """Return True when cl100k_base can be loaded without network errors."""
    try:
        import tiktoken

        tiktoken.get_encoding("cl100k_base").encode("probe")
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _has_tiktoken_encoding(),
    reason="cl100k_base tokenizer data unavailable in offline environment",
)
class TestCLI:
    def test_script_exists(self):
        assert SCRIPT_PATH.exists()

    def test_missing_input_file(self):
        result = run_cli(["-i", "/nonexistent/file.md", "-d", "/tmp/out"])
        assert result.returncode == 1

    def test_json_output_to_stdout(self, cli_workspace):
        input_file = cli_workspace / "input.md"
        input_file.write_text(SAMPLE_DOC, encoding="utf-8")
        result = run_cli(["-i", str(input_file), "-d", str(cli_workspace / "details")])

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert output["metrics"]["original_tokens"] > 0
        assert output["metrics"]["sections_extracted"] >= 3

    def test_output_to_file(self, cli_workspace):
        input_file = cli_workspace / "input.md"
        detail_dir = cli_workspace / "details"
        output_file = cli_workspace / "index.md"
        input_file.write_text(SAMPLE_DOC, encoding="utf-8")
        result = run_cli(
            [
                "-i",
                str(input_file),
                "-d",
                str(detail_dir),
                "-o",
                str(output_file),
            ]
        )

        assert result.returncode == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "[" in content
        assert "(see:" in content

    def test_custom_detail_ref(self, cli_workspace):
        input_file = cli_workspace / "input.md"
        input_file.write_text(SAMPLE_DOC, encoding="utf-8")
        result = run_cli(
            [
                "-i",
                str(input_file),
                "-d",
                str(cli_workspace / "details"),
                "-r",
                ".custom-docs",
            ]
        )

        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert ".custom-docs/" in output["index_content"]
