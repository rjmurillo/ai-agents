"""Preflight and origin-branch checks for ``new_pr.py`` (issue #6424)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests import new_pr_harness
from tests.containment_fixtures import private_dir
from tests.new_pr_harness import completed, main, new_pr

_pr_val = new_pr._pr_val

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**_GIT_ENV, "PATH": os.environ["PATH"], "HOME": str(cwd)},
    )


@pytest.fixture
def clone_with_origin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A clone whose origin is a local bare repository holding only ``main``."""
    bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(bare))
    _git(tmp_path, "init", "--initial-branch=main", str(work))
    (work / "a.txt").write_text("a", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", "init")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "origin", "main")
    monkeypatch.chdir(work)
    return work


class TestHeadOnOrigin:
    def test_true_for_a_pushed_branch(self, clone_with_origin: Path) -> None:
        assert _pr_val.head_on_origin("main") is True

    def test_false_for_a_branch_origin_lacks(self, clone_with_origin: Path) -> None:
        _git(clone_with_origin, "branch", "feat/local-only")

        assert _pr_val.head_on_origin("feat/local-only") is False

    def test_a_suffix_of_a_pushed_branch_is_not_a_match(self, clone_with_origin: Path) -> None:
        _git(clone_with_origin, "branch", "feat/x")
        _git(clone_with_origin, "push", "origin", "feat/x")

        assert _pr_val.head_on_origin("feat/x") is True
        assert _pr_val.head_on_origin("x") is False

    def test_a_head_that_looks_like_an_option_is_a_plain_miss(
        self, clone_with_origin: Path
    ) -> None:
        assert _pr_val.head_on_origin("--upload-pack=true") is False

    def test_a_ref_that_only_ends_with_the_head_is_not_a_match(
        self, clone_with_origin: Path
    ) -> None:
        """``ls-remote`` matches the tail of a ref, so ``x/refs/heads/main`` answers ``main``."""
        _git(clone_with_origin, "branch", "evil/refs/heads/target")
        _git(clone_with_origin, "push", "origin", "evil/refs/heads/target")

        assert _pr_val.head_on_origin("target") is False
        assert _pr_val.head_on_origin("evil/refs/heads/target") is True

    def test_a_glob_head_is_refused_without_a_git_call(self) -> None:
        with patch("subprocess.run", side_effect=AssertionError("git must not run")):
            assert _pr_val.head_on_origin("feat/*") is False
            assert _pr_val.head_on_origin("feat/[a-z]") is False

    def test_none_when_origin_cannot_be_read(self, clone_with_origin: Path) -> None:
        _git(clone_with_origin, "remote", "set-url", "origin", str(clone_with_origin / "gone.git"))

        assert _pr_val.head_on_origin("main") is None

    def test_none_when_git_times_out(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=60),
        ):
            assert _pr_val.head_on_origin("feat/x") is None

    def test_none_when_git_is_missing(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError("git")):
            assert _pr_val.head_on_origin("feat/x") is None


_LEGAL_NAMES = [
    "main",
    "feat/x",
    "fix/6506-input",
    "release-1.2",
    "a.b",
    "user/feat_x",
    "@x",
    "a@b",
    "head",
    "HEAD2",
    "feat/HEAD",
]
_ILLEGAL_NAMES = [
    "",
    "@",
    "HEAD",
    "-x",
    "--upload-pack=true",
    "a b",
    "a\tb",
    "a\nb",
    "a\x7fb",
    "a*",
    "a?b",
    "a[b",
    "a\\b",
    "a~1",
    "a^",
    "a:b",
    "a..b",
    "a@{u}",
    "a//b",
    "/a",
    "a/",
    "a.",
    ".a",
    "a/.b",
    "a.lock",
    "a.lock/b",
]


