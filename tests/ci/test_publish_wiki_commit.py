"""The git failure paths after the clone in scripts/ci/publish_wiki.py (issue #7202).

A failed ``git add``, ``git diff`` or ``git commit`` is an external failure (exit 3).
It must never read as "the wiki already matches". Its stderr reaches the log only
after the token, the base64 credential, workflow commands, and line breaks are removed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts.ci import publish_wiki as pw
from tests.ci.publish_wiki_helpers import file_url, make_repo, make_wiki


def run_with_git_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verb: str, stderr: str, token: str | None
) -> int:
    repo = make_repo(tmp_path / "repo")
    wiki = make_wiki(tmp_path)
    real = pw.run_git

    def fake(
        args: Sequence[str], cwd: Path | None, env: Mapping[str, str]
    ) -> subprocess.CompletedProcess[str]:
        if verb in args:
            return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)
        return real(args, cwd, env)

    monkeypatch.setattr(pw, "run_git", fake)
    argv = ["--repo-root", str(repo), "--repo", "acme/widgets", "--wiki-url", file_url(wiki)]
    return pw.main(argv, environ={"WIKI_TOKEN": token} if token else {})


def test_a_failed_commit_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        run_with_git_failing(tmp_path, monkeypatch, "commit", "fatal: unable to write", None) == 3
    )


def test_commit_stderr_is_redacted_and_neutralized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stderr = "::add-mask::x\nerror: leaked s3cret-token here"
    assert run_with_git_failing(tmp_path, monkeypatch, "commit", stderr, "s3cret-token") == 3
    err = capsys.readouterr().err
    assert "s3cret-token" not in err
    assert "::add-mask::" not in err
    assert "EXTERNAL: git commit failed" in err


@pytest.mark.parametrize("verb", ["add", "diff"])
def test_a_failed_staging_step_exits_3_not_a_clean_no_op(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verb: str,
) -> None:
    code = run_with_git_failing(tmp_path, monkeypatch, verb, "fatal: index.lock exists", None)
    captured = capsys.readouterr()
    assert code == 3
    assert "EXTERNAL: git staging failed" in captured.err
    assert "already matches" not in captured.out


def test_staging_stderr_is_redacted_and_neutralized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stderr = "::add-mask::x\nerror: leaked s3cret-token here"
    assert run_with_git_failing(tmp_path, monkeypatch, "add", stderr, "s3cret-token") == 3
    err = capsys.readouterr().err
    assert "s3cret-token" not in err
    assert "::add-mask::" not in err
