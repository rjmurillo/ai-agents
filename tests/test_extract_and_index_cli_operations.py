"""Single-file check operation tests for the context extractor CLI."""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from context_output_cli_test_support import (
    REPO_ROOT,
    SAMPLE_DOC,
    cli,
    cli_args,
    cli_workspace,
    core,
)


class TestCLIOperations:
    def test_single_check_helper_maps_io_error(self, tmp_path, monkeypatch):
        _, _, detail_dir, index_path, _ = cli_workspace(tmp_path)
        monkeypatch.setattr(
            core,
            "check_generated_files",
            Mock(side_effect=OSError("read failed")),
        )

        args = cli_args(detail_dir=detail_dir, output=index_path)
        assert cli._run_single_check(args, SAMPLE_DOC, "details", core) == 3

    def test_single_check_helper_maps_runtime_error(self, tmp_path, monkeypatch):
        _, _, detail_dir, index_path, _ = cli_workspace(tmp_path)
        monkeypatch.setattr(
            core,
            "check_generated_files",
            Mock(side_effect=RuntimeError("repository unavailable")),
        )

        args = cli_args(detail_dir=detail_dir, output=index_path)
        assert cli._run_single_check(args, SAMPLE_DOC, "details", core) == 3

    def test_single_check_helper_maps_success_drift_and_path_error(self, tmp_path):
        _, _, detail_dir, index_path, _ = cli_workspace(tmp_path)
        args = cli_args(detail_dir=detail_dir, output=index_path)
        detail_ref = detail_dir.relative_to(REPO_ROOT).as_posix()
        assert cli._run_single_check(args, SAMPLE_DOC, detail_ref, core) == 0

        index_path.write_text("drift\n", encoding="utf-8")
        assert cli._run_single_check(args, SAMPLE_DOC, "details", core) == 1

        unsafe = cli_args(detail_dir=detail_dir, output=tmp_path / "outside.md")
        assert cli._run_single_check(unsafe, SAMPLE_DOC, "details", core) == 3

    def test_main_rejects_staged_without_manifest(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["extract_and_index.py", "--check", "--staged"])
        with pytest.raises(SystemExit) as error:
            cli.main(core)
        assert error.value.code == 2
