"""Edge paths of the ship scripts that the behavior suites do not reach."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from tests.skills.ship.conftest import git
from tests.skills.ship.ship_helpers import (
    SCRIPTS,
    approved_ado_build,
    invoke,
    symlink_or_skip,
    values,
)

GITHUB = "https://github.com/rjmurillo/ai-agents.git"
ADO = "https://dev.azure.com/contoso/p/_git/r"
TITLE = "feat(ship): add the driver"
MERGE = "m" * 40


@pytest.mark.parametrize(
    ("script", "argv", "terminal"),
    [
        ("ship_detect.py", [], "NEXT: preflight"),
        ("ship_preflight.py", ["--check", "tree"], "NEXT: write-body"),
        ("ship_pr.py", ["branch", "--name", "BAD"], "STOP: bad-branch-name"),
    ],
)
def test_script_runs_under_isolated_mode(make_repo, fakes, script, argv, terminal):
    """Each script loads its siblings by path and runs its main guard under python3 -I."""
    repo = make_repo(GITHUB)
    fakes.no_pr_github()
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS / script), *argv, "--output-format", "human"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = done.stdout.splitlines()
    assert lines[-1].startswith(terminal), done.stderr
    assert sum(line.startswith(("NEXT:", "STOP:")) for line in lines) == 1
    assert (done.returncode == 0) == lines[-1].startswith("NEXT:")


class TestCommonEdges:
    def test_long_stop_detail_spills_lines_that_fit_the_budget(self, scripts, tmp_path):
        common = scripts[0]
        result = common.Result("t.py", frozenset({"x-failed"}))
        for index in range(40):
            result.add("ITEM", f"{index:02d}" + "y" * 1000)
        result.stop("x-failed", 1, "z" * 2500)
        text = common.render(result, "human", tmp_path)
        lines = text.splitlines()
        assert len(text.encode("utf-8")) <= common.MAX_BYTES
        assert any(line.startswith("DETAIL_FILE: ") for line in lines)
        assert lines[-1] == "STOP: x-failed " + "z" * (common.MAX_DETAIL_CHARS - 3) + "..."

    @pytest.mark.parametrize("output_format", ["json", "human"])
    def test_non_ascii_and_quote_heavy_output_stays_under_the_cap(
        self, scripts, tmp_path, output_format
    ):
        common = scripts[0]
        result = common.Result("t.py", frozenset({"x-failed"}))
        for _index in range(200):
            result.add("FINDING", "\u00e9" * 150 + '"\\' * 75)
        result.stop("x-failed", 1, "d")
        text = common.render(result, output_format, tmp_path)
        assert len(text.encode("utf-8")) <= common.MAX_BYTES
        if output_format == "json":
            envelope = json.loads(text)
            assert "DETAIL_FILE" in envelope["Data"]
            assert envelope["Error"]["Code"] == 1

    def test_scratch_mkdir_failure_is_refused(self, scripts, tmp_path):
        common = scripts[0]
        root = tmp_path / "ro"
        root.mkdir()
        root.chmod(0o500)
        try:
            assert common.scratch_dir(root, create=True) is None
        finally:
            root.chmod(0o700)

    def test_existing_scratch_without_create(self, scripts, tmp_path):
        common = scripts[0]
        assert common.scratch_dir(tmp_path) is None
        assert (
            common.scratch_dir(tmp_path, create=True) == (tmp_path / common.SCRATCH_REL).resolve()
        )
        assert common.scratch_dir(tmp_path) == (tmp_path / common.SCRATCH_REL).resolve()

    def test_scratch_resolve_failure_is_refused(self, scripts, tmp_path, monkeypatch):
        common = scripts[0]
        (tmp_path / common.SCRATCH_REL).mkdir(parents=True)
        real = common.Path.resolve
        calls = {"n": 0}

        def flaky(self, strict=False):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("gone")
            return real(self, strict=strict)

        monkeypatch.setattr(common.Path, "resolve", flaky)
        assert common.scratch_dir(tmp_path) is None

    def test_scratch_resolving_elsewhere_is_refused(self, scripts, tmp_path, monkeypatch):
        common = scripts[0]
        (tmp_path / common.SCRATCH_REL).mkdir(parents=True)
        real = common.Path.resolve

        def moved(self, strict=False):
            resolved = real(self, strict=strict)
            return resolved.parent / "elsewhere" if resolved.name == "scratch" else resolved

        monkeypatch.setattr(common.Path, "resolve", moved)
        assert common.scratch_dir(tmp_path) is None

    def test_write_private_open_failure(self, scripts, tmp_path, monkeypatch):
        common = scripts[0]

        def refuse(*args, **kwargs):
            raise OSError("no")

        monkeypatch.setattr(common.os, "open", refuse)
        assert common.write_private(tmp_path, "p", ".md", "x") is None


class TestDetectEdges:
    def test_unsafe_origin_head_falls_back_to_main(self, make_repo, fakes, scripts, capsys):
        repo = make_repo(GITHUB)
        git(repo, "update-ref", "refs/remotes/origin/a+b", "HEAD")
        git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/a+b")
        fakes.no_pr_github()
        _code, lines = invoke(scripts[1], [], capsys)
        assert values(lines, "BASE") == ["main"]


class TestPrEdges:
    def test_windows_prepare_without_a_template(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        repo = make_repo(GITHUB)
        monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
        code, lines = invoke(scripts[3], ["prepare"], capsys)
        assert code == 0
        body = repo / values(lines, "BODY_FILE")[0]
        assert body.read_text(encoding="utf-8") == "<!-- replace with PR body -->\n"

    def test_windows_prepare_stops_on_an_unsafe_scratch(
        self, make_repo, fakes, scripts, capsys, monkeypatch
    ):
        make_repo(GITHUB)
        monkeypatch.setattr(scripts[0], "on_windows", lambda: True)
        monkeypatch.setattr(scripts[0], "write_private", lambda *args, **kwargs: None)
        code, lines = invoke(scripts[3], ["prepare"], capsys)
        assert code == 2
        assert lines[-1] == "STOP: prepare-failed scratch directory is unsafe"

    def test_publish_git_status_failure_stops(
        self, make_repo, fakes, scripts, capsys, body_file, monkeypatch
    ):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        body = body_file(repo)
        common = scripts[0]
        real_git = common.git

        def broken(args, cwd=None, timeout=60, **kw):
            if args[:1] == ["status"]:
                return common.Completed(128, "", "fatal")
            return real_git(args, cwd=cwd, timeout=timeout, **kw)

        monkeypatch.setattr(common, "git", broken)
        code, lines = invoke(
            scripts[3],
            ["publish", "--paths-checked-by-hand", "--title", TITLE, "--body-file", str(body)],
            capsys,
        )
        assert code == 2
        assert lines[-1].startswith("STOP: no-repo")

    @pytest.mark.parametrize(
        "command", [["prepare"], ["check", "--title", TITLE, "--body-file", "x"]]
    )
    def test_unsafe_base_value_stops(self, make_repo, fakes, scripts, capsys, command):
        make_repo(GITHUB)
        code, lines = invoke(scripts[3], [*command, "--base=a..b"], capsys)
        assert code == 2
        assert lines[-1] == "STOP: bad-arguments --base is not a plain ref"


class TestPreflightEdges:
    def test_unsafe_base_value_stops(self, make_repo, fakes, scripts, capsys):
        make_repo(GITHUB)
        code, lines = invoke(scripts[2], ["--check", "tree", "--base=a..b"], capsys)
        assert code == 2
        assert lines[-1] == "STOP: bad-arguments --base is not a plain ref"

    def test_github_second_head_query_failure_stops(self, make_repo, fakes, scripts, capsys):
        repo = make_repo(GITHUB)
        fakes.no_pr_github()
        head = git(repo, "rev-parse", "HEAD")
        fakes.rule(
            "gh",
            ["pr", "view", "41"],
            {
                "stdout": json.dumps(
                    {
                        "headRefName": "feat/ship-change",
                        "headRefOid": head,
                        "url": "https://github.com/o/r/pull/41",
                    }
                )
            },
            {"rc": 1, "stderr": "HTTP 502\n"},
        )
        fakes.rule(
            "get_pr_checks",
            [],
            {
                "stdout": json.dumps({"Data": {"RequiredState": "SUCCESS", "AllPassing": True}})
                + "\n"
            },
        )
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--pr", "41"], capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: checks-query-failed")

    def test_ado_second_show_failure_stops(self, make_repo, fakes, scripts, capsys):
        repo = make_repo(ADO)
        fakes.rule(
            "az",
            ["repos", "pr", "list"],
            {
                "stdout": json.dumps(
                    [
                        {
                            "pullRequestId": 77,
                            "targetRefName": "refs/heads/main",
                            "createdBy": {"uniqueName": "me"},
                        }
                    ]
                )
            },
        )
        fakes.rule("az", ["account", "show"], {"stdout": "me\n"})
        state = {
            "source": "refs/heads/feat/ship-change",
            "head": git(repo, "rev-parse", "HEAD"),
            "merge": MERGE,
        }
        fakes.rule(
            "az",
            ["repos", "pr", "show"],
            {"stdout": json.dumps(state)},
            {"rc": 1, "stderr": "TF000\n"},
        )
        approved_ado_build(fakes, MERGE)
        code, lines = invoke(scripts[2], ["--check", "pipeline", "--wait-seconds", "0"], capsys)
        assert code == 3
        assert lines[-1].startswith("STOP: pipeline-query-failed")


@pytest.mark.parametrize("script", ["ship_detect.py", "ship_preflight.py", "ship_pr.py"])
def test_symlinked_entry_uses_its_real_sibling(tmp_path, script):
    entry = tmp_path / script
    symlink_or_skip(entry, SCRIPTS / script)
    done = subprocess.run(
        [sys.executable, "-I", str(entry), "--output-format", "human"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 2
    assert done.stdout.splitlines()[-1].startswith("STOP:")
    assert not done.stderr
