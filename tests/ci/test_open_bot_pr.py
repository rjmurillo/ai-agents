"""Tests for scripts/ci/open_bot_pr.py.

Issue #7287: the default branch is protected, so update-reviewer-stats.yml
cannot push to it. Branch mode commits on a bot branch and opens a pull
request. These tests drive `main(argv)` and assert on the exit code, the
commands issued, and the commands that must not be issued. Git and gh are
faked at the subprocess boundary and dispatched on argv, so an unexpected
command fails by name instead of shifting a positional reply list.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

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

_BRANCH = "automation/reviewer-stats"
_ARGS = [
    "--path",
    "a.md",
    "--path",
    "b.json",
    "--user-name",
    "bot",
    "--user-email",
    "bot@example.com",
    "--message",
    "chore(stats): update reviewer signal statistics",
    "--message",
    "body",
    "--branch",
    _BRANCH,
    "--issue",
    "234",
]


def _done(argv: list[str], code: int, out: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, code, out)


class _World:
    """Fake git + gh keyed on argv. Constructor arguments pick the replies."""

    def __init__(
        self,
        *,
        dirty: bool = True,
        open_prs: list[dict[str, str | bool]] | None = None,
        pr_list_rc: int = 0,
        pr_list_out: str | None = None,
        remote_branch: bool = False,
        ls_remote_rc: int | None = None,
        failing: tuple[str, ...] | None = None,
        pr_create_rc: int = 0,
        merge_base_rc: int = 0,
    ) -> None:
        self._dirty = dirty
        self._pr_list_rc = pr_list_rc
        self._pr_list_out = pr_list_out if pr_list_out is not None else json.dumps(open_prs or [])
        self._ls_remote_rc = (
            ls_remote_rc if ls_remote_rc is not None else (0 if remote_branch else 2)
        )
        self._failing = failing
        self._pr_create_rc = pr_create_rc
        self._merge_base_rc = merge_base_rc
        self._calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self._calls.append(list(argv))
        tool, verb = argv[0], argv[1]
        if self._failing and tuple(argv[: len(self._failing)]) == self._failing:
            return _done(argv, 1, "boom")
        if tool == "git":
            return self._git(argv, verb)
        if tool == "gh":
            return self._gh(argv)
        raise AssertionError(f"unexpected command: {argv}")

    def _git(self, argv: list[str], verb: str) -> subprocess.CompletedProcess[str]:
        if verb == "status":
            return _done(argv, 0, " M a.md\n" if self._dirty else "")
        if verb == "ls-remote":
            code = self._ls_remote_rc
            return _done(argv, code, "sha\trefs/heads/x\n" if code == 0 else "")
        if verb == "merge-base":
            return _done(argv, self._merge_base_rc)
        if verb in {"config", "checkout", "add", "commit", "push"}:
            return _done(argv, 0)
        raise AssertionError(f"unexpected git command: {argv}")

    def _gh(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        match argv[1:3]:
            case ["pr", "list"]:
                return _done(argv, self._pr_list_rc, self._pr_list_out)
            case ["pr", "create"]:
                return _done(argv, self._pr_create_rc, "https://github.com/o/r/pull/9\n")
        raise AssertionError(f"unexpected gh command: {argv}")

    def argvs(self) -> list[list[str]]:
        return list(self._calls)

    def issued(self, *prefix: str) -> list[list[str]]:
        return [c for c in self._calls if tuple(c[: len(prefix)]) == prefix]


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
    verbs = [tuple(c[:3]) for c in world.argvs() if c[1] in {"checkout", "add", "commit", "push"}]
    assert verbs == [
        ("git", "checkout", "-B"),
        ("git", "add", "--"),
        ("git", "commit", "-m"),
        ("git", "push", "--set-upstream"),
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
    result = subprocess.run(
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


def _workflow_publish_step() -> tuple[dict, dict]:
    import yaml

    doc = yaml.safe_load(
        (_REPO / ".github" / "workflows" / "update-reviewer-stats.yml").read_text(encoding="utf-8")
    )
    job = doc["jobs"]["update-stats"]
    (step,) = [s for s in job["steps"] if "open_bot_pr.py" in s.get("run", "")]
    return job, step


def test_workflow_publishes_through_branch_mode_with_the_scopes_it_needs() -> None:
    job, step = _workflow_publish_step()
    assert "--branch automation/reviewer-stats" in step["run"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"


def test_git_config_failure_exits_git_failed_before_any_other_call(
    make_world: Callable[..., _World],
) -> None:
    world = make_world(failing=("git", "config"))
    assert main(_ARGS) == 1
    assert world.issued("gh") == []
    assert world.issued("git", "status") == []


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


def test_open_pr_lookup_is_scoped_to_head_and_base(make_world: Callable[..., _World]) -> None:
    world = make_world()
    main(_ARGS)
    (lookup,) = world.issued("gh", "pr", "list")
    assert lookup[lookup.index("--head") + 1] == _BRANCH
    assert lookup[lookup.index("--base") + 1] == "main"
