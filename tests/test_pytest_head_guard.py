"""Tests for the repository-wide pytest HEAD guard.

Direct-read/path-safety/fast-path tests for `_direct_read_repo_head` live in
`tests/test_pytest_head_fastpath.py`; this file covers trace/reflog/attribution
behavior (`_check_head_change`, `_trace_has_project_head_mutation`,
`_reflog_contains_action`, and the `_guard_real_repo_head` autouse fixture).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import types
import warnings
from pathlib import Path

import pytest

from tests.head_guard_test_helpers import (
    _commit_file,
    _init_git_repo,
    _load_root_conftest,
    _run_git,
)

pytestmark = pytest.mark.windows_path

BEFORE_SHA = "a" * 40
AFTER_SHA = "c" * 40


def _force_fast_path_fallback(module, monkeypatch) -> None:
    """Make `_direct_read_repo_head` raise so `_real_repo_head` reaches the subprocess path
    (inside this real checkout the fast path always resolves and never shells out)."""

    def _raise(*_args, **_kwargs):
        raise module._HeadFastPathUnresolvedError("forced for subprocess-path test")

    monkeypatch.setattr(module, "_direct_read_repo_head", _raise)


def test_real_repo_head_unsets_git_environment_overrides(monkeypatch):
    module = _load_root_conftest()
    _force_fast_path_fallback(module, monkeypatch)
    captured: dict[str, dict[str, object]] = {}

    monkeypatch.setenv("GIT_DIR", "wrong")
    monkeypatch.setenv("GIT_WORK_TREE", "wrong")
    monkeypatch.setenv("GIT_INDEX_FILE", "wrong")
    monkeypatch.setenv("GIT_COMMON_DIR", "wrong")
    monkeypatch.setenv("GIT_REFLOG_ACTION", "caller-action")
    monkeypatch.setenv("GIT_TRACE2_EVENT", "caller-trace.json")
    monkeypatch.setenv("GIT_TRACE_REFS", "caller-refs.log")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "kept")

    def fake_run(*_args, **kwargs):
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="abc123\n",
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head() == "abc123"
    kwargs = captured["kwargs"]
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert env["GIT_AUTHOR_NAME"] == "kept"
    for key in module._GIT_ENV_OVERRIDES | set(module._TRACE_ENV_NAMES):
        assert key not in env
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert "text" not in kwargs


def test_real_repo_head_subject_decodes_git_output_as_utf8(monkeypatch):
    module = _load_root_conftest()
    captured: dict[str, object] = {}

    def fake_run(*_args, **kwargs):
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="subject\n",
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head_subject() == "subject"
    kwargs = captured["kwargs"]
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert "text" not in kwargs


def test_real_repo_readers_return_fallbacks_on_git_error(monkeypatch):
    module = _load_root_conftest()
    _force_fast_path_fallback(module, monkeypatch)

    def raise_error(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(module.subprocess, "run", raise_error)

    assert module._real_repo_head() is None
    assert module._real_repo_head_subject() == "<unknown>"


def test_real_repo_readers_return_fallbacks_on_nonzero_exit(monkeypatch):
    module = _load_root_conftest()
    _force_fast_path_fallback(module, monkeypatch)

    def fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=128,
            stdout="ignored\n",
            stderr="fatal\n",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._real_repo_head() is None
    assert module._real_repo_head_subject() == "<unknown>"


def _silence_subject(module, monkeypatch):
    """Stub the commit-subject read so warn-path tests do not shell out to git."""
    monkeypatch.setattr(module, "_real_repo_head_subject", lambda: "concurrent work")


def test_check_head_change_is_silent_when_head_is_unchanged(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module._check_head_change("aaaaaaaa1111", "aaaaaaaa1111")

    assert caught == []


def test_check_head_change_warns_without_blaming_on_concurrent_commit(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with pytest.warns(UserWarning) as record:
        module._check_head_change("aaaaaaaa1111", "bbbbbbbb2222")

    message = str(record[0].message)
    assert "#3109" in message
    assert "aaaaaaaa" in message
    assert "bbbbbbbb" in message
    # The guard names the concurrent commit as the likely cause, never accuses.
    assert "concurrent external commit" in message
    assert "mutated the REAL repo" not in message


def test_check_head_change_fails_when_post_head_is_unreadable(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with pytest.raises(pytest.fail.Exception, match="could not read repository HEAD"):
        module._check_head_change("aaaaaaaa1111", None)


def test_check_head_change_fails_when_both_head_reads_are_unreadable(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with pytest.raises(pytest.fail.Exception, match="could not read repository HEAD"):
        module._check_head_change(None, None)


def test_check_head_change_is_silent_when_baseline_is_unreadable(monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module._check_head_change(None, "bbbbbbbb2222")

    assert caught == []


def _init_repo_with_non_head_commit(repo: Path) -> str:
    head = _init_git_repo(repo)
    non_head_commit = _commit_file(repo, "second\n", "second")
    _run_git(repo, "reset", "--hard", head)
    return non_head_commit


def _git_trace_env(path: Path) -> dict[str, str]:
    trace_names = ("GIT_TRACE2_EVENT", "GIT_TRACE_REFS", "GIT_TRACE_SETUP")
    return {**os.environ, **{name: str(path) for name in trace_names}}


def _write_trace2(
    path: Path,
    command: str,
    argv: list[str],
    worktree: Path,
    *,
    exit_code: int = 0,
) -> None:
    events = [
        {"event": "start", "sid": "test-session", "argv": argv},
        {
            "event": "def_repo",
            "sid": "test-session",
            "repo": 1,
            "worktree": str(worktree),
        },
        {"event": "cmd_name", "sid": "test-session", "name": command},
    ]
    lines = [f"{json.dumps(event)}\n" for event in events]
    lines.append(f"{json.dumps({'event': 'exit', 'sid': 'test-session', 'code': exit_code})}\n")
    path.write_text("".join(lines), encoding="utf-8")


def test_real_repo_head_subject_replaces_invalid_utf8(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    parent = _init_git_repo(repo)
    tree = _run_git(repo, "write-tree")
    commit_data = (
        f"tree {tree}\n"
        f"parent {parent}\n"
        "author pytest <pytest@example.invalid> 1 +0000\n"
        "committer pytest <pytest@example.invalid> 1 +0000\n"
        "encoding UTF-8\n"
        "\n"
        "invalid "
    ).encode() + b"\xff subject\n"
    commit = (
        subprocess.run(
            ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
            cwd=repo,
            check=True,
            input=commit_data,
            capture_output=True,
            timeout=10,
        )
        .stdout.decode("ascii")
        .strip()
    )
    _run_git(repo, "update-ref", "HEAD", commit)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    assert "invalid � subject" == module._real_repo_head_subject()


def test_reflog_action_detects_actual_commit(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    marker = "pytest-head-guard:test-commit"

    _commit_file(
        repo,
        "changed\n",
        "changed",
        env={**os.environ, "GIT_REFLOG_ACTION": marker},
    )

    assert module._reflog_contains_action(marker)


def test_reflog_action_detects_checkout_between_different_commits(
    tmp_path,
    monkeypatch,
):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    _run_git(repo, "branch", "other")
    _commit_file(repo, "changed\n", "changed")
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    marker = "pytest-head-guard:test-checkout"

    _run_git(
        repo,
        "checkout",
        "--quiet",
        "other",
        env={**os.environ, "GIT_REFLOG_ACTION": marker},
    )

    assert module._reflog_contains_action(marker)


def test_reflog_action_ignores_unmarked_external_commit(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    _commit_file(repo, "external\n", "external")

    assert not module._reflog_contains_action("pytest-head-guard:not-present")


def test_reflog_action_ignores_marked_unrelated_branch_update(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    marker = "pytest-head-guard:unrelated-branch"

    _run_git(
        repo,
        "branch",
        "other",
        env={**os.environ, "GIT_REFLOG_ACTION": marker},
    )

    assert not module._reflog_contains_action(marker)


def test_guard_fixture_fails_for_real_test_launched_head_movement(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)
    _commit_file(repo, "changed\n", "changed")

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command"):
        next(generator)


def test_guard_fixture_allows_branch_creation_from_recorded_base(tmp_path):
    repo = tmp_path / "repo"
    base = _init_git_repo(repo)

    _run_git(repo, "checkout", "-b", "local", base)

    assert _run_git(repo, "branch", "--show-current") == "local"


_SYMREF = ["git", "symbolic-ref"]
_OTHER_REF = "refs/heads/other"
_SYMBOLIC_REF_TRACE_CASES = [
    ("read_only", [*_SYMREF, "HEAD"], False),
    ("write", [*_SYMREF, "HEAD", _OTHER_REF], True),
    ("end_of_options", [*_SYMREF, "--end-of-options", "HEAD", _OTHER_REF], True),
    ("unknown_long_option", [*_SYMREF, "--no-delete", "HEAD", _OTHER_REF], True),
    ("long_option_prefix_of_another", [*_SYMREF, "--no-rec", "HEAD", _OTHER_REF], True),
    ("bundled_short_options", [*_SYMREF, "-qmreason", "HEAD", _OTHER_REF], True),
    ("windows_plumbing_executable", ["git-symbolic-ref.exe", "HEAD", _OTHER_REF], True),
    ("unrelated_ref", [*_SYMREF, "refs/meta/current", _OTHER_REF], False),
]


def test_trace_ignores_read_only_symbolic_ref(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "symbolic-ref",
        ["git", "symbolic-ref", "HEAD"],
        module.PROJECT_ROOT,
    )

    assert not module._trace_has_project_head_mutation(trace_path)


def test_trace_detects_successful_symbolic_ref_write_without_ref_transaction(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "symbolic-ref",
        ["git", "symbolic-ref", "HEAD", "refs/heads/other"],
        module.PROJECT_ROOT,
    )

    assert module._trace_has_project_head_mutation(trace_path)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [case[1:] for case in _SYMBOLIC_REF_TRACE_CASES],
    ids=[case[0] for case in _SYMBOLIC_REF_TRACE_CASES],
)
def test_trace_verdict_for_symbolic_ref_session(tmp_path, argv, expected):
    """A symbolic-ref session counts as a HEAD mutation only when it successfully repoints
    project HEAD, whether or not Git emitted the ref-transaction trace lines."""
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(trace_path, "symbolic-ref", argv, module.PROJECT_ROOT)

    assert module._trace_has_project_head_mutation(trace_path) is expected


def test_trace_parses_actual_symbolic_ref_write(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    _run_git(repo, "branch", "other")
    trace_path = tmp_path / "git-trace.json"
    _run_git(
        repo,
        "symbolic-ref",
        "HEAD",
        "refs/heads/other",
        env=_git_trace_env(trace_path),
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    assert module._trace_has_project_head_mutation(trace_path)


def test_check_head_change_ignores_reflog_expiry_trace_continuations(
    tmp_path,
    monkeypatch,
):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    trace_path = tmp_path / "git-trace.log"
    _run_git(
        repo,
        "reflog",
        "expire",
        "--all",
        "--expire=now",
        env=_git_trace_env(trace_path),
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    _silence_subject(module, monkeypatch)

    with pytest.warns(UserWarning, match="concurrent external commit"):
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:not-present",
            trace_path,
        )


def test_check_head_change_warns_when_unrelated_branch_write_coincides_with_commit(
    tmp_path,
    monkeypatch,
):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    second = _init_repo_with_non_head_commit(repo)
    trace_path = tmp_path / "git-trace.json"
    subprocess.run(
        ["git", "update-ref", "--stdin"],
        cwd=repo,
        check=True,
        input=f"update refs/heads/other {second}\n".encode(),
        env=_git_trace_env(trace_path),
        timeout=10,
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)
    _silence_subject(module, monkeypatch)

    with pytest.warns(UserWarning, match="concurrent external commit"):
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:not-present",
            trace_path,
        )


@pytest.mark.parametrize(
    ("reflog_found", "trace_found"),
    [(True, False), (False, True)],
    ids=["marked_reflog_action", "traced_head_mutation"],
)
def test_check_head_change_fails_for_attributed_mutation(
    tmp_path, monkeypatch, reflog_found, trace_found
):
    """Either attribution signal on its own blames the test, never the concurrent commit."""
    module = _load_root_conftest()
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: reflog_found)
    monkeypatch.setattr(module, "_trace_has_project_head_mutation", lambda _path: trace_found)
    trace_path = tmp_path / "git-trace.json"

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command"):
        module._check_head_change(BEFORE_SHA, AFTER_SHA, "pytest-head-guard:test", trace_path)


def test_check_head_change_warns_for_external_concurrent_commit(tmp_path, monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    monkeypatch.setattr(module, "_trace_has_project_head_mutation", lambda _path: False)
    trace_path = tmp_path / "git-trace.json"

    with pytest.warns(UserWarning, match="concurrent external commit"):
        module._check_head_change(BEFORE_SHA, AFTER_SHA, "pytest-head-guard:test", trace_path)


def test_check_head_change_fails_loud_when_call_failed_and_commit_is_concurrent(
    tmp_path, monkeypatch
):
    """Issue #5123: escalate to a distinct, greppable failure when the test's own
    call phase already failed and the HEAD move is not attributable to it."""
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    monkeypatch.setattr(module, "_trace_has_project_head_mutation", lambda _path: False)
    trace_path = tmp_path / "git-trace.json"

    with pytest.raises(pytest.fail.Exception, match="#5123") as excinfo:
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:test",
            trace_path,
            call_failed=True,
        )

    message = str(excinfo.value)
    assert "not meaningful" in message
    assert "concurrent external commit" in message


def test_check_head_change_still_warns_when_call_failed_but_head_is_unchanged(monkeypatch):
    """call_failed alone must not manufacture a failure when HEAD never moved."""
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module._check_head_change("aaaaaaaa1111", "aaaaaaaa1111", call_failed=True)

    assert caught == []


def test_check_head_change_attributed_mutation_ignores_call_failed(monkeypatch):
    """A real test-launched mutation stays #2316 regardless of call_failed; #5123
    is reserved for HEAD movement the guard could not attribute to the test."""
    module = _load_root_conftest()
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: True)

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command") as excinfo:
        module._check_head_change(
            BEFORE_SHA, AFTER_SHA, "pytest-head-guard:test", None, call_failed=True
        )

    assert "#5123" not in str(excinfo.value)


def test_pytest_runtest_makereport_stashes_call_phase_outcome():
    module = _load_root_conftest()
    node = types.SimpleNamespace(stash={})
    call = types.SimpleNamespace(when="call")
    report = types.SimpleNamespace(failed=True)

    generator = module.pytest_runtest_makereport(node, call)
    next(generator)
    with pytest.raises(StopIteration) as excinfo:
        generator.send(report)

    assert excinfo.value.value is report
    assert node.stash[module._CALL_FAILED_STASH_KEY] is True


def test_pytest_runtest_makereport_ignores_setup_and_teardown_phases():
    module = _load_root_conftest()
    node = types.SimpleNamespace(stash={})
    report = types.SimpleNamespace(failed=True)

    for when in ("setup", "teardown"):
        call = types.SimpleNamespace(when=when)
        generator = module.pytest_runtest_makereport(node, call)
        next(generator)
        with pytest.raises(StopIteration):
            generator.send(report)

    assert module._CALL_FAILED_STASH_KEY not in node.stash


def test_guard_fixture_escalates_when_stash_marks_call_failed(monkeypatch):
    """Wiring test: the fixture reads the stash the hook writes, end to end
    through `_guard_real_repo_head`, and escalates the #3109 warning to a
    #5123 failure exactly when the stash says the call phase failed."""
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    monkeypatch.setattr(module, "_trace_has_project_head_mutation", lambda _path: False)
    heads = iter(["aaaaaaaa1111", "bbbbbbbb2222"])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))
    node = types.SimpleNamespace(stash={module._CALL_FAILED_STASH_KEY: True})
    request = types.SimpleNamespace(node=node)

    generator = module._guard_real_repo_head.__wrapped__(request)
    next(generator)

    with pytest.raises(pytest.fail.Exception, match="#5123"):
        next(generator)


