"""Tests for the new_issue.py GITHUB_OUTPUT writes on failure (issue #6180).

When the issue exists but a later step fails, an Actions caller must still see
``issue_number`` and ``issue_url`` with ``success=false``. A failure before
creation must write no ``issue_number``.
"""

import subprocess

import pytest

from .new_issue_harness import (
    FakeGh,
    _make_proc,
    _run,
    resolve_repo_fixture,  # noqa: F401  (autouse fixture)
)

MILESTONES = ("api", "repos/owner/repo/milestones")
LIST_OK = _make_proc(stdout="v0.7.0\n")
BASE = ["--title", "Title", "--source", "human"]
CREATED = {
    "success": "false",
    "issue_number": "42",
    "issue_url": "https://github.com/owner/repo/issues/42",
}


@pytest.fixture(name="gh_output")
def gh_output_fixture(tmp_path, monkeypatch):
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    return out


def _outputs(path) -> dict[str, str]:
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines)


def test_label_failure_writes_issue_number(gh_output):
    gh = FakeGh(issue_edit=_make_proc(returncode=1, stderr="label boom"))

    rc, _ = _run([*BASE, "--labels", "bug"], gh)

    assert rc == 3
    assert _outputs(gh_output) == CREATED


def test_label_timeout_writes_issue_number(gh_output):
    gh = FakeGh(issue_edit=subprocess.TimeoutExpired(cmd="gh", timeout=30))

    rc, _ = _run([*BASE, "--labels", "bug"], gh)

    assert rc == 3
    assert _outputs(gh_output) == CREATED


def test_milestone_failure_writes_issue_number(gh_output):
    gh = FakeGh(
        issue_edit=_make_proc(returncode=1, stderr="edit boom"),
        extra_routes={MILESTONES: LIST_OK},
    )

    rc, _ = _run([*BASE, "--milestone", "v0.7.0"], gh)

    assert rc == 3
    assert _outputs(gh_output) == CREATED


def test_milestone_auth_failure_writes_issue_number(gh_output):
    gh = FakeGh(
        issue_edit=_make_proc(returncode=1, stderr="authentication required"),
        extra_routes={MILESTONES: LIST_OK},
    )

    rc, _ = _run([*BASE, "--milestone", "v0.7.0"], gh)

    assert rc == 4
    assert _outputs(gh_output) == CREATED


def test_failure_writes_output_once(gh_output):
    gh = FakeGh(issue_edit=_make_proc(returncode=1, stderr="label boom"))

    _run([*BASE, "--labels", "bug"], gh)

    assert gh_output.read_text(encoding="utf-8").count("issue_number=") == 1


@pytest.mark.parametrize(
    ("gh", "argv", "code"),
    [
        (FakeGh(issue_create=_make_proc(returncode=1, stderr="boom")), BASE, 3),
        (
            FakeGh(issue_create=_make_proc(stdout="no number here")),
            BASE,
            3,
        ),
        (
            FakeGh(
                extra_routes={("issue", "create"): subprocess.TimeoutExpired(cmd="gh", timeout=30)}
            ),
            BASE,
            3,
        ),
        (FakeGh(extra_routes={MILESTONES: LIST_OK}), [*BASE, "--milestone", "v9"], 2),
    ],
    ids=["create-fails", "create-unparseable", "create-times-out", "milestone-missing"],
)
def test_failure_before_creation_writes_no_issue_number(gh_output, gh, argv, code):
    rc, _ = _run(argv, gh)

    assert rc == code
    assert "issue_number" not in _outputs(gh_output)
    assert not gh_output.exists()


def test_invalid_request_writes_nothing(gh_output):
    rc, gh = _run([*BASE[:2], "--source", "agent"], FakeGh())

    assert rc == 2
    assert gh.calls == []
    assert not gh_output.exists()


def test_success_still_writes_success_true(gh_output):
    rc, _ = _run(BASE, FakeGh())

    assert rc == 0
    assert _outputs(gh_output) == {
        "success": "true",
        "issue_number": "42",
        "issue_url": "https://github.com/owner/repo/issues/42",
    }


def test_unwritable_output_file_does_not_mask_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "missing_dir" / "out"))
    gh = FakeGh(issue_edit=_make_proc(returncode=1, stderr="label boom"))

    rc, _ = _run([*BASE, "--labels", "bug"], gh)

    assert rc == 3


def test_no_github_output_env_is_a_noop(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    gh = FakeGh(issue_edit=_make_proc(returncode=1, stderr="label boom"))

    rc, _ = _run([*BASE, "--labels", "bug"], gh)

    assert rc == 3
