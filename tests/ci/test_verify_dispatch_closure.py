"""Tests for scripts/ci/verify_dispatch_closure.py (ADR-101 Application B).

Each case builds a base repository holding the real dispatcher, a small config and
a verifier, then a separate head work tree, so the comparison is between two real
git trees and the head is only ever read.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from scripts.ci import verify_dispatch_closure as vdc  # noqa: E402

GATE = vdc.GATE
CONFIG = vdc.CONFIG
VERIFIER = ".claude/skills/demo/scripts/verify.py"
HELPER = ".claude/skills/demo/scripts/helper.py"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
    )


def _write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "base"
    base.mkdir()
    _git(base, "init", "-q")
    _git(base, "config", "user.email", "t@example.invalid")
    _git(base, "config", "user.name", "t")
    gate = base / GATE
    gate.parent.mkdir(parents=True, exist_ok=True)
    gate.write_bytes((_REPO_ROOT / GATE).read_bytes())
    config = {
        "scripts": {"claude_code": {"go": f"python3 {VERIFIER} --pull-request {{number}}"}},
        "completion_criteria": [],
    }
    _write(base, CONFIG, yaml.safe_dump(config))
    _write(base, VERIFIER, "import helper\n")
    _write(base, HELPER, "X = 1\n")
    _write(base, "README.md", "unrelated\n")
    _git(base, "add", "-A")
    _git(base, "commit", "-q", "-m", "base")
    head = tmp_path / "head"
    _git(base, "worktree", "add", "--detach", str(head), "HEAD")
    return base, head


def _run(trees: tuple[Path, Path]) -> vdc.Report:
    base, head = trees
    return vdc.verify(base, head, "HEAD")


class TestVerify:
    def test_an_identical_head_is_clean_and_reports_what_it_examined(
        self, trees: tuple[Path, Path]
    ) -> None:
        report = _run(trees)

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

        report = _run(trees)

        assert path in report.changed
        assert not report.clean

    @pytest.mark.parametrize("path", [GATE, CONFIG, VERIFIER])
    def test_a_deleted_dispatcher_config_or_verifier_is_reported_as_removed(
        self, trees: tuple[Path, Path], path: str
    ) -> None:
        _, head = trees
        (head / path).unlink()

        report = _run(trees)

        assert path in report.removed
        assert not report.clean

    def test_a_file_outside_the_closure_is_not_reported(self, trees: tuple[Path, Path]) -> None:
        _, head = trees
        (head / "README.md").write_text("edited\n", encoding="utf-8")

        assert _run(trees).clean

    def test_a_new_module_the_verifier_now_imports_is_reported_as_added(
        self, trees: tuple[Path, Path]
    ) -> None:
        _, head = trees
        (head / VERIFIER).write_text("import helper\nimport extra\n", encoding="utf-8")
        _write(head, ".claude/skills/demo/scripts/extra.py", "Y = 2\n")

        report = _run(trees)

        assert ".claude/skills/demo/scripts/extra.py" in report.added
        assert VERIFIER in report.changed

    def test_a_dynamic_load_added_in_the_head_is_reported(self, trees: tuple[Path, Path]) -> None:
        _, head = trees
        (head / VERIFIER).write_text("import sys\n__import__(sys.argv[1])\n", encoding="utf-8")

        report = _run(trees)

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
        _write(base, ".claude/skills/demo/scripts/dyn.py", "Z = 1\n")
        _git(base, "add", "-A")
        _git(base, "commit", "-q", "-m", "dynamic")
        (head / VERIFIER).write_text(loader, encoding="utf-8")
        _write(head, ".claude/skills/demo/scripts/dyn.py", "Z = 1\n")
        _git(head, "checkout", "--detach", "-q", "--force", _rev(base))
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

        report = _run(trees)

        assert not marker.exists()
        assert GATE in report.changed

    def test_a_ref_that_does_not_exist_reports_every_file_as_new(
        self, trees: tuple[Path, Path]
    ) -> None:
        base, head = trees

        report = vdc.verify(base, head, "refs/heads/nowhere")

        assert VERIFIER in report.added


def _rev(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


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
                str(_REPO_ROOT / "scripts/ci/verify_dispatch_closure.py"),
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
        report = vdc.verify(_REPO_ROOT, _REPO_ROOT, "HEAD")

        assert report.examined > 20
        assert report.unresolved == []


def _upstream_with_pr(base: Path, edit: dict[str, str], attributes: str = "") -> tuple[Path, str]:
    """A repository holding the base history plus one commit at refs/pull/1/head."""
    upstream = base.parent / "upstream"
    subprocess.run(
        ["git", "clone", "-q", str(base), str(upstream)], capture_output=True, check=True
    )
    _git(upstream, "config", "user.email", "t@example.invalid")
    _git(upstream, "config", "user.name", "t")
    for relative, body in edit.items():
        _write(upstream, relative, body)
    if attributes:
        (upstream / ".gitattributes").write_text(attributes, encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-q", "-m", "pull request")
    sha = _rev(upstream)
    _git(upstream, "update-ref", "refs/pull/1/head", sha)
    return upstream, sha


class TestMaterializeHead:
    def test_the_head_is_written_from_the_object_store_with_no_git_directory(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, sha = _upstream_with_pr(base, {HELPER: "X = 99\n"})
        dest = tmp_path / "out"

        vdc.materialize_head(base, 1, sha, dest, remote=str(upstream))

        assert (dest / HELPER).read_text(encoding="utf-8") == "X = 99\n"
        assert not (dest / ".git").exists()
        assert not (tmp_path / "out.index").exists()

    def test_export_ignore_in_the_heads_gitattributes_cannot_hide_a_file(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, sha = _upstream_with_pr(
            base, {HELPER: "X = 99\n"}, attributes=f"{HELPER} export-ignore\n"
        )
        dest = tmp_path / "out"

        vdc.materialize_head(base, 1, sha, dest, remote=str(upstream))

        assert (dest / HELPER).is_file()

    def test_a_head_that_moved_since_the_event_aborts(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, _sha = _upstream_with_pr(base, {HELPER: "X = 99\n"})

        with pytest.raises(vdc.DispatchClosureError, match="head moved"):
            vdc.materialize_head(base, 1, "a" * 40, tmp_path / "out", remote=str(upstream))

    @pytest.mark.parametrize("sha", ["", "HEAD", "abc", "A" * 40, "--upload-pack=x", "a" * 39])
    def test_a_malformed_sha_is_refused_before_any_git_call(
        self, trees: tuple[Path, Path], tmp_path: Path, sha: str
    ) -> None:
        base, _ = trees

        with pytest.raises(vdc.DispatchClosureError, match="not a full commit id"):
            vdc.materialize_head(base, 1, sha, tmp_path / "out")

    def test_a_missing_pull_request_ref_is_a_configuration_error(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, sha = _upstream_with_pr(base, {HELPER: "X = 99\n"})

        with pytest.raises(vdc.DispatchClosureError, match="fetch failed"):
            vdc.materialize_head(base, 7, sha, tmp_path / "out", remote=str(upstream))

    def test_every_git_call_reading_the_head_carries_the_inert_configuration(
        self, trees: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base, _ = trees
        upstream, sha = _upstream_with_pr(base, {HELPER: "X = 99\n"})
        calls: list[list[str]] = []
        real = subprocess.run

        def record(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(list(argv))
            return real(argv, **kwargs)

        monkeypatch.setattr(vdc.subprocess, "run", record)

        vdc.materialize_head(base, 1, sha, tmp_path / "out", remote=str(upstream))

        git_calls = [c for c in calls if c[0] == "git"]
        assert [c[c.index("core.fsmonitor=false") - 1] for c in git_calls] == ["-c"] * len(
            git_calls
        )
        assert all("core.hooksPath=/dev/null" in c for c in git_calls)
        assert {c[5] for c in git_calls} == {"fetch", "rev-parse", "read-tree", "checkout-index"}

    def test_main_verifies_a_head_it_fetched_itself(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = _upstream_with_pr(base, {HELPER: "X = 99\n"})

        code = vdc.main(
            [
                "--tool-root",
                str(base),
                "--head-sha",
                sha,
                "--pull-number",
                "1",
                "--remote",
                str(upstream),
                "--json",
            ]
        )

        assert code == vdc.EXIT_DIFFERS
        assert json.loads(capsys.readouterr().out)["changed"] == [HELPER]

    @pytest.mark.parametrize(
        "extra",
        [[], ["--head-sha", "a" * 40], ["--pull-number", "1"]],
    )
    def test_main_needs_a_head_root_or_a_sha_and_a_number(
        self, trees: tuple[Path, Path], extra: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees

        code = vdc.main(["--tool-root", str(base), *extra])

        assert code == vdc.EXIT_CONFIG
        assert "give --head-root" in capsys.readouterr().err