def test_guard_fixture_stays_a_warning_when_stash_has_no_entry(monkeypatch):
    """Same wiring, opposite input: an empty stash (test passed, or no report
    hook ran) must not manufacture the #5123 escalation."""
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    monkeypatch.setattr(module, "_trace_has_project_head_mutation", lambda _path: False)
    heads = iter(["aaaaaaaa1111", "bbbbbbbb2222"])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))
    node = types.SimpleNamespace(stash={})
    request = types.SimpleNamespace(node=node)

    generator = module._guard_real_repo_head.__wrapped__(request)
    next(generator)

    with pytest.warns(UserWarning, match="#3109"):
        with pytest.raises(StopIteration):
            next(generator)


@pytest.mark.parametrize(
    "break_trace",
    [
        lambda path: path.write_text("not-json\n", encoding="utf-8"),
        lambda path: path.mkdir(),
    ],
    ids=["malformed_json", "unreadable_directory"],
)
def test_check_head_change_fails_when_trace_cannot_be_read(tmp_path, monkeypatch, break_trace):
    """An unattributable trace fails loudly instead of being read as an external commit."""
    module = _load_root_conftest()
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    trace_path = tmp_path / "git-trace.json"
    break_trace(trace_path)

    with pytest.raises(pytest.fail.Exception, match="could not attribute"):
        module._check_head_change(BEFORE_SHA, AFTER_SHA, "pytest-head-guard:test", trace_path)


