"""Tests for the `--branch` publish mode of scripts/ci/commit_and_push.py.

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
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS_CI = _REPO / "scripts" / "ci"
_VALIDATOR = (
    _REPO / ".claude" / "skills" / "github" / "scripts" / "pr" / "validate_pr_description.py"
)
_original_path = sys.path.copy()
try:
    sys.path.insert(0, str(_SCRIPTS_CI))
    import commit_and_push
    from commit_and_push import main, pr_body
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
    "7287",
]


def _done(argv: list[str], code: int, out: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, code, out)


class _World:
    """Fake git + gh keyed on argv. Fields set which replies the world gives."""

    def __init__(self) -> None:
        self.dirty = True
        self.open_prs: list[dict[str, str]] = []
        self.pr_list_rc = 0
        self.pr_list_out: str | None = None
        self.remote_branch = False
        self.ls_remote_rc: int | None = None
        self.failing: tuple[str, ...] | None = None
        self.pr_create_rc = 0
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        tool, verb, *rest = argv
        if self.failing and tuple(argv[: len(self.failing)]) == self.failing:
            return _done(argv, 1, "boom")
        if tool == "git":
            return self._git(argv, verb, rest)
        if tool == "gh":
            return self._gh(argv, verb, rest)
        raise AssertionError(f"unexpected command: {argv}")

    def _git(self, argv: list[str], verb: str, rest: list[str]) -> subprocess.CompletedProcess[str]:
        if verb == "status":
            return _done(argv, 0, " M a.md\n" if self.dirty else "")
        if verb == "ls-remote":
            code = self.ls_remote_rc
            if code is None:
                code = 0 if self.remote_branch else 2
            return _done(argv, code, "sha\trefs/heads/x\n" if code == 0 else "")
        if verb in {"config", "checkout", "add", "commit", "push"}:
            return _done(argv, 0)
        raise AssertionError(f"unexpected git command: {argv}")

    def _gh(self, argv: list[str], verb: str, rest: list[str]) -> subprocess.CompletedProcess[str]:
        if (verb, rest[0]) == ("pr", "list"):
            out = self.pr_list_out if self.pr_list_out is not None else json.dumps(self.open_prs)
            return _done(argv, self.pr_list_rc, out)
        if (verb, rest[0]) == ("pr", "create"):
            return _done(argv, self.pr_create_rc, "https://github.com/o/r/pull/9\n")
        raise AssertionError(f"unexpected gh command: {argv}")

    def issued(self, *prefix: str) -> list[list[str]]:
        return [c for c in self.calls if tuple(c[: len(prefix)]) == prefix]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> _World:
    fake = _World()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def test_clean_tree_is_a_no_op_and_reports_the_examined_count(
    world: _World, capsys: pytest.CaptureFixture[str]
) -> None:
    world.dirty = False
    assert main(_ARGS) == 0
    assert "No changes to commit (examined 2 path(s))" in capsys.readouterr().out
    assert world.issued("gh") == []
    assert world.issued("git", "checkout") == []


def test_open_pull_request_is_left_alone(world: _World, capsys: pytest.CaptureFixture[str]) -> None:
    world.open_prs = [{"url": "https://github.com/o/r/pull/5", "isCrossRepository": False}]
    assert main(_ARGS) == 0
    assert "pull/5" in capsys.readouterr().out
    assert world.issued("git", "checkout") == []
    assert world.issued("git", "push") == []
    assert world.issued("gh", "pr", "create") == []


def test_fork_pull_request_with_the_same_branch_name_does_not_block_publishing(
    world: _World,
) -> None:
    world.open_prs = [{"url": "https://github.com/o/r/pull/6", "isCrossRepository": True}]
    assert main(_ARGS) == 0
    assert world.issued("gh", "pr", "create")


def test_publishes_branch_and_opens_pull_request(world: _World) -> None:
    assert main(_ARGS) == 0
    verbs = [tuple(c[:3]) for c in world.calls if c[1] in {"checkout", "add", "commit", "push"}]
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
    assert "Refs #7287" in body


def test_stale_remote_branch_is_deleted_before_the_push(world: _World) -> None:
    world.remote_branch = True
    assert main(_ARGS) == 0
    order = [c[1] for c in world.calls if c[1] in {"push", "checkout"}]
    assert world.issued("git", "push", "origin", "--delete", _BRANCH)
    delete_at = world.calls.index(["git", "push", "origin", "--delete", _BRANCH])
    push_at = world.calls.index(["git", "push", "--set-upstream", "origin", _BRANCH])
    assert delete_at < push_at
    assert order.count("push") == 2


def test_no_force_push_in_any_path(world: _World) -> None:
    world.remote_branch = True
    main(_ARGS)
    assert not [c for c in world.calls if "--force" in c or "-f" in c or "--force-with-lease" in c]


def test_pr_list_failure_exits_external_before_any_mutation(world: _World) -> None:
    world.pr_list_rc = 1
    assert main(_ARGS) == 3
    assert world.issued("git", "checkout") == []
    assert world.issued("git", "push") == []


@pytest.mark.parametrize(
    "payload", ["not json", '{"url": "x"}', '[{"number": 1}]', '[{"url": "x"}]']
)
def test_unreadable_pr_list_output_is_not_read_as_no_pull_request(
    world: _World, payload: str
) -> None:
    world.pr_list_out = payload
    assert main(_ARGS) == 3
    assert world.issued("git", "push") == []
    assert world.issued("gh", "pr", "create") == []


def test_push_failure_exits_git_failed_and_opens_no_pull_request(world: _World) -> None:
    world.failing = ("git", "push", "--set-upstream")
    assert main(_ARGS) == 1
    assert world.issued("gh", "pr", "create") == []


def test_stale_branch_delete_failure_exits_git_failed(world: _World) -> None:
    world.remote_branch = True
    world.failing = ("git", "push", "origin", "--delete")
    assert main(_ARGS) == 1
    assert world.issued("git", "checkout") == []


def test_ls_remote_error_is_not_read_as_branch_absent(world: _World) -> None:
    world.ls_remote_rc = 128
    assert main(_ARGS) == 1
    assert world.issued("git", "push") == []


def test_pr_create_failure_exits_external(world: _World) -> None:
    world.pr_create_rc = 1
    assert main(_ARGS) == 3


def test_missing_gh_binary_exits_usage(monkeypatch: pytest.MonkeyPatch, world: _World) -> None:
    def no_gh(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if argv[0] == "gh":
            raise FileNotFoundError("gh")
        return world(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", no_gh)
    assert main(_ARGS) == 2


def test_default_mode_never_calls_gh(world: _World) -> None:
    args = [a for a in _ARGS if a not in {"--branch", _BRANCH, "--issue", "7287"}]
    assert main(args) == 0
    assert world.issued("gh") == []
    assert world.issued("git", "push") == [["git", "push"]]


def test_pull_request_body_passes_the_repo_validator(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text(pr_body(["a.md", "b.json"], "7287"), encoding="utf-8")
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
    assert commit_and_push.pr_body(["a.md"], None).count("Refs #") == 0


def _workflow_publish_step() -> tuple[dict, dict]:
    import yaml

    doc = yaml.safe_load(
        (_REPO / ".github" / "workflows" / "update-reviewer-stats.yml").read_text(encoding="utf-8")
    )
    job = doc["jobs"]["update-stats"]
    (step,) = [s for s in job["steps"] if "commit_and_push.py" in s.get("run", "")]
    return job, step


def test_workflow_publishes_through_branch_mode_with_the_scopes_it_needs() -> None:
    job, step = _workflow_publish_step()
    assert "--branch automation/reviewer-stats" in step["run"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
