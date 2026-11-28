"""Tests for scripts/ci/open_bot_pr.py.

Issue #7287: the default branch is protected, so the deleted update-reviewer-stats.yml
could not push to it. Branch mode commits on a bot branch and opens a pull
request. These tests drive `main(argv)` and assert on the exit code, the
commands issued, and the commands that must not be issued. Git and gh are
faked at the subprocess boundary and dispatched on argv, so an unexpected
command fails by name instead of shifting a positional reply list.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.ci.open_bot_pr_helpers import (
    _ARGS,
    _BRANCH,
    _REAL_RUN,
    _World,
)

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS_CI = _REPO / "scripts" / "ci"
_VALIDATOR = (
    _REPO / ".claude" / "skills" / "github" / "scripts" / "pr" / "validate_pr_description.py"
)
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    from open_bot_pr import main, pr_body
finally:
    sys.path[:] = _original_path


@pytest.fixture(autouse=True)
def _forbid_unmocked_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def guard(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"unmocked subprocess.run: {argv}")

    monkeypatch.setattr(subprocess, "run", guard)


@pytest.fixture
def make_world(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _World]:
    def build(**replies: Any) -> _World:
        fake = _World(**replies)
        monkeypatch.setattr(subprocess, "run", fake)
        return fake

    return build


def test_clean_tree_is_a_no_op_and_reports_the_examined_count(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(dirty=False)
    assert main(_ARGS) == 0
    assert "No changes to commit (examined 2 path(s))" in capsys.readouterr().out
    assert world.issued("gh") == []
    assert world.issued("git", "checkout") == []


def test_open_pull_request_is_left_alone(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(
        open_prs=[{"url": "https://github.com/o/r/pull/5", "isCrossRepository": False}]
    )
    assert main(_ARGS) == 0
    assert "pull/5" in capsys.readouterr().out
    assert world.issued("git", "checkout") == []
    assert world.issued("git", "push") == []
    assert world.issued("gh", "pr", "create") == []


def test_fork_pull_request_with_the_same_branch_name_does_not_block_publishing(
    make_world: Callable[..., _World],
) -> None:
    world = make_world(
        open_prs=[{"url": "https://github.com/o/r/pull/6", "isCrossRepository": True}]
    )
    assert main(_ARGS) == 0
    assert world.issued("gh", "pr", "create")


def test_full_pr_list_page_fails_closed_instead_of_reading_as_no_match(
    make_world: Callable[..., _World],
) -> None:
    world = make_world(
        open_prs=[
            {"url": f"https://github.com/o/r/pull/{n}", "isCrossRepository": True}
            for n in range(100)
        ]
    )
    assert main(_ARGS) == 3
    assert world.issued("git", "push") == []
    assert world.issued("gh", "pr", "create") == []


def test_publishes_branch_and_opens_pull_request(make_world: Callable[..., _World]) -> None:
    world = make_world()
    assert main(_ARGS) == 0
    assert world.issued("git", "config") == []
    verbs = [tuple(c[:3]) for c in world.argvs() if c[1] in {"checkout", "add", "-c", "push"}]
    assert verbs == [
        ("git", "checkout", "-B"),
        ("git", "add", "--"),
        ("git", "-c", "user.name=bot"),
        ("git", "push", "--set-upstream"),
    ]
    assert world.issued("git", "-c") == [
        [
            "git",
            "-c",
            "user.name=bot",
            "-c",
            "user.email=bot@example.com",
            "commit",
            "-m",
            "chore(stats): update reviewer signal statistics",
            "-m",
            "body",
        ]
    ]
    assert world.issued("git", "push", "origin", "--delete") == []
    (create,) = world.issued("gh", "pr", "create")
    assert create[create.index("--head") + 1] == _BRANCH
    assert create[create.index("--base") + 1] == "main"
    assert create[create.index("--title") + 1] == "chore(stats): update reviewer signal statistics"
    body = create[create.index("--body") + 1]
    assert "- `a.md`" in body
    assert "- `b.json`" in body
    assert "Refs #234" in body


def test_stale_remote_branch_is_deleted_before_the_push(make_world: Callable[..., _World]) -> None:
    world = make_world(remote_branch=True)
    assert main(_ARGS) == 0
    assert world.issued("git", "push", "origin", "--delete", _BRANCH)
    delete_at = world.argvs().index(["git", "push", "origin", "--delete", _BRANCH])
    push_at = world.argvs().index(["git", "push", "--set-upstream", "origin", _BRANCH])
    assert delete_at < push_at


def test_no_force_push_in_any_path(make_world: Callable[..., _World]) -> None:
    world = make_world(remote_branch=True)
    main(_ARGS)
    assert not [
        c for c in world.argvs() if "--force" in c or "-f" in c or "--force-with-lease" in c
    ]


def test_pr_list_failure_exits_external_before_any_mutation(
    make_world: Callable[..., _World],
) -> None:
    world = make_world(pr_list_rc=1)
    assert main(_ARGS) == 3
    assert world.issued("git", "checkout") == []
    assert world.issued("git", "push") == []


@pytest.mark.parametrize(
    "payload", ["not json", '{"url": "x"}', '[{"number": 1}]', '[{"url": "x"}]']
)
def test_unreadable_pr_list_output_is_not_read_as_no_pull_request(
    make_world: Callable[..., _World], payload: str
) -> None:
    world = make_world(pr_list_out=payload)
    assert main(_ARGS) == 3
    assert world.issued("git", "push") == []
    assert world.issued("gh", "pr", "create") == []


def test_push_failure_exits_git_failed_and_opens_no_pull_request(
    make_world: Callable[..., _World],
) -> None:
    world = make_world(failing=("git", "push", "--set-upstream"))
    assert main(_ARGS) == 1
    assert world.issued("gh", "pr", "create") == []


def test_stale_branch_delete_failure_exits_git_failed(make_world: Callable[..., _World]) -> None:
    world = make_world(remote_branch=True, failing=("git", "push", "origin", "--delete"))
    assert main(_ARGS) == 1
    assert world.issued("git", "checkout") == []


def test_ls_remote_error_is_not_read_as_branch_absent(make_world: Callable[..., _World]) -> None:
    world = make_world(ls_remote_rc=128)
    assert main(_ARGS) == 1
    assert world.issued("git", "push") == []


def test_pr_create_failure_exits_external(make_world: Callable[..., _World]) -> None:
    make_world(pr_create_rc=1)
    assert main(_ARGS) == 3


def test_missing_gh_binary_exits_usage(
    monkeypatch: pytest.MonkeyPatch, make_world: Callable[..., _World]
) -> None:
    world = make_world()

    def no_gh(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[0] == "gh":
            raise FileNotFoundError("gh")
        return world(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", no_gh)
    assert main(_ARGS) == 2


def test_pull_request_body_passes_the_repo_validator(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text(pr_body(["a.md", "b.json"], "234"), encoding="utf-8")
    result = _REAL_RUN(
        [
            sys.executable,
            "-I",
            str(_VALIDATOR),
            "--title",
            "chore(stats): update reviewer signal statistics",
            "--body-file",
            str(body),
            "--fail-on-violation",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_issue_flag_is_required(make_world: Callable[..., _World]) -> None:
    world = make_world()
    args = [a for a in _ARGS if a not in {"--issue", "234"}]
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    assert exit_info.value.code == 2
    assert world.argvs() == []


def test_published_outcome_reports_the_last_line_as_the_url(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    make_world()
    assert main(_ARGS) == 0
    assert "pr=https://github.com/o/r/pull/9" in capsys.readouterr().out


def test_a_gh_warning_before_the_url_does_not_become_the_reported_url(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    make_world(pr_create_out="warning: something\nhttps://github.com/o/r/pull/9\n")
    assert main(_ARGS) == 0
    out = capsys.readouterr().out
    assert "pr=https://github.com/o/r/pull/9" in out
    assert "warning" not in out


def test_gh_only_timeout_exits_external(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = _World()

    def gh_hangs(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[0] == "gh":
            raise subprocess.TimeoutExpired(argv, 1)
        return inner(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", gh_hangs)
    assert main(_ARGS) == 3
    assert inner.issued("git", "push") == []


def test_git_commit_failure_exits_git_failed_and_never_runs_git_config(
    make_world: Callable[..., _World],
) -> None:
    world = make_world(failing=("git", "-c"))
    assert main(_ARGS) == 1
    assert world.issued("git", "config") == []
    assert world.issued("git", "push", "--set-upstream") == []
    assert world.issued("gh", "pr", "create") == []


def test_git_status_failure_names_the_command(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    make_world(failing=("git", "status"))
    assert main(_ARGS) == 1
    assert "git status failed" in capsys.readouterr().err


def test_title_and_base_overrides_reach_gh_pr_create(make_world: Callable[..., _World]) -> None:
    world = make_world()
    assert main([*_ARGS, "--pr-title", "chore: custom", "--base", "develop"]) == 0
    (create,) = world.issued("gh", "pr", "create")
    assert create[create.index("--title") + 1] == "chore: custom"
    assert create[create.index("--base") + 1] == "develop"


def test_skip_prints_a_notice_annotation_and_outcome(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    make_world(open_prs=[{"url": "https://github.com/o/r/pull/5", "isCrossRepository": False}])
    assert main(_ARGS) == 0
    out = capsys.readouterr().out
    assert "::notice title=" in out
    assert "outcome=skipped" in out


def test_publish_and_noop_print_their_outcome(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    make_world()
    assert main(_ARGS) == 0
    assert "outcome=published" in capsys.readouterr().out
    make_world(dirty=False)
    assert main(_ARGS) == 0
    assert "outcome=noop" in capsys.readouterr().out


def test_pr_create_failure_says_the_branch_is_already_pushed(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    make_world(pr_create_rc=1)
    assert main(_ARGS) == 3
    assert "already pushed" in capsys.readouterr().err


def test_timeout_counts_as_the_call_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"]
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(subprocess, "run", hang)
    assert main(_ARGS) == 1


def test_ls_remote_matches_the_full_ref_name(make_world: Callable[..., _World]) -> None:
    world = make_world()
    main(_ARGS)
    (ls,) = world.issued("git", "ls-remote")
    assert ls[-1] == f"refs/heads/{_BRANCH}"


def test_head_off_base_refuses_to_publish_and_mutates_nothing(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(merge_base_rc=1)
    assert main(_ARGS) == 2
    assert "not an ancestor of origin/main" in capsys.readouterr().err
    assert world.issued("gh") == []
    assert world.issued("git", "checkout") == []
    assert world.issued("git", "push") == []


def test_merge_base_error_is_not_read_as_on_base(make_world: Callable[..., _World]) -> None:
    world = make_world(merge_base_rc=128)
    assert main(_ARGS) == 1
    assert world.issued("git", "push") == []


@pytest.mark.parametrize(
    "branch", ["main", "feature/x", "automation/", "automation/-x", "--all", "automation/a b"]
)
def test_branch_outside_the_automation_namespace_is_a_usage_error(
    make_world: Callable[..., _World], branch: str
) -> None:
    world = make_world()
    args = [*_ARGS]
    args[args.index(_BRANCH)] = branch
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    assert exit_info.value.code == 2
    assert world.argvs() == []


def test_open_pr_lookup_is_scoped_to_the_head_and_not_the_base(
    make_world: Callable[..., _World],
) -> None:
    """A human pull request into another base must still block the branch delete."""
    world = make_world()
    main(_ARGS)
    (lookup,) = world.issued("gh", "pr", "list")
    assert lookup[lookup.index("--head") + 1] == _BRANCH
    assert "--base" not in lookup


def test_only_changed_paths_are_staged_and_named_in_the_body(
    make_world: Callable[..., _World],
) -> None:
    world = make_world(dirty_paths={"b.json"})
    assert main(_ARGS) == 0
    (add,) = world.issued("git", "add")
    assert add == ["git", "add", "--", "b.json"]
    (create,) = world.issued("gh", "pr", "create")
    body = create[create.index("--body") + 1]
    assert "- `b.json`" in body
    assert "- `a.md`" not in body


def test_no_changed_path_among_several_is_a_noop(
    make_world: Callable[..., _World], capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(dirty_paths=set())
    assert main(_ARGS) == 0
    assert "examined 2 path(s)" in capsys.readouterr().out
    assert world.issued("gh") == []
