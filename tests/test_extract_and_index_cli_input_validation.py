"""Input and dispatch tests for the context extractor CLI."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from context_output_cli_test_support import (
    SAMPLE_DOC,
    cli,
    cli_args,
    cli_workspace,
    core,
)


class TestCLIInputValidation:
    def test_read_input_requires_output_and_reads_valid(self, tmp_path):
        _, source, detail_dir, _, _ = cli_workspace(tmp_path)
        parser = cli._build_parser(core)
        with pytest.raises(SystemExit) as error:
            cli._read_input(cli_args(), parser, core)
        assert error.value.code == 2

        with pytest.raises(SystemExit):
            cli._read_input(
                cli_args(check=True, input=source, detail_dir=detail_dir),
                parser,
                core,
            )

        content, detail_ref = cli._read_input(
            cli_args(input=source, detail_dir=detail_dir, detail_ref="custom/details"),
            parser,
            core,
        )
        assert content == SAMPLE_DOC
        assert detail_ref == "custom/details"

        def raise_os_error(*args, **kwargs):
            raise OSError("read failed")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(Path, "read_text", raise_os_error)
        try:
            with pytest.raises(SystemExit) as error:
                cli._read_input(
                    cli_args(input=source, detail_dir=detail_dir),
                    parser,
                    core,
                )
            assert error.value.code == 1
        finally:
            monkeypatch.undo()

    def test_read_input_maps_missing_and_unsafe_paths(self, tmp_path):
        parser = cli._build_parser(core)
        missing = cli_args(input=Path("/nonexistent/context.md"), detail_dir=Path("."))
        with pytest.raises(SystemExit) as error:
            cli._read_input(missing, parser, core)
        assert error.value.code == 1

        outside = tmp_path / "context.md"
        outside.write_text(SAMPLE_DOC, encoding="utf-8")
        unsafe = cli_args(input=outside, detail_dir=Path("."))
        with pytest.raises(SystemExit) as error:
            cli._read_input(unsafe, parser, core)
        assert error.value.code == 3
