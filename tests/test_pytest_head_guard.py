"""Tests for the repository-wide pytest HEAD guard."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import pytest

BEFORE_SHA = "a" * 40
AFTER_SHA = "c" * 40


def _load_root_conftest():
    path = Path(__file__).resolve().parents[1] / "conftest.py"
    spec = importlib.util.spec_from_file_location("root_conftest_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["root_conftest_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_real_repo_head_unsets_git_environment_overrides(monkeypatch):
    module = _load_root_conftest()
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

    def raise_error(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr(module.subprocess, "run", raise_error)

    assert module._real_repo_head() is None
    assert module._real_repo_head_subject() == "<unknown>"


def test_real_repo_readers_return_fallbacks_on_nonzero_exit(monkeypatch):
    module = _load_root_conftest()

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


def _run_git(repo: Path, *args: str, env=None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=10,
    )
    return result.stdout.strip()


def _commit_file(repo: Path, content: str, message: str, env=None) -> str:
    (repo / "file.txt").write_text(content, encoding="utf-8")
    _run_git(repo, "add", "file.txt")
    _run_git(
        repo,
        "-c",
        "user.name=pytest",
        "-c",
        "user.email=pytest@example.invalid",
        "commit",
        "--quiet",
        "-m",
        message,
        env=env,
    )
    return _run_git(repo, "rev-parse", "HEAD")


def _init_git_repo(repo: Path) -> str:
    repo.mkdir()
    _run_git(repo, "init", "--quiet")
    return _commit_file(repo, "initial\n", "initial")


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
    head_mutated: bool = False,
    symref_mutated: bool = False,
    transaction_finish: int = 0,
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
    if head_mutated:
        lines.extend(
            [
                "00:00:00.000000 refs/debug.c:80         transaction {\n",
                f"00:00:00.000001 refs/debug.c:73         0: HEAD {BEFORE_SHA} "
                f'-> {AFTER_SHA} (F=0x5, T=0x1) ""\n',
                "00:00:00.000002 refs/debug.c:86         }\n",
                f"00:00:00.000003 refs/debug.c:99         finish: {transaction_finish}\n",
            ]
        )
    if symref_mutated:
        lines.append(
            "00:00:00.000004 refs/debug.c:141        create_symref: HEAD -> "
            'refs/heads/other "": 0\n'
        )
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


def test_guard_fixture_allows_branch_creation_from_recorded_base(tmp_path):
    repo = tmp_path / "repo"
    base = _init_git_repo(repo)

    _run_git(repo, "checkout", "-b", "local", base)

    assert _run_git(repo, "branch", "--show-current") == "local"


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


def test_trace_detects_symbolic_ref_write(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "symbolic-ref",
        ["git", "symbolic-ref", "HEAD", "refs/heads/other"],
        module.PROJECT_ROOT,
        symref_mutated=True,
    )

    assert module._trace_has_project_head_mutation(trace_path)


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
    "argv",
    [
        ["git", "symbolic-ref", "--end-of-options", "HEAD", "refs/heads/other"],
        ["git", "symbolic-ref", "--no-delete", "HEAD", "refs/heads/other"],
        ["git", "symbolic-ref", "--no-rec", "HEAD", "refs/heads/other"],
        ["git", "symbolic-ref", "-qmreason", "HEAD", "refs/heads/other"],
        ["git-symbolic-ref.exe", "HEAD", "refs/heads/other"],
    ],
)
def test_trace_detects_supported_symbolic_ref_write_forms(tmp_path, argv):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(trace_path, "symbolic-ref", argv, module.PROJECT_ROOT)

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_ignores_symbolic_ref_write_to_unrelated_ref(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "symbolic-ref",
        ["git", "symbolic-ref", "refs/meta/current", "refs/heads/other"],
        module.PROJECT_ROOT,
    )

    assert not module._trace_has_project_head_mutation(trace_path)


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


def test_trace_parses_actual_commit_transaction(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    trace_path = tmp_path / "git-trace.log"
    _commit_file(
        repo,
        "changed\n",
        "changed",
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


def test_trace_detects_explicit_project_git_dir(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    project_git_dir = module._project_git_dir()
    _write_trace2(
        trace_path,
        "update-ref",
        [
            "git",
            f"--git-dir={project_git_dir}",
            "update-ref",
            "HEAD",
            AFTER_SHA,
        ],
        tmp_path / "other-worktree",
        head_mutated=True,
    )

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_detects_project_git_dir_from_environment(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    second = _init_repo_with_non_head_commit(repo)
    outside.mkdir()
    trace_path = tmp_path / "git-trace.log"
    env = _git_trace_env(trace_path)
    env["GIT_DIR"] = str(repo / ".git")
    _run_git(outside, "update-ref", "HEAD", second, env=env)
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_ignores_failed_plumbing_write(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "update-ref",
        ["git", "update-ref", "HEAD", "invalid-object"],
        module.PROJECT_ROOT,
        exit_code=128,
        head_mutated=True,
        transaction_finish=-1,
    )

    assert not module._trace_has_project_head_mutation(trace_path)


def test_trace_recognizes_windows_plumbing_executable(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "update-ref",
        [
            r"C:\Program Files\Git\mingw64\libexec\git-core\git-update-ref.exe",
            "HEAD",
            AFTER_SHA,
        ],
        module.PROJECT_ROOT,
        head_mutated=True,
    )

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_detects_update_ref_write(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "update-ref",
        ["git", "update-ref", "HEAD", AFTER_SHA],
        module.PROJECT_ROOT,
        head_mutated=True,
    )

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_detects_update_ref_write_to_checked_out_branch(tmp_path, monkeypatch):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    second = _init_repo_with_non_head_commit(repo)
    branch_ref = _run_git(repo, "symbolic-ref", "HEAD")
    trace_path = tmp_path / "git-trace.json"
    _run_git(
        repo,
        "update-ref",
        branch_ref,
        second,
        env=_git_trace_env(trace_path),
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_detects_update_ref_stdin_write_to_checked_out_branch(
    tmp_path,
    monkeypatch,
):
    module = _load_root_conftest()
    repo = tmp_path / "repo"
    second = _init_repo_with_non_head_commit(repo)
    branch_ref = _run_git(repo, "symbolic-ref", "HEAD")
    trace_path = tmp_path / "git-trace.json"
    subprocess.run(
        ["git", "update-ref", "--stdin"],
        cwd=repo,
        check=True,
        input=f"update {branch_ref} {second}\n".encode(),
        env=_git_trace_env(trace_path),
        timeout=10,
    )
    monkeypatch.setattr(module, "PROJECT_ROOT", repo)

    assert module._trace_has_project_head_mutation(trace_path)


def test_trace_ignores_plumbing_write_in_other_worktree(tmp_path):
    module = _load_root_conftest()
    trace_path = tmp_path / "git-trace.json"
    _write_trace2(
        trace_path,
        "update-ref",
        ["git", "update-ref", "HEAD", AFTER_SHA],
        tmp_path / "isolated-repo",
        head_mutated=True,
    )

    assert not module._trace_has_project_head_mutation(trace_path)


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


def test_check_head_change_fails_for_marked_reflog_action(tmp_path, monkeypatch):
    module = _load_root_conftest()
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: True)
    monkeypatch.setattr(
        module,
        "_trace_has_project_head_mutation",
        lambda _path: False,
    )

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command"):
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:test",
            tmp_path / "trace.json",
        )


def test_check_head_change_fails_for_traced_head_mutation(tmp_path, monkeypatch):
    module = _load_root_conftest()
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    monkeypatch.setattr(
        module,
        "_trace_has_project_head_mutation",
        lambda _path: True,
    )

    with pytest.raises(pytest.fail.Exception, match="test-launched Git command"):
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:test",
            tmp_path / "trace.json",
        )


def test_check_head_change_warns_for_external_concurrent_commit(tmp_path, monkeypatch):
    module = _load_root_conftest()
    _silence_subject(module, monkeypatch)
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    monkeypatch.setattr(
        module,
        "_trace_has_project_head_mutation",
        lambda _path: False,
    )

    with pytest.warns(UserWarning, match="concurrent external commit"):
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:test",
            tmp_path / "trace.json",
        )


def test_check_head_change_fails_when_trace_is_malformed(tmp_path, monkeypatch):
    module = _load_root_conftest()
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    trace_path = tmp_path / "git-trace.json"
    trace_path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(pytest.fail.Exception, match="could not attribute"):
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:test",
            trace_path,
        )


def test_check_head_change_fails_when_trace_is_unreadable(tmp_path, monkeypatch):
    module = _load_root_conftest()
    monkeypatch.setattr(module, "_reflog_contains_action", lambda _marker: False)
    trace_path = tmp_path / "git-trace"
    trace_path.mkdir()

    with pytest.raises(pytest.fail.Exception, match="could not attribute"):
        module._check_head_change(
            BEFORE_SHA,
            AFTER_SHA,
            "pytest-head-guard:test",
            trace_path,
        )


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