def test_guard_fixture_does_not_blame_test_for_external_commit(monkeypatch):
    """Reproduces #3109: HEAD moves during the test window; the test never ran git.

    Drives the real autouse fixture generator with a head-reader that returns a
    different SHA at teardown than at setup. The guard must warn, not fail.
    """
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)

    heads = iter(["aaaaaaaa1111", "bbbbbbbb2222"])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)  # fixture setup: captures the per-test baseline

    with pytest.warns(UserWarning, match="#3109"):
        with pytest.raises(StopIteration):
            next(generator)  # fixture teardown: reads the moved HEAD, warns


def test_guard_fixture_fails_for_test_launched_mutation(monkeypatch):
    module = _load_root_conftest()
    heads = iter([BEFORE_SHA, AFTER_SHA])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: True)

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command"):
        next(generator)


def test_guard_fixture_restores_existing_trace_settings(monkeypatch):
    module = _load_root_conftest()
    heads = iter([BEFORE_SHA, BEFORE_SHA])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))
    previous = {
        "GIT_REFLOG_ACTION": "caller-action",
        "GIT_TRACE2_EVENT": "caller-event.json",
        "GIT_TRACE_REFS": "caller-refs.log",
        "GIT_TRACE_SETUP": "caller-setup.log",
    }
    for name, value in previous.items():
        monkeypatch.setenv(name, value)

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)

    for name, value in previous.items():
        if name == "GIT_TRACE_REFS":
            assert name not in os.environ
        else:
            assert os.environ[name] != value
    with pytest.raises(StopIteration):
        next(generator)
    for name, value in previous.items():
        assert os.environ[name] == value