class TestIsValidBranchName:
    @pytest.mark.parametrize("name", _LEGAL_NAMES)
    def test_accepts_legal_names(self, name: str) -> None:
        assert _pr_val.is_valid_branch_name(name) is True

    @pytest.mark.parametrize("name", _ILLEGAL_NAMES)
    def test_rejects_names_git_refuses(self, name: str) -> None:
        assert _pr_val.is_valid_branch_name(name) is False

    # ``check-ref-format --branch @`` exits 0 because ``@`` expands to HEAD, but
    # ``git branch @`` refuses it, so ``@`` stays rejected and out of this table.
    @pytest.mark.parametrize(
        "name", [*_LEGAL_NAMES, *[n for n in _ILLEGAL_NAMES if n not in {"", "@"}]]
    )
    def test_agrees_with_git_check_ref_format(self, name: str, tmp_path: Path) -> None:
        git = subprocess.run(
            ["git", "check-ref-format", "--branch", name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=tmp_path,
        )
        assert (git.returncode == 0) is _pr_val.is_valid_branch_name(name)


class TestRequireHeadOnOrigin:
    def test_invalid_head_is_refused_without_a_push_hint(self, capsys) -> None:
        with patch("subprocess.run", side_effect=AssertionError("git must not run")):
            assert _pr_val.require_head_on_origin("feat/*") is False

        err = capsys.readouterr().err
        assert "not a valid git branch name" in err
        assert "git push" not in err

    def test_missing_branch_names_the_push_command(self, capsys) -> None:
        with patch.object(_pr_val, "head_on_origin", return_value=False):
            assert _pr_val.require_head_on_origin("feat/x") is False

        assert "git push -u origin feat/x" in capsys.readouterr().err

    def test_unreadable_origin_warns_and_continues(self, capsys) -> None:
        with patch.object(_pr_val, "head_on_origin", return_value=None):
            assert _pr_val.require_head_on_origin("feat/x") is True

        assert "could not read origin" in capsys.readouterr().err
        _pr_val._PREFLIGHT_WARNINGS.clear()

    def test_unreadable_origin_is_recorded_for_the_summary(self, capsys) -> None:
        _pr_val._PREFLIGHT_WARNINGS.clear()
        with patch.object(_pr_val, "head_on_origin", return_value=None):
            assert _pr_val.require_head_on_origin("feat/x") is True
        capsys.readouterr()

        assert len(_pr_val._PREFLIGHT_WARNINGS) == 1
        assert "could not read origin" in _pr_val._PREFLIGHT_WARNINGS[0]
        _pr_val._PREFLIGHT_WARNINGS.clear()

    def test_pushed_and_missing_branches_record_no_warning(self) -> None:
        _pr_val._PREFLIGHT_WARNINGS.clear()
        for found in (True, False):
            with patch.object(_pr_val, "head_on_origin", return_value=found):
                _pr_val.require_head_on_origin("feat/x")

        assert _pr_val._PREFLIGHT_WARNINGS == []

    def test_pushed_branch_is_silent(self, capsys) -> None:
        with patch.object(_pr_val, "head_on_origin", return_value=True):
            assert _pr_val.require_head_on_origin("feat/x") is True

        assert capsys.readouterr().err == ""


class TestMainRequiresPushedHead:
    def _run(self, tmp_path: Path, extra: list[str]):
        commands: list[list[str]] = []

        def _side(argv, **kwargs):
            commands.append(list(argv))
            return completed(stdout=str(tmp_path) if "--show-toplevel" in argv else "")

        with (
            patch("subprocess.run", side_effect=_side),
            patch.object(_pr_val, "head_on_origin", return_value=False),
            patch.object(new_pr, "run_validations") as validations,
            patch.object(new_pr, "write_audit_log") as audit,
        ):
            rc = main(["--title", "feat: test", "--head", "feat/x", *extra])
        return rc, commands, validations, audit

    def test_unpushed_head_exits_2_before_validation_and_creation(self, tmp_path) -> None:
        rc, commands, validations, _audit = self._run(tmp_path, [])

        assert rc == 2
        validations.assert_not_called()
        assert not any(command[:3] == ["gh", "pr", "create"] for command in commands)

    def test_unpushed_head_writes_no_audit_log_under_skip_validation(self, tmp_path) -> None:
        rc, _commands, _validations, audit = self._run(
            tmp_path, ["--skip-validation", "--audit-reason", "hotfix"]
        )

        assert rc == 2
        audit.assert_not_called()

    def test_pushed_head_reaches_pr_creation(self, tmp_path) -> None:
        commands: list[list[str]] = []

        def _side(argv, **kwargs):
            commands.append(list(argv))
            return completed(stdout=str(tmp_path) if "--show-toplevel" in argv else "")

        with (
            patch("subprocess.run", side_effect=_side),
            patch.object(_pr_val, "head_on_origin", return_value=True),
            patch.object(new_pr, "run_validations"),
        ):
            rc = main(["--title", "feat: test", "--head", "feat/x"])

        assert rc == 0
        assert any(command[:3] == ["gh", "pr", "create"] for command in commands)


@pytest.mark.usefixtures("stub_git_probes", "tmp_path_is_temp_root")
class TestPreflight:
    def _prepared(self, repo: Path, content: str = "## Summary\n\nDone.\n") -> str:
        relative = new_pr.prepare_pr_body(repo)
        (repo / relative).write_text(content, encoding="utf-8")
        return relative.as_posix()

    def _preflight(self, repo: Path, argv: list[str]) -> int:
        with (
            patch.object(new_pr, "get_repo_root", return_value=str(repo)),
            patch("subprocess.run", side_effect=AssertionError("preflight ran a command")),
        ):
            return main(["--preflight", *argv])

    def test_valid_title_and_body_pass_without_running_any_command(
        self, tmp_path: Path, capsys
    ) -> None:
        body = self._prepared(tmp_path)

        rc = self._preflight(tmp_path, ["--title", "feat: test", "--body-file", body])

        assert rc == 0
        assert "Preflight OK" in capsys.readouterr().out

    def test_title_without_conventional_prefix_fails(self, tmp_path: Path) -> None:
        body = self._prepared(tmp_path)

        assert self._preflight(tmp_path, ["--title", "Update stuff", "--body-file", body]) == 2

    def test_missing_title_fails(self, tmp_path: Path) -> None:
        body = self._prepared(tmp_path)

        assert self._preflight(tmp_path, ["--body-file", body]) == 2

    def test_scratchpad_body_outside_the_repo_passes(self, tmp_path: Path, capsys) -> None:
        """Issue #6667: a /tmp/claude-<uid>/ scratchpad path is accepted."""
        scratchpad = private_dir(tmp_path / "claude-1000" / "scratchpad")
        body = scratchpad / "pr7.md"
        body.write_text("## Summary\n\nDone.\n", encoding="utf-8")

        rc = self._preflight(
            tmp_path / "repo-root", ["--title", "feat: test", "--body-file", str(body)]
        )

        assert rc == 0
        assert "Preflight OK" in capsys.readouterr().out

    def test_fixed_name_body_in_scratch_passes(self, tmp_path: Path) -> None:
        scratch = private_dir(tmp_path / ".project-toolkit" / "scratch")
        (scratch / "body.md").write_text("text", encoding="utf-8")

        rc = self._preflight(
            tmp_path,
            ["--title", "feat: test", "--body-file", ".project-toolkit/scratch/body.md"],
        )

        assert rc == 0

    def test_body_outside_every_root_fails(
        self, external_tmp_path: Path, stub_temp_roots, capsys
    ) -> None:
        stub_temp_roots()
        stray = external_tmp_path / "body.md"
        stray.write_text("text", encoding="utf-8")

        rc = self._preflight(
            external_tmp_path, ["--title", "feat: test", "--body-file", str(stray)]
        )

        assert rc == 2
        assert "must be under the repo root" in capsys.readouterr().err

    def test_missing_body_fails(self, tmp_path: Path, capsys) -> None:
        rc = self._preflight(
            tmp_path, ["--title", "feat: test", "--body-file", str(tmp_path / "missing.md")]
        )

        assert rc == 2
        assert "Invalid body file" in capsys.readouterr().err

    def test_group_readable_prepared_body_is_refused(self, tmp_path: Path, capsys) -> None:
        body = self._prepared(tmp_path)
        (tmp_path / body).chmod(0o644)

        rc = self._preflight(tmp_path, ["--title", "feat: test", "--body-file", body])

        assert rc == 2
        assert "mode 600" in capsys.readouterr().err

    def test_unedited_seed_fails(self, tmp_path: Path, capsys) -> None:
        relative = new_pr.prepare_pr_body(tmp_path)

        rc = self._preflight(
            tmp_path, ["--title", "feat: test", "--body-file", relative.as_posix()]
        )

        assert rc == 2
        assert "placeholder" in capsys.readouterr().err

    def test_preflight_without_body_file_checks_only_the_title(self, tmp_path: Path) -> None:
        assert self._preflight(tmp_path, ["--title", "fix: test"]) == 0


def test_isolated_script_reads_a_scratchpad_body_file(tmp_path: Path) -> None:
    """Under ``python -I`` the shared rule loads by path and approves a temp-root file (#6667)."""
    scratchpad = private_dir(tmp_path / "claude-1000" / "scratchpad")
    body = scratchpad / "pr7.md"
    body.write_text("## Summary\n\nDone.\n", encoding="utf-8")
    env = {**os.environ, "TMPDIR": str(tmp_path)}
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("GITHUB_WORKSPACE", None)

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(new_pr_harness.SCRIPTS_DIR / "new_pr.py"),
            "--preflight",
            "--title",
            "feat: test",
            "--body-file",
            str(body),
        ],
        cwd=new_pr_harness.REPO_ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Preflight OK" in result.stdout
