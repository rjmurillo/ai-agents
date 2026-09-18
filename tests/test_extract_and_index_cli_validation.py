"""Manifest validation tests for the context extractor CLI."""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent))

from context_output_cli_test_support import cli, cli_args, cli_workspace, core


class TestCLIManifestValidation:
    def test_helper_maps_success_drift_and_config(self, tmp_path, capsys):
        work_dir, _, _, index_path, manifest_path = cli_workspace(tmp_path)
        parser = cli._build_parser(core)
        args = cli_args(check=True, manifest=manifest_path)
        assert cli._check_manifest_cli(args, parser, core) == 0
        assert "Checked 1 source" in capsys.readouterr().err

        index_path.write_text("drift\n", encoding="utf-8")
        assert cli._check_manifest_cli(args, parser, core) == 1

        missing_args = cli_args(check=True, manifest=work_dir / "missing.json")
        assert cli._check_manifest_cli(missing_args, parser, core) == 2
        assert (
            cli._check_manifest_cli(
                cli_args(check=True, manifest=Path("/tmp/missing-manifest.json")),
                parser,
                core,
            )
            == 3
        )

    def test_helper_maps_runtime_error(self, tmp_path, monkeypatch):
        _, _, _, _, manifest_path = cli_workspace(tmp_path)
        monkeypatch.setattr(
            core,
            "check_manifest",
            Mock(side_effect=RuntimeError("index unavailable")),
        )
        parser = cli._build_parser(core)
        args = cli_args(check=True, manifest=manifest_path)
        assert cli._check_manifest_cli(args, parser, core) == 3