def test_guard_fixture_removes_new_trace_settings(monkeypatch):
    module = _load_root_conftest()
    heads = iter([BEFORE_SHA, BEFORE_SHA])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))
    for name in module._TRACE_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)

    assert os.environ["GIT_REFLOG_ACTION"].startswith("pytest-head-guard:")
    for name in module._TRACE_FILE_ENV_NAMES:
        assert name in os.environ
    for name in module._TRACE_BLOCKED_ENV_NAMES:
        assert name not in os.environ
    with pytest.raises(StopIteration):
        next(generator)
    for name in module._TRACE_ENV_NAMES:
        assert name not in os.environ


def test_guard_fixture_uses_shared_temp_directory_and_removes_trace_file(monkeypatch):
    module = _load_root_conftest()
    heads = iter([BEFORE_SHA, BEFORE_SHA])
    monkeypatch.setattr(module, "_real_repo_head", lambda: next(heads))

    generator = module._guard_real_repo_head.__wrapped__()
    next(generator)
    trace_path = Path(os.environ["GIT_TRACE2_EVENT"])

    assert all(os.environ[name] == str(trace_path) for name in module._TRACE_FILE_ENV_NAMES)
    assert trace_path.parent == Path(tempfile.gettempdir())
    assert ":" not in trace_path.name
    trace_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(StopIteration):
        next(generator)
    assert not trace_path.exists()
