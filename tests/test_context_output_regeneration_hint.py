"""Drift failures name the command that regenerates the context outputs."""

import shlex
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from context_output_cli_test_support import REPO_ROOT, cli, cli_args, cli_workspace, core
from test_extract_and_index import SCRIPT_PATH


@pytest.fixture(autouse=True)
def stub_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid network dependency from tiktoken in in-process tests."""
    monkeypatch.setattr("extract_and_index.count_tokens", lambda text: len(text.split()))


@pytest.fixture
def workspace(tmp_path):
    """Yield a generated document workspace and remove it afterwards."""
    values = cli_workspace(tmp_path)
    yield values
    shutil.rmtree(values[0], ignore_errors=True)


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


class TestRegenerationCommand:
    def test_names_script_and_every_path(self):
        command = cli.regeneration_command("AGENTS.md", "out/index.md", "out/details", "out/ref")
        command_parts = shlex.split(command)

        assert command_parts[3].endswith("/extract_and_index.py")
        assert Path(command_parts[3]).resolve() == SCRIPT_PATH.resolve()
        assert command_parts == [
            "uv",
            "run",
            "python",
            command_parts[3],
            "-i",
            "AGENTS.md",
            "-d",
            "out/details",
            "-r",
            "out/ref",
            "-o",
            "out/index.md",
        ]

    def test_script_is_relative_inside_the_working_directory(self, monkeypatch):
        monkeypatch.chdir(REPO_ROOT)

        script = shlex.split(cli.regeneration_command("a", "i", "d", "d"))[3]

        assert not Path(script).is_absolute()

    def test_script_is_absolute_outside_the_working_directory(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)

        script = shlex.split(cli.regeneration_command("a", "i", "d", "d"))[3]

        assert Path(script).is_absolute()
        assert Path(script).resolve() == SCRIPT_PATH.resolve()

    def test_quotes_paths_with_spaces(self):
        command = cli.regeneration_command("my docs/A.md", "o/i.md", "o/d", "o/d")

        assert shlex.split(command)[5] == "my docs/A.md"

    def test_accepts_path_objects(self):
        command = cli.regeneration_command(Path("a.md"), Path("i.md"), Path("d"), Path("d"))

        assert "-i a.md" in command


class TestPrintRegenerationHint:
    def test_silent_without_commands_or_extras(self, capsys):
        cli.print_regeneration_hint([], ["a.md: Detail drift: x"])

        assert capsys.readouterr().err == ""

    def test_lists_each_command(self, capsys):
        cli.print_regeneration_hint(["cmd one", "cmd two"], ["Detail drift: x"])

        err = capsys.readouterr().err
        assert "  cmd one" in err
        assert "  cmd two" in err
        assert "Delete each" not in err

    def test_extra_file_note_appears_without_commands(self, capsys):
        cli.print_regeneration_hint([], ["Extra context output: x"])

        assert "Delete each 'Extra' path" in capsys.readouterr().err

    def test_extra_detail_file_note_appears_with_commands(self, capsys):
        cli.print_regeneration_hint(["cmd"], ["src.md: Extra detail file: x"])

        err = capsys.readouterr().err
        assert "  cmd" in err
        assert "Delete each 'Extra' path" in err


class TestManifestCheckHint:
    def test_drift_prints_command_that_repairs_it(self, workspace, capsys):
        work_dir, source, detail_dir, index_path, manifest_path = workspace
        next(detail_dir.iterdir()).write_text("drift\n", encoding="utf-8")

        report = core.check_manifest(manifest_path)

        assert report.issues
        assert report.regenerate == [
            cli.regeneration_command(
                _rel(source), _rel(index_path), _rel(detail_dir), _rel(detail_dir)
            )
        ]
        cli.print_manifest_report(report)
        err = capsys.readouterr().err
        assert "Regenerate, then stage the rewritten outputs:" in err
        assert report.regenerate[0] in err

        args = shlex.split(report.regenerate[0])
        content = source.read_text(encoding="utf-8")
        core.extract_and_index(
            content, REPO_ROOT / args[args.index("-d") + 1], args[args.index("-r") + 1]
        )
        assert core.check_manifest(manifest_path).issues == []

    def test_clean_manifest_prints_no_hint(self, workspace, capsys):
        _, _, _, _, manifest_path = workspace

        report = core.check_manifest(manifest_path)
        cli.print_manifest_report(report)

        assert report.regenerate == []
        assert "Regenerate" not in capsys.readouterr().err

    def test_missing_source_has_no_command(self, workspace):
        _, source, _, _, manifest_path = workspace
        source.unlink()

        report = core.check_manifest(manifest_path)

        assert any("Missing source file" in issue for issue in report.issues)
        assert report.regenerate == []

    def test_extra_output_prints_cleanup_note_only(self, workspace, capsys):
        work_dir, _, _, _, manifest_path = workspace
        (work_dir / "output" / "stray.md").write_text("x\n", encoding="utf-8")

        report = core.check_manifest(manifest_path)
        cli.print_manifest_report(report)

        err = capsys.readouterr().err
        assert report.regenerate == []
        assert "Delete each 'Extra' path" in err


class TestSingleFileCheckHint:
    def test_drift_prints_command(self, workspace, capsys):
        _, source, detail_dir, index_path, _ = workspace
        index_path.write_text("drift\n", encoding="utf-8")
        args = cli_args(check=True, input=source, detail_dir=detail_dir, output=index_path)

        code = cli._run_single_check(
            args, source.read_text(encoding="utf-8"), _rel(detail_dir), core
        )

        err = capsys.readouterr().err
        assert code == 1
        assert cli.regeneration_command(source, index_path, detail_dir, _rel(detail_dir)) in err

    def test_clean_check_prints_no_hint(self, workspace, capsys):
        _, source, detail_dir, index_path, _ = workspace
        args = cli_args(check=True, input=source, detail_dir=detail_dir, output=index_path)

        code = cli._run_single_check(
            args, source.read_text(encoding="utf-8"), _rel(detail_dir), core
        )

        assert code == 0
        assert "Regenerate" not in capsys.readouterr().err
