"""Tests for scripts/ci/verify_dispatch_closure.py (ADR-101 Application B).

Each case builds a base repository holding the real dispatcher, a small config and
a verifier, then a separate head work tree, so the comparison is between two real
git trees and the head is only ever read.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.ci.dispatch_closure_helpers import (  # noqa: F401
    CONFIG,
    GATE,
    HELPER,
    REPO_ROOT,
    VERIFIER,
    git,
    rev,
    run,
    upstream_with_pr,
    vdc,
    write,
)


class TestVerify:
    def test_an_identical_head_is_clean_and_reports_what_it_examined(
        self, trees: tuple[Path, Path]
    ) -> None:
        report = run(trees)

        # The dispatcher, its config, the verifier the config names, and the
        # module that verifier imports.
        assert report.clean
        assert report.examined == 4

    @pytest.mark.parametrize("path", [GATE, CONFIG, VERIFIER, HELPER])
    def test_a_rewritten_dispatcher_config_verifier_or_import_is_reported(
        self, trees: tuple[Path, Path], path: str
    ) -> None:
        _, head = trees
        with (head / path).open("a", encoding="utf-8") as handle:
            handle.write("\n# edited by the pull request\n")

        report = run(trees)

        assert path in report.changed
        assert not report.clean

    @pytest.mark.parametrize("path", [GATE, CONFIG, VERIFIER])
    def test_a_deleted_dispatcher_config_or_verifier_is_reported_as_removed(
        self, trees: tuple[Path, Path], path: str
    ) -> None:
        _, head = trees
        (head / path).unlink()

        report = run(trees)

        assert path in report.removed
        assert not report.clean

    def test_a_file_outside_the_closure_is_not_reported(self, trees: tuple[Path, Path]) -> None:
        _, head = trees
        (head / "README.md").write_text("edited\n", encoding="utf-8")

        assert run(trees).clean

    def test_a_new_module_the_verifier_now_imports_is_reported_as_added(
        self, trees: tuple[Path, Path]
    ) -> None:
        _, head = trees
        (head / VERIFIER).write_text("import helper\nimport extra\n", encoding="utf-8")
        write(head, ".claude/skills/demo/scripts/extra.py", "Y = 2\n")

        report = run(trees)

        assert ".claude/skills/demo/scripts/extra.py" in report.added
        assert VERIFIER in report.changed

    def test_a_dynamic_load_added_in_the_head_is_reported(self, trees: tuple[Path, Path]) -> None:
        _, head = trees
        (head / VERIFIER).write_text("import sys\n__import__(sys.argv[1])\n", encoding="utf-8")

        report = run(trees)

        assert any("unresolvable dynamic load" in item for item in report.unresolved)

    def test_a_resolvable_dynamic_load_joins_the_compared_closure(
        self, trees: tuple[Path, Path]
    ) -> None:
        base, head = trees
        loader = (
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('m', Path(__file__).parent / 'dyn.py')\n"
        )
        (base / VERIFIER).write_text(loader, encoding="utf-8")
        write(base, ".claude/skills/demo/scripts/dyn.py", "Z = 1\n")
        git(base, "add", "-A")
        git(base, "commit", "-q", "-m", "dynamic")
        (head / VERIFIER).write_text(loader, encoding="utf-8")
        write(head, ".claude/skills/demo/scripts/dyn.py", "Z = 1\n")
        git(head, "checkout", "--detach", "-q", "--force", rev(base))
        (head / ".claude/skills/demo/scripts/dyn.py").write_text("Z = 99\n", encoding="utf-8")

        report = vdc.verify(base, head, "HEAD")

        assert ".claude/skills/demo/scripts/dyn.py" in report.changed

    def test_the_head_is_read_as_data_its_code_never_runs(self, trees: tuple[Path, Path]) -> None:
        _, head = trees
        marker = head.parent / "ran.txt"
        (head / VERIFIER).write_text(
            f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n", encoding="utf-8"
        )
        (head / GATE).write_text(
            f"import pathlib\npathlib.Path({str(marker)!r}).write_text('gate ran')\n",
            encoding="utf-8",
        )

        report = run(trees)

        assert not marker.exists()
        assert GATE in report.changed

    def test_a_ref_that_does_not_exist_reports_every_file_as_new(
        self, trees: tuple[Path, Path]
    ) -> None:
        base, head = trees

        report = vdc.verify(base, head, "refs/heads/nowhere")

        assert VERIFIER in report.added


class TestErrors:
    def test_a_base_without_the_dispatcher_is_a_configuration_error(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()

        with pytest.raises(vdc.DispatchClosureError, match="dispatcher not found"):
            vdc.verify(empty, empty, "HEAD")

    def test_a_dispatcher_that_raises_on_import_is_a_configuration_error(
        self, trees: tuple[Path, Path]
    ) -> None:
        base, head = trees
        (base / GATE).write_text("raise RuntimeError('broken')\n", encoding="utf-8")

        with pytest.raises(vdc.DispatchClosureError, match="does not load"):
            vdc.verify(base, head, "HEAD")

    @pytest.mark.parametrize("body", ["k: [unclosed\n", "- a\n- b\n"])
    def test_an_unreadable_or_non_mapping_base_config_is_a_configuration_error(
        self, trees: tuple[Path, Path], body: str
    ) -> None:
        base, head = trees
        (base / CONFIG).write_text(body, encoding="utf-8")

        with pytest.raises(vdc.DispatchClosureError, match="base config"):
            vdc.verify(base, head, "HEAD")

    def test_a_missing_base_config_is_a_configuration_error(self, trees: tuple[Path, Path]) -> None:
        base, head = trees
        (base / CONFIG).unlink()

        with pytest.raises(vdc.DispatchClosureError, match="cannot be read"):
            vdc.verify(base, head, "HEAD")

    def test_a_config_command_that_is_not_a_command_line_is_a_configuration_error(
        self, trees: tuple[Path, Path]
    ) -> None:
        base, head = trees
        config = {"completion_criteria": [{"name": "x", "verification": "manual"}]}
        (base / CONFIG).write_text(yaml.safe_dump(config), encoding="utf-8")

        with pytest.raises(vdc.DispatchClosureError, match="cannot be classified"):
            vdc.verify(base, head, "HEAD")


class TestMain:
    def _args(self, trees: tuple[Path, Path], *extra: str) -> list[str]:
        base, head = trees
        return ["--tool-root", str(base), "--head-root", str(head), *extra]

    def test_clean_exits_zero(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = vdc.main(self._args(trees))

        assert code == vdc.EXIT_OK
        assert "0 differ" in capsys.readouterr().out

    def test_a_difference_exits_one_and_advisory_exits_zero(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, head = trees
        (head / HELPER).write_text("X = 2\n", encoding="utf-8")

        strict = vdc.main(self._args(trees))
        advisory = vdc.main(self._args(trees, "--advisory"))

        assert (strict, advisory) == (vdc.EXIT_DIFFERS, vdc.EXIT_OK)
        assert f"DIFFERS {HELPER}" in capsys.readouterr().out

    def test_json_output_names_each_category(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, head = trees
        (head / HELPER).write_text("X = 2\n", encoding="utf-8")

        vdc.main(self._args(trees, "--json", "--advisory"))

        document = json.loads(capsys.readouterr().out)
        assert document["changed"] == [HELPER]
        assert document["removed"] == document["added"] == document["unresolved"] == []

    def test_a_configuration_error_exits_two_even_when_advisory(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = vdc.main(["--tool-root", str(tmp_path), "--head-root", str(tmp_path), "--advisory"])

        assert code == vdc.EXIT_CONFIG
        assert "ERROR" in capsys.readouterr().err

    def test_a_name_that_cannot_be_encoded_is_escaped(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        _, head = trees
        (head / VERIFIER).write_text("import helper\n__import__(input())\n", encoding="utf-8")

        vdc.main(self._args(trees, "--advisory"))

        assert capsys.readouterr().out.isascii()

    def test_the_script_runs_as_a_process(self, trees: tuple[Path, Path]) -> None:
        base, head = trees
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/ci/verify_dispatch_closure.py"),
                "--tool-root",
                str(base),
                "--head-root",
                str(head),
            ],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )

        assert result.returncode == 0
        assert "dispatch-closure:" in result.stdout


class TestTheRepositoryItself:
    def test_this_checkout_against_its_own_head_is_clean(self) -> None:
        report = vdc.verify(REPO_ROOT, REPO_ROOT, "HEAD")

        assert report.examined > 20
        assert report.unresolved == []
