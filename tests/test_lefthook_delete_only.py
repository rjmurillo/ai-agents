"""Tests for delete-only pre-push scheduling and the ref guard contract."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
import yaml

from scripts.validation import lefthook_runner as runner
from tests.support.lefthook_binary import resolve_lefthook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh shim")
_LEFTHOOK = resolve_lefthook()


# --- delete-only pushes run only the ref guard jobs ------------------------

ZERO_SHA = "0" * 40
SOME_SHA = "954729fa9af4ef395fd0b8643f9c50a0b04b7d36"
DELETE_LINE = f"(delete) {ZERO_SHA} refs/heads/old {SOME_SHA}\n"
UPDATE_LINE = f"refs/heads/topic {SOME_SHA} refs/heads/topic {ZERO_SHA}\n"
GIT_ARGUMENTS = ["origin", "https://example.test/repo.git"]
# The pre-push jobs that guard refs. A literal, not read from lefthook.yml, so
# dropping the tag from any one of them fails a test.
REF_GUARD_JOBS = frozenset(
    {
        "repo-health",
        "repair-packed-refs",
        "mutation-safety",
        "push-ref-staleness",
        "push-ref-policy",
        "security-suppression-policy",
        "placeholder-identity",
    }
)
# Every other pre-push job. None is required to guard a ref deletion.
# Listing every job means a new one fails a test until someone classifies it.
TREE_JOBS = frozenset(
    {
        "python-unreachable-statements",
        "python-unused-arguments",
        "path-normalization",
        "planning-artifacts",
        "branch-context-policy",
        "import-boundaries",
        "dash-prohibition",
        "security-scan",
        "plugin-scanner",
        "pre-pr-validation",
        "count-ratchets",
        "worktree-gc-report",
        "branch-config-prune-report",
        "python-lint-advisory",
        "python-type-check",
        "additions-advisory",
        "bot-cascade-advisory",
        "workflow-local-run",
        "hook-anchoring-e2e",
        "plugin-load-e2e",
    }
)
GUARD_TAG_ARGS = ["--tag", "ref-guard"]


def _pre_push(stdin: bytes | None, *flags: str) -> list[str]:
    arguments = ["run", "pre-push", *flags, *GIT_ARGUMENTS]
    with mock.patch.object(runner, "lefthook_file_args", return_value=["--file=a.py"]):
        return runner._child_arguments(arguments, stdin)


def _leaf_jobs(jobs: list[dict]) -> Iterator[dict]:
    """Yield every job that runs a command, including jobs inside nested groups."""
    for job in jobs:
        if "group" in job:
            yield from _leaf_jobs(job["group"].get("jobs", []))
        else:
            yield job


def _pre_push_jobs() -> list[dict]:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    return config["pre-push"]["jobs"]


def _tagged_job_names(tag: str) -> list[str]:
    return [job["name"] for job in _leaf_jobs(_pre_push_jobs()) if tag in (job.get("tags") or [])]


def test_delete_only_push_adds_the_ref_guard_tag() -> None:
    result = _pre_push(DELETE_LINE.encode())

    assert result == [
        "run",
        "pre-push",
        "--file=a.py",
        *GUARD_TAG_ARGS,
        "--",
        *GIT_ARGUMENTS,
    ]


def test_delete_only_push_with_several_deletes_adds_the_tag() -> None:
    stdin = (DELETE_LINE + DELETE_LINE.replace("old", "older")).encode()

    assert _pre_push(stdin)[3:5] == GUARD_TAG_ARGS


def test_delete_only_push_says_tree_jobs_were_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    _pre_push((DELETE_LINE + DELETE_LINE.replace("old", "older")).encode())

    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "skipped the tree jobs" in err
    assert "only deletes refs (2)" in err
    assert "Only jobs tagged ref-guard run" in err


def test_mixed_delete_and_update_keeps_every_job() -> None:
    stdin = (DELETE_LINE + UPDATE_LINE).encode()

    assert "--tag" not in _pre_push(stdin)


def test_update_before_delete_keeps_every_job() -> None:
    stdin = (UPDATE_LINE + DELETE_LINE).encode()

    assert "--tag" not in _pre_push(stdin)


def test_update_only_push_keeps_every_job(capsys: pytest.CaptureFixture[str]) -> None:
    assert "--tag" not in _pre_push(UPDATE_LINE.encode())
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("stdin", [None, b"", b"\n"])
def test_empty_stdin_keeps_every_job(
    stdin: bytes | None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "--tag" not in _pre_push(stdin)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "flags",
    [
        ("--job", "python-tests"),
        ("--job=python-tests",),
        ("--tag", "fast"),
        ("--tag=fast",),
        ("--command", "lint"),
        ("--command=lint",),
    ],
)
def test_caller_supplied_scope_flag_is_respected(
    flags: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    result = _pre_push(DELETE_LINE.encode(), *flags)

    assert result == ["run", "pre-push", "--file=a.py", *flags, "--", *GIT_ARGUMENTS]
    assert capsys.readouterr().err == ""


def test_caller_supplied_file_flag_is_respected() -> None:
    arguments = ["run", "pre-push", "--file", "x.py", *GIT_ARGUMENTS]

    result = runner._child_arguments(arguments, DELETE_LINE.encode())

    assert result == ["run", "pre-push", "--file", "x.py", "--", *GIT_ARGUMENTS]


def test_other_hooks_never_get_the_tag() -> None:
    arguments = ["run", "pre-commit"]

    assert runner._child_arguments(arguments, DELETE_LINE.encode()) == arguments


def test_malformed_ref_line_still_stops_the_push() -> None:
    arguments = ["run", "pre-push", *GIT_ARGUMENTS]

    with pytest.raises(runner.PushFileListError):
        runner._child_arguments(arguments, b"not a ref line\n")


def test_runner_tag_matches_the_config_tag() -> None:
    assert GUARD_TAG_ARGS == ["--tag", runner.REF_GUARD_TAG]


def test_exactly_the_ref_guard_jobs_carry_the_tag() -> None:
    assert sorted(_tagged_job_names(runner.REF_GUARD_TAG)) == sorted(REF_GUARD_JOBS)


def test_every_pre_push_job_is_a_ref_guard_or_a_tree_job() -> None:
    names = [job["name"] for job in _leaf_jobs(_pre_push_jobs())]

    assert len(names) == len(set(names)), "pre-push job names must be unique"
    unclassified = set(names) - REF_GUARD_JOBS - TREE_JOBS
    assert not unclassified, f"classify as ref guard or tree job: {sorted(unclassified)}"
    assert set(names) == REF_GUARD_JOBS | TREE_JOBS, "remove jobs gone from lefthook.yml"
    assert not TREE_JOBS & REF_GUARD_JOBS


def test_the_protected_branch_guard_carries_the_tag() -> None:
    # check_push_refs refusing a protected delete is covered end to end by
    # tests/test_pre_push_ref_guard_entrypoint.py. This pins that a delete reaches it.
    assert "push-ref-policy" in _tagged_job_names(runner.REF_GUARD_TAG)


# --- delete-only push through the real Lefthook binary --------------------


def _marker_config(marks: Path) -> dict:
    """Return lefthook.yml with each pre-push job's command replaced by a marker write.

    Job names, tags, groups, globs, and stdin settings stay as they are, so
    Lefthook selects jobs exactly as it does for the real config.
    """
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    for job in _leaf_jobs(config["pre-push"]["jobs"]):
        job.pop("env", None)
        name = job["name"]
        record = f"printf '%s\\n' {shlex.quote(name)} >> {shlex.quote(str(marks / 'ran.txt'))}"
        if job.get("use_stdin"):
            record += f"; cat > {shlex.quote(str(marks / (name + '.stdin')))}"
        job["run"] = record
    return {"pre-push": config["pre-push"], "min_version": config["min_version"]}


def _run_real_pre_push(tmp_path: Path, child_arguments: list[str]) -> tuple[int, set[str], Path]:
    assert _LEFTHOOK is not None
    repo = tmp_path / "repo"
    marks = tmp_path / "marks"
    marks.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    (repo / "lefthook.yml").write_text(yaml.safe_dump(_marker_config(marks)), encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("LEFTHOOK")}
    result = subprocess.run(
        [_LEFTHOOK, *child_arguments],
        cwd=repo,
        env=env,
        input=DELETE_LINE.encode(),
        capture_output=True,
        check=False,
        timeout=30,
    )
    ran_file = marks / "ran.txt"
    ran = set(ran_file.read_text(encoding="utf-8").split()) if ran_file.exists() else set()
    return result.returncode, ran, marks


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_real_lefthook_runs_only_the_ref_guards_on_a_delete(tmp_path: Path) -> None:
    child = runner._child_arguments(["run", "pre-push", *GIT_ARGUMENTS], DELETE_LINE.encode())
    assert GUARD_TAG_ARGS[0] in child

    returncode, ran, marks = _run_real_pre_push(tmp_path, child)

    assert returncode == 0
    assert ran == REF_GUARD_JOBS
    # The guards inside the piped group still get git's ref lines on stdin.
    assert (marks / "push-ref-policy.stdin").read_text(encoding="utf-8") == DELETE_LINE


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_real_lefthook_without_the_tag_runs_the_tree_jobs(tmp_path: Path) -> None:
    # Negative control: the same config and file list without the tag runs more
    # than the ref guards, so the test above proves the tag does the selecting.
    child = runner._child_arguments(["run", "pre-push", *GIT_ARGUMENTS], DELETE_LINE.encode())
    untagged = [item for item in child if item not in GUARD_TAG_ARGS]

    returncode, ran, _ = _run_real_pre_push(tmp_path, untagged)

    assert returncode == 0
    assert REF_GUARD_JOBS < ran
    assert "pre-pr-validation" in ran
