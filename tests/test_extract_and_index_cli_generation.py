"""Generation operation tests for the context extractor CLI."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from context_output_cli_test_support import SAMPLE_DOC, cli, cli_args, cli_workspace, core


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


class TestCLIGeneration:
    def test_reports_verbose_and_output_io_errors(self, tmp_path, capsys):
        _, _, detail_dir, index_path, _ = cli_workspace(tmp_path)
        args = cli_args(detail_dir=detail_dir, output=index_path, verbose=True)
        assert cli._run_generation(args, SAMPLE_DOC, "details", core) == 0
        assert "Metrics:" in capsys.readouterr().err

        directory_args = cli_args(detail_dir=detail_dir, output=detail_dir)
        assert cli._run_generation(directory_args, SAMPLE_DOC, "details", core) == 3

    def test_maps_success_json_and_tokenizer_errors(self, tmp_path, monkeypatch, capsys):
        _, _, detail_dir, index_path, _ = cli_workspace(tmp_path)
        args = cli_args(detail_dir=detail_dir, output=index_path)
        assert cli._run_generation(args, SAMPLE_DOC, "details", core) == 0
        assert index_path.exists()

        json_args = cli_args(detail_dir=detail_dir)
        assert cli._run_generation(json_args, SAMPLE_DOC, "details", core) == 0
        assert json.loads(capsys.readouterr().out)["success"] is True

        monkeypatch.setattr(
            core,
            "extract_and_index",
            Mock(side_effect=RuntimeError("tokenizer unavailable")),
        )
        assert cli._run_generation(args, SAMPLE_DOC, "details", core) == 4

    def test_maps_os_and_permission_errors(self, tmp_path, monkeypatch):
        _, _, detail_dir, _, _ = cli_workspace(tmp_path)
        args = cli_args(detail_dir=detail_dir, output=tmp_path / "outside.md")
        assert cli._run_generation(args, SAMPLE_DOC, "details", core) == 3

        monkeypatch.setattr(
            core,
            "extract_and_index",
            Mock(side_effect=OSError("write failed")),
        )
        assert cli._run_generation(args, SAMPLE_DOC, "details", core) == 3
