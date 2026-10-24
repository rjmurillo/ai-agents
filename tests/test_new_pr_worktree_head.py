"""End-to-end check that ``new_pr.py --head`` opens a PR for a worktree branch (#5540).

A branch developed in an external worktree cannot be checked out in the primary
clone. Real git builds both checkouts here. Only ``gh`` is faked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.containment_fixtures import private_dir
from tests.new_pr_test_support import _prepared_body, main

_BRANCH = "feat/5540-external-worktree"


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def clone_and_worktree(tmp_path: Path) -> tuple[Path, Path]:
    # A clone below a shared temp root must be owner-only, or the body-file
    # reader refuses the prepared body inside it (issue #6667).
    clone = private_dir(tmp_path / "clone")
    _git(clone, "init", "-b", "main")
    (clone / "README.md").write_text("seed\n", encoding="utf-8")
    _git(clone, "add", "README.md")
    _git(clone, "commit", "-m", "chore: seed")
    worktree = tmp_path / "worktrees" / "feat-5540"
    _git(clone, "worktree", "add", str(worktree), "-b", _BRANCH)
    return clone, worktree


_FAKE_GH = """#!{python}
import json, sys
with open({log!r}, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(sys.argv[1:]) + "\\n")
"""


def _run_main(clone: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *extra: str):
    """Run ``main`` from the primary clone with a fake ``gh`` on PATH and real git."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh-calls.jsonl"
    gh = bin_dir / "gh"
    gh.write_text(_FAKE_GH.format(python=sys.executable, log=str(log)), encoding="utf-8")
    gh.chmod(0o700)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(clone)

    body_file = _prepared_body(clone)
    argv = ["--title", "feat: external worktree", "--body-file", body_file, *extra]
    rc = main(argv)
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return rc, [call for call in calls if call[:2] == ["pr", "create"]]


def test_head_from_external_worktree_reaches_gh(clone_and_worktree, monkeypatch, tmp_path):
    clone, worktree = clone_and_worktree

    rc, create_calls = _run_main(
        clone,
        monkeypatch,
        tmp_path,
        "--head",
        _BRANCH,
        "--skip-validation",
        "--audit-reason",
        "issue 5540 end-to-end test",
    )

    assert rc == 0
    assert len(create_calls) == 1
    command = create_calls[0]
    assert command[command.index("--head") + 1] == _BRANCH
    assert command[command.index("--base") + 1] == "main"


def test_worktree_survives_pr_creation(clone_and_worktree, monkeypatch, tmp_path):
    clone, worktree = clone_and_worktree

    _run_main(
        clone,
        monkeypatch,
        tmp_path,
        "--head",
        _BRANCH,
        "--skip-validation",
        "--audit-reason",
        "x y",
    )

    assert worktree.is_dir()
    assert _git(clone, "branch", "--show-current") == "main"
    assert _git(worktree, "branch", "--show-current") == _BRANCH


def test_without_head_the_primary_clone_branch_is_used(clone_and_worktree, monkeypatch, tmp_path):
    clone, _ = clone_and_worktree

    rc, create_calls = _run_main(
        clone, monkeypatch, tmp_path, "--skip-validation", "--audit-reason", "head default check"
    )

    assert rc == 0
    command = create_calls[0]
    assert command[command.index("--head") + 1] == "main"
