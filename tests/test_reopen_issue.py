"""Tests for reopen_issue.py skill script (issue #2475)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1] / ".claude" / "skills" / "github" / "scripts" / "issue"
)


def _import_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _import_script("reopen_issue")
main = _mod.main

pytestmark = pytest.mark.usefixtures("stub_git_probes")
build_parser = _mod.build_parser


def _completed(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def _state_open():
    return _completed(stdout=json.dumps({"state": "OPEN"}), rc=0)


def _state_closed():
    return _completed(stdout=json.dumps({"state": "CLOSED"}), rc=0)


def _paginated_comments(*pages: list[str]):
    return _completed(
        stdout=json.dumps([[{"body": body} for body in page] for page in pages]),
        rc=0,
    )


def _envelope(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


class TestBuildParser:
    def test_issue_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_comment_and_comment_file_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--issue", "5", "--comment", "x", "--comment-file", "f.txt"])


class TestCommentBaseDir:
    def test_uses_git_root_from_current_working_directory(self, monkeypatch):
        repo = Path("workspace-repo").resolve()
        nested = repo / "nested"
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
        with (
            patch("reopen_issue.Path.cwd", return_value=nested),
            patch("reopen_issue._find_git_root", return_value=repo),
        ):
            assert _mod._comment_base_dir() == repo

    def test_defaults_to_current_working_directory_without_git_root(self, monkeypatch):
        expected = Path("workspace-repo")
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
        with (
            patch("reopen_issue.Path.cwd", return_value=expected),
            patch("reopen_issue._find_git_root", return_value=None),
        ):
            assert _mod._comment_base_dir() == expected.resolve()


class TestMain:
    def test_not_authenticated_exits_4(self):
        with patch("reopen_issue.assert_gh_authenticated", side_effect=SystemExit(4)):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "1"])
            assert exc.value.code == 4

    def test_reopen_success_no_comment(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[_state_closed(), _completed(stdout="reopened", rc=0)],
            ) as mock_run,
        ):
            rc = main(["--issue", "50"])
        assert rc == 0
        env = _envelope(capsys)
        assert env["Success"] is True
        assert env["Error"] is None
        assert env["Metadata"]["Script"] == "reopen_issue.py"
        data = env["Data"]
        assert data["issue"] == 50
        assert data["state"] == "open"
        assert data["action"] == "reopened"
        assert data["commented"] is False
        assert mock_run.call_count == 2
        reopen_args = mock_run.call_args_list[1].args[0]
        assert reopen_args[:3] == ["gh", "issue", "reopen"]

    def test_subprocesses_read_utf8(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[_state_open(), _paginated_comments(["old"]), _completed()],
            ) as mock_run,
        ):
            rc = main(["--issue", "7", "--comment", "new"])

        assert rc == 0
        _envelope(capsys)
        assert all(call.kwargs.get("encoding") == "utf-8" for call in mock_run.call_args_list)

    def test_already_open_is_noop(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=[_state_open()]) as mock_run,
        ):
            rc = main(["--issue", "7"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["action"] == "already_open"
        assert data["state"] == "open"
        # Only the state check ran; no reopen call.
        assert mock_run.call_count == 1

    def test_reopen_with_comment_reopens_then_comments(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[
                    _state_closed(),
                    _completed(stdout="reopened", rc=0),
                    _completed(stdout="{}", rc=0),
                ],
            ) as mock_run,
        ):
            rc = main(["--issue", "9", "--comment", "Reopened: maintainer kept open"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["commented"] is True
        assert mock_run.call_count == 3

    def test_already_open_posts_missing_comment(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[
                    _state_open(),
                    _paginated_comments(["unrelated"]),
                    _completed(stdout="{}", rc=0),
                ],
            ) as mock_run,
        ):
            rc = main(["--issue", "9", "--comment", "new note"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["action"] == "already_open"
        assert data["commented"] is True
        assert mock_run.call_count == 3

    def test_already_open_skips_duplicate_comment(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[_state_open(), _paginated_comments(["dup"])],
            ) as mock_run,
        ):
            rc = main(["--issue", "9", "--comment", "dup"])
        assert rc == 0
        data = _envelope(capsys)["Data"]
        assert data["commented"] is False
        assert data["commentAlreadyPresent"] is True
        # State check + comment list, no POST.
        assert mock_run.call_count == 2

    def test_reopen_api_failure_returns_3(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[_state_closed(), _completed(stderr="server error", rc=1)],
            ),
        ):
            rc = main(["--issue", "9"])
        assert rc == 3
        env = _envelope(capsys)
        assert env["Success"] is False

    def test_not_found_returns_2(self, capsys):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch(
                "subprocess.run",
                side_effect=[_completed(stderr="Could not resolve to an Issue", rc=1)],
            ),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "999"])
            assert exc.value.code == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


class TestCommentFileContainment:
    """--comment-file follows the shared containment rule (issue #6667)."""

    @staticmethod
    def _reopen(argv, side_effect):
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch(
                "reopen_issue.resolve_repo_params",
                return_value=RepoInfo(owner="o", repo="r"),
            ),
            patch("subprocess.run", side_effect=side_effect) as mock_run,
        ):
            return mock_run, main(argv)

    def test_scratchpad_comment_file_under_temp_dir_reopens(self, tmp_path, capsys, monkeypatch):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        scratch = tmp_path / "claude-1000" / "scratchpad"
        scratch.mkdir(parents=True)
        body = scratch / "reopen.md"
        body.write_text("Reopening from scratchpad.", encoding="utf-8")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        mock_run, rc = self._reopen(
            ["--issue", "9", "--comment-file", str(body)],
            [_state_closed(), _completed(stdout="reopened"), _completed(stdout="{}")],
        )
        assert rc == 0
        assert _envelope(capsys)["Data"]["commented"] is True
        post_input = mock_run.call_args_list[2].kwargs["input"]
        assert json.loads(post_input)["body"] == "Reopening from scratchpad."

    def test_relative_comment_file_inside_workspace_reopens(self, tmp_path, capsys, monkeypatch):
        body = tmp_path / "note.md"
        body.write_text("Relative note.", encoding="utf-8")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        mock_run, rc = self._reopen(
            ["--issue", "9", "--comment-file", "note.md"],
            [_state_closed(), _completed(stdout="reopened"), _completed(stdout="{}")],
        )
        assert rc == 0
        post_input = mock_run.call_args_list[2].kwargs["input"]
        assert json.loads(post_input)["body"] == "Relative note."

    def test_comment_file_outside_every_root_exits_2(self, external_tmp_path, capsys, monkeypatch):
        work = external_tmp_path / "work"
        work.mkdir()
        outside = external_tmp_path / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(work))
        monkeypatch.delenv("TMPDIR", raising=False)
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch("reopen_issue.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", return_value=_state_closed()) as mock_run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "9", "--comment-file", str(outside)])
            assert exc.value.code == 2
        mock_run.assert_not_called()
        env = _envelope(capsys)
        assert env["Success"] is False
        assert env["Error"]["Type"] == "InvalidParams"
        assert "Comment file must be under" in env["Error"]["Message"]

    def test_symlink_in_temp_dir_pointing_outside_exits_2(
        self, tmp_path, external_tmp_path, capsys, monkeypatch
    ):
        target = external_tmp_path / "secret.md"
        target.write_text("secret", encoding="utf-8")
        link = tmp_path / "link.md"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlinks unavailable")
        work = external_tmp_path / "work"
        work.mkdir()
        monkeypatch.setenv("GITHUB_WORKSPACE", str(work))
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch("reopen_issue.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", return_value=_state_closed()),
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "9", "--comment-file", str(link)])
            assert exc.value.code == 2

    def test_missing_comment_file_exits_2(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        with (
            patch("reopen_issue.assert_gh_authenticated"),
            patch("reopen_issue.resolve_repo_params", return_value=RepoInfo(owner="o", repo="r")),
            patch("subprocess.run", return_value=_state_closed()) as mock_run,
        ):
            with pytest.raises(SystemExit) as exc:
                main(["--issue", "9", "--comment-file", "missing.md"])
            assert exc.value.code == 2
        mock_run.assert_not_called()
        assert _envelope(capsys)["Error"]["Type"] == "NotFound"
