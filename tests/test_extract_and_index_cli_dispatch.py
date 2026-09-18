"""Parser and dispatch tests for the context extractor CLI."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from context_output_cli_test_support import REPO_ROOT, cli, cli_args, cli_workspace, core


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


class TestCLIDispatch:
    def test_parser_rejects_invalid_manifest_modes(self):
        parser = cli._build_parser(core)
        with pytest.raises(SystemExit):
            cli._check_manifest_cli(cli_args(manifest=Path("manifest.json")), parser, core)
        with pytest.raises(SystemExit):
            cli._check_manifest_cli(
                cli_args(check=True, manifest=Path("manifest.json"), input=Path("source.md")),
                parser,
                core,
            )

    def test_main_dispatches_manifest_and_single_file_checks(self, tmp_path, monkeypatch):
        _, source, detail_dir, index_path, manifest_path = cli_workspace(tmp_path)
        monkeypatch.setattr(
            sys,
            "argv",
            ["extract_and_index.py", "--check", "--manifest", str(manifest_path)],
        )
        with pytest.raises(SystemExit) as error:
            cli.main(core)
        assert error.value.code == 0

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "extract_and_index.py",
                "--check",
                "-i",
                str(source),
                "-d",
                str(detail_dir),
                "-r",
                detail_dir.relative_to(REPO_ROOT).as_posix(),
                "-o",
                str(index_path),
            ],
        )
        with pytest.raises(SystemExit) as error:
            cli.main(core)
        assert error.value.code == 0
